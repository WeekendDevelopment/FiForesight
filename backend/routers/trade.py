# backend/routers/trade.py
import json
import logging
from typing import Any, List

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from config import Config
from dependencies import analyst_jury_svc

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Trade Setup endpoint
# ---------------------------------------------------------------------------

class TradeSetupRequest(BaseModel):
    symbol: str
    current_price: float
    high_range: float
    low_range: float
    rsi: float
    support: List[float] = []
    resistance: List[float] = []
    trend: str = "Bullish"
    sentiment_label: str = "Neutral"

    @field_validator("current_price")
    @classmethod
    def validate_current_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("current_price must be > 0")
        return v

    @field_validator("rsi")
    @classmethod
    def validate_rsi(cls, v: float) -> float:
        if not (0 <= v <= 100):
            raise ValueError("rsi must be between 0 and 100")
        return v

    @field_validator("high_range")
    @classmethod
    def validate_ranges(cls, v: float, info: Any) -> float:
        low = info.data.get("low_range")
        if low is not None and v <= low:
            raise ValueError("high_range must be > low_range")
        return v

    @field_validator("support", "resistance")
    @classmethod
    def validate_non_negative(cls, v: List[float]) -> List[float]:
        if any(x < 0 for x in v):
            raise ValueError("support/resistance values must be non-negative")
        return v


class TradeSetupResponse(BaseModel):
    entry_low: float
    entry_high: float
    stop_loss: float
    target_1: float
    target_2: float
    target_3: float
    risk_reward: str
    setup_type: str
    rationale: str


@router.post("/trade-setup", response_model=TradeSetupResponse)
async def trade_setup(req: TradeSetupRequest):
    p = req.current_price

    if req.trend == "Bearish":
        # Entry zone: nearest resistance within 3% above price, else price ± 0.5%
        resistance_nearby = sorted(
            [r for r in req.resistance if 1.0 <= r / p <= 1.03],
        )
        if resistance_nearby:
            entry_high = round(resistance_nearby[0], 2)
            entry_low  = round(entry_high * 0.99, 2)
        else:
            entry_high = round(p * 1.005, 2)
            entry_low  = round(p * 0.995, 2)

        entry_mid = (entry_low + entry_high) / 2

        # Stop: nearest resistance above entry_high, capped at 5% above entry_mid
        resistance_above = sorted([r for r in req.resistance if r > entry_high])
        if resistance_above:
            raw_stop = round(resistance_above[0] * 1.015, 2)
        else:
            raw_stop = round(entry_high * 1.03, 2)
        max_stop  = round(entry_mid * 1.05, 2)
        stop_loss = round(min(raw_stop, max_stop), 2)

        # Targets: descending below entry_mid toward low_range
        target_1 = round(entry_mid - (entry_mid - req.low_range) / 3, 2)
        target_2 = round(req.low_range, 2)
        target_3 = round(req.low_range - (entry_mid - req.low_range), 2)

        # R:R — risk is distance to stop above, reward is distance to T2 below
        risk        = max(stop_loss - entry_mid, 0.01)
        reward      = max(entry_mid - target_2, 0.01)
        risk_reward = f"1:{reward / risk:.1f}"
    else:
        # Bullish: entry zone near nearest support within 3% below price
        support_nearby = sorted(
            [s for s in req.support if 0.97 <= s / p <= 1.0],
            reverse=True,
        )
        if support_nearby:
            entry_low  = round(support_nearby[0], 2)
            entry_high = round(entry_low * 1.01, 2)
        else:
            entry_low  = round(p * 0.995, 2)
            entry_high = round(p * 1.005, 2)

        # Stop: nearest support below entry_low, capped at 5% below entry_mid
        support_below_entry = sorted(
            [s for s in req.support if s < entry_low],
            reverse=True,
        )
        if support_below_entry:
            stop_loss = round(support_below_entry[0] * 0.985, 2)
        else:
            stop_loss = round(entry_low * 0.97, 2)

        entry_mid = (entry_low + entry_high) / 2

        # Targets: ascending above entry_mid toward high_range
        target_1 = round(entry_mid + (req.high_range - entry_mid) / 3, 2)
        target_2 = round(req.high_range, 2)
        target_3 = round(req.high_range + (req.high_range - entry_low), 2)

        # R:R — cap stop at 5% below entry so R:R stays meaningful
        raw_stop    = stop_loss
        min_stop    = round(entry_mid * 0.95, 2)
        stop_loss   = round(max(raw_stop, min_stop), 2)
        risk        = max(entry_mid - stop_loss, 0.01)
        reward      = max(target_2 - entry_mid, 0.01)
        risk_reward = f"1:{reward / risk:.1f}"

    # Setup type derived from trend + RSI
    rsi = req.rsi
    if req.trend == "Bullish" and rsi <= 40:
        setup_type = "Oversold Reversal"
    elif req.trend == "Bullish" and rsi >= 65:
        setup_type = "Momentum Continuation"
    elif req.trend == "Bullish":
        setup_type = "Support Bounce"
    elif req.trend == "Bearish" and rsi >= 70:
        setup_type = "Overbought Fade"
    elif req.trend == "Bearish" and rsi <= 40:
        setup_type = "Breakdown Play"
    else:
        setup_type = "Range Consolidation"

    # Rationale via Groq (~80 tokens)
    rationale = (
        f"{setup_type} setup with RSI at {rsi:.0f} and a {req.trend.lower()} trend; "
        f"entry zone ${entry_low:.2f}–${entry_high:.2f} targets ${target_2:.2f}."
    )
    try:
        system = (
            "You are a trading analyst. "
            "Respond in exactly one plain-text sentence — no markdown, no bullet points."
        )
        user = (
            f"Symbol: {req.symbol} | Price: ${p:.2f} | RSI: {rsi:.1f} | "
            f"Trend: {req.trend} | Sentiment: {req.sentiment_label}\n"
            f"Entry: ${entry_low:.2f}–${entry_high:.2f} | Stop: ${stop_loss:.2f} | "
            f"Targets: ${target_1:.2f} / ${target_2:.2f} / ${target_3:.2f}\n"
            f"Write one sentence explaining why this {setup_type} trade setup makes sense."
        )
        raw = await analyst_jury_svc._call_groq("llama-3.3-70b-versatile", system, user)
        rationale = raw.strip()
    except Exception as exc:
        logger.warning("[TRADE-SETUP] Groq rationale failed: %s", exc)

    return TradeSetupResponse(
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        risk_reward=risk_reward,
        setup_type=setup_type,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Chat SSE endpoint
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    context: dict = {}
    history: List[dict] = []


@router.post("/chat")
async def chat_endpoint(req: ChatRequest):
    async def generate():
        ctx = req.context
        system = (
            f"You are a financial assistant for FiForesight.\n"
            f"Ticker: {ctx.get('symbol', 'N/A')}\n"
            f"Current Price: ${ctx.get('currentPrice', 'N/A')}\n"
            f"RSI: {ctx.get('rsi', 'N/A')} | Trend: {ctx.get('trend', 'N/A')}\n"
            f"Analyst Jury: {ctx.get('jury_summary', 'N/A')}\n"
            f"Sentiment: {ctx.get('sentiment_label', 'N/A')}\n"
            f"Recent Headlines: {ctx.get('headlines', 'N/A')}\n\n"
            "Answer concisely. Use plain language — assume the user may be a beginner. "
            "Do not give financial advice. Use 'could', 'may', 'historically' language."
        )

        messages: List[dict] = [{"role": "system", "content": system}]
        for msg in req.history[-10:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": req.message})

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "stream": True,
            "max_tokens": 400,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    "https://api.groq.com/openai/v1/chat/completions",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {Config.GROQ_API_KEY}",
                        "Content-Type": "application/json",
                    },
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning("[CHAT] Groq returned %s: %s", response.status_code, body[:200])
                        yield f"data: [ERROR] Groq error {response.status_code}\n\n"
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            chunk = json.loads(data)
                            token = chunk["choices"][0]["delta"].get("content", "")
                            if token:
                                yield f"data: {json.dumps(token)}\n\n"
                        except Exception:
                            continue
        except Exception as exc:
            logger.warning("[CHAT] Groq streaming failed: %s", exc)
            yield "data: [ERROR] Streaming unavailable\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
