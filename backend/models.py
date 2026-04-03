# backend/models.py  # noqa
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from typing import List, Dict

# Quantitative Models
MODELS_AVAILABLE = False
try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    from prophet import Prophet
    from sklearn.ensemble import RandomForestRegressor
    MODELS_AVAILABLE = True
except ImportError:
    pass

logger = logging.getLogger(__name__)

FORECAST_DAYS = 5


# ---------------------------------------------------------------------------
# Technical Indicators
# ---------------------------------------------------------------------------

def calculate_macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict:
    """Returns per-point MACD line, signal line, and histogram lists."""
    series = pd.Series(prices)
    ema_fast   = series.ewm(span=fast,   adjust=False).mean()
    ema_slow   = series.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return {
        "macd":   [round(v, 4) if not np.isnan(v) else None for v in macd_line],
        "signal": [round(v, 4) if not np.isnan(v) else None for v in signal_line],
        "hist":   [round(v, 4) if not np.isnan(v) else None for v in histogram],
    }


def calculate_bollinger_bands(
    prices: List[float],
    window: int = 20,
    num_std: float = 2.0,
) -> Dict:
    """Returns per-point upper, middle, lower Bollinger Band lists."""
    series = pd.Series(prices)
    middle = series.rolling(window=window).mean()
    std    = series.rolling(window=window).std()
    upper  = middle + num_std * std
    lower  = middle - num_std * std
    def _clean(s):
        return [round(v, 4) if not np.isnan(v) else None for v in s]
    return {"upper": _clean(upper), "middle": _clean(middle), "lower": _clean(lower)}


def calculate_sma_series(prices: List[float], period: int) -> List:
    """Returns SMA array for given period, None where insufficient data."""
    series = pd.Series(prices)
    sma = series.rolling(window=period).mean()
    return [round(v, 4) if not np.isnan(v) else None for v in sma]


def calculate_rsi_series(prices: List[float], periods: int = 14) -> List:
    """Returns full RSI series (same length as prices), None where insufficient data."""
    series = pd.Series(prices)
    delta  = series.diff()
    gain   = delta.where(delta > 0, 0).ewm(com=periods - 1, min_periods=periods).mean()
    loss   = (-delta.where(delta < 0, 0)).ewm(com=periods - 1, min_periods=periods).mean()
    loss   = loss.replace(0, 1e-9)
    rsi    = 100 - (100 / (1 + gain / loss))
    return [round(float(v), 2) if not pd.isna(v) else None for v in rsi]


def calculate_rsi(prices: List[float], periods: int = 14) -> float:
    if len(prices) < periods + 1:
        return 50.0
    series = pd.Series(prices)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    loss = loss.replace(0, 1e-9)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0


def calculate_support_resistance(
    prices: List[float],
    lookback: int = 65,       # ~3 months of trading days
    window: int = 5,           # local extremum neighbourhood
    cluster_tol_pct: float = 1.5,   # merge levels within 1.5% of each other
    max_levels: int = 3,       # return up to 3 support and 3 resistance lines
) -> Dict:
    """
    Identifies key support and resistance levels from recent price history.

    Strategy:
      1. Take the last `lookback` closing prices.
      2. Find all local minima (potential support) and maxima (potential resistance)
         using a rolling window comparison — a point is a local min/max if it is
         the lowest/highest value in a 2*window+1 neighbourhood.
      3. Cluster nearby levels: if two extrema are within `cluster_tol_pct`% of
         each other, keep only the average (weighted by frequency).
      4. Return the `max_levels` strongest levels of each type, sorted by proximity
         to the most recent close.

    Returns a dict with keys "support" and "resistance", each a list of floats.
    """
    if len(prices) < window * 2 + 2:
        return {"support": [], "resistance": []}

    data = prices[-lookback:]
    arr  = np.array(data)

    supports: List[float] = []
    resistances: List[float] = []

    for i in range(window, len(arr) - window):
        neighbourhood = arr[i - window: i + window + 1]
        if arr[i] == neighbourhood.min():
            supports.append(float(arr[i]))
        if arr[i] == neighbourhood.max():
            resistances.append(float(arr[i]))

    def _cluster(levels: List[float]) -> List[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clusters: List[List[float]] = [[levels[0]]]
        for val in levels[1:]:
            centre = np.mean(clusters[-1])
            if abs(val - centre) / centre * 100 <= cluster_tol_pct:
                clusters[-1].append(val)
            else:
                clusters.append([val])
        return [round(float(np.mean(c)), 2) for c in clusters]

    support_levels    = _cluster(supports)
    resistance_levels = _cluster(resistances)

    last_price = arr[-1]

    # Keep levels below/above current price; sort by closeness to current price
    support_levels    = sorted(
        [support_level for support_level in support_levels    if support_level < last_price],
        key=lambda x: abs(x - last_price),
    )[:max_levels]
    resistance_levels = sorted(
        [resistance_level for resistance_level in resistance_levels if resistance_level > last_price],
        key=lambda x: abs(x - last_price),
    )[:max_levels]

    return {"support": support_levels, "resistance": resistance_levels}


def calculate_model_stats(prices: List[float]) -> Dict:
    """
    Returns a dict of descriptive statistics used both in the response
    and as context for the AI analysis layer later.
    """
    arr = np.array(prices)
    returns = np.diff(arr) / arr[:-1]

    # Annualised volatility (252 trading days)
    ann_vol = float(np.std(returns) * np.sqrt(252)) if len(returns) > 1 else 0.0

    # Linear trend slope over last 20 days (positive = uptrend)
    window = arr[-20:] if len(arr) >= 20 else arr
    x = np.arange(len(window))
    slope, _ = np.polyfit(x, window, 1)
    trend_slope = float(slope)

    # 20-day simple moving average
    sma20 = float(np.mean(arr[-20:])) if len(arr) >= 20 else float(np.mean(arr))

    # Distance from SMA (momentum proxy)
    last = float(arr[-1])
    sma_pct = ((last - sma20) / sma20 * 100) if sma20 > 0 else 0.0

    return {
        "ann_volatility_pct": round(ann_vol * 100, 2),
        "trend_slope":        round(trend_slope, 4),
        "sma_20":             round(sma20, 2),
        "price_vs_sma20_pct": round(sma_pct, 2),
    }


# ---------------------------------------------------------------------------
# Per-model forecast helpers
# ---------------------------------------------------------------------------

def _prophet_forecast(prices: List[float], steps: int) -> np.ndarray:
    df = pd.DataFrame({
        "ds": pd.date_range(end=datetime.now(timezone.utc), periods=len(prices), freq="B"),
        "y":  prices,
    })
    m = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        changepoint_prior_scale=0.05,
        interval_width=0.80,
    )
    m.fit(df)
    future = m.make_future_dataframe(periods=steps, freq="B")
    fc = m.predict(future).tail(steps)
    return fc[["yhat", "yhat_lower", "yhat_upper"]].values   # shape (steps, 3)


def _sarima_forecast(prices: List[float], steps: int) -> np.ndarray:
    model = SARIMAX(prices, order=(1, 1, 1), enforce_stationarity=False, enforce_invertibility=False)
    fit = model.fit(disp=False)
    fc = fit.get_forecast(steps=steps)
    mean = fc.predicted_mean.values
    ci   = fc.conf_int(alpha=0.20).values   # 80% CI → columns [lower, upper]
    return np.column_stack([mean, ci[:, 0], ci[:, 1]])       # shape (steps, 3)


def _rf_forecast(prices: List[float], steps: int) -> np.ndarray:
    """
    Random Forest: use a sliding window of the last 10 closes as features.
    Returns point estimates only (no CI from RF — we derive bands from volatility).
    """
    window = 10
    if len(prices) < window + 1:
        last = prices[-1]
        return np.column_stack([
            np.full(steps, last),
            np.full(steps, last),
            np.full(steps, last),
        ])

    X, y = [], []
    for i in range(len(prices) - window):
        X.append(prices[i: i + window])
        y.append(prices[i + window])
    X, y = np.array(X), np.array(y)

    rf = RandomForestRegressor(n_estimators=100, random_state=42)
    rf.fit(X, y)

    preds = []
    last_window = list(prices[-window:])
    vol = np.std(prices[-20:]) / np.mean(prices[-20:]) if len(prices) >= 20 else 0.02
    for _ in range(steps):
        p = float(rf.predict([last_window])[0])
        preds.append(p)
        last_window = last_window[1:] + [p]

    preds = np.array(preds)
    # RF gives point estimates; use historical vol to derive bands
    band = preds * vol * 1.5
    return np.column_stack([preds, preds - band, preds + band])


# ---------------------------------------------------------------------------
# Main ensemble entry point
# ---------------------------------------------------------------------------

def run_ensemble_forecast(prices: List[float], symbol: str) -> Dict:
    """
    Returns:
        forecast_days : list of FORECAST_DAYS dicts, each with
                        { date, predicted, high, low, confidence_pct }
        high          : overall 5-day high (backwards-compat with frontend)
        low           : overall 5-day low
        note          : analyst narrative
        conf          : 'high' | 'medium' | 'low'
        stats         : descriptive statistics dict
    """
    last_price = float(prices[-1]) if prices else 100.0
    vol = np.std(prices[-10:]) / np.mean(prices[-10:]) if len(prices) >= 10 else 0.02
    stats = calculate_model_stats(prices) if len(prices) >= 5 else {}

    # ── Fallback (models unavailable or not enough data) ─────────────────────
    if not MODELS_AVAILABLE or len(prices) < 20:
        days = []
        for i in range(1, FORECAST_DAYS + 1):
            dt = (datetime.now(timezone.utc) + timedelta(days=i))
            predicted = round(last_price * (1 + (vol * 0.3 * (1 if i % 2 == 0 else -0.5))), 2)
            days.append({
                "date":           dt.strftime("%m/%d"),
                "predicted":      predicted,
                "high":           round(predicted * (1 + vol), 2),
                "low":            round(predicted * (1 - vol), 2),
                "confidence_pct": 30,
            })
        return {
            "forecast_days": days,
            "high":  max(d["high"] for d in days),
            "low":   min(d["low"]  for d in days),
            "note":  "Insufficient history for full model run — using volatility estimate.",
            "conf":  "low",
            "stats": stats,
        }

    # ── Run all three models ──────────────────────────────────────────────────
    p_fc = s_fc = r_fc = None
    errors = []

    try:
        p_fc = _prophet_forecast(prices, FORECAST_DAYS)
    except Exception as e:
        errors.append(f"Prophet: {e}")
        logger.warning(f"Prophet forecast failed: {e}")

    try:
        s_fc = _sarima_forecast(prices, FORECAST_DAYS)
    except Exception as e:
        errors.append(f"SARIMA: {e}")
        logger.warning(f"SARIMA forecast failed: {e}")

    try:
        r_fc = _rf_forecast(prices, FORECAST_DAYS)
    except Exception as e:
        errors.append(f"RF: {e}")
        logger.warning(f"RF forecast failed: {e}")

    available = [fc for fc in [p_fc, s_fc, r_fc] if fc is not None]
    if not available:
        # All three failed — use fallback
        logger.error(f"All models failed for {symbol}: {errors}")
        days = []
        for i in range(1, FORECAST_DAYS + 1):
            dt = datetime.now(timezone.utc) + timedelta(days=i)
            days.append({
                "date":           dt.strftime("%m/%d"),
                "predicted":      round(last_price * (1 + vol * 0.1 * i * 0.3), 2),
                "high":           round(last_price * (1 + vol * i * 0.4), 2),
                "low":            round(last_price * (1 - vol * i * 0.4), 2),
                "confidence_pct": 20,
            })
        return {
            "forecast_days": days,
            "high":  max(d["high"] for d in days),
            "low":   min(d["low"]  for d in days),
            "note":  f"Model errors: {'; '.join(errors)}. Using fallback estimate.",
            "conf":  "low",
            "stats": stats,
        }

    # ── Dynamic weights: inverse-error weighting ──────────────────────────────
    # Use each model's in-sample error vs. last known price as a weight proxy.
    # Models that predicted closer to last_price get higher weight.
    raw_weights = []
    for fc in [p_fc, s_fc, r_fc]:
        if fc is None:
            raw_weights.append(0.0)
        else:
            err = abs(fc[0, 0] - last_price)    # error on day-1 prediction
            raw_weights.append(1.0 / (err + 1e-6))

    total = sum(raw_weights)
    w = [rw / total for rw in raw_weights]
    logger.info(f"Ensemble weights for {symbol} → Prophet:{w[0]:.2f} SARIMA:{w[1]:.2f} RF:{w[2]:.2f}")

    # ── Build per-day forecast ────────────────────────────────────────────────
    days = []
    for i in range(FORECAST_DAYS):
        # Weighted average of available model point estimates
        predicted = 0.0
        high_sum  = 0.0
        low_sum   = 0.0
        w_used    = 0.0

        for fc, wi in zip([p_fc, s_fc, r_fc], w):
            if fc is None:
                continue
            predicted += wi * fc[i, 0]
            low_sum   += wi * fc[i, 1]
            high_sum  += wi * fc[i, 2]
            w_used    += wi

        if w_used > 0:
            predicted /= w_used
            high_sum  /= w_used
            low_sum   /= w_used

        # Widen bands slightly per day (uncertainty grows over time)
        horizon_factor = 1 + i * 0.05
        day_high = round(max(high_sum, predicted) * horizon_factor, 2)
        day_low  = round(min(low_sum,  predicted) / horizon_factor, 2)

        # Confidence: more models + more data = higher confidence, decreases with horizon
        n_models   = len(available)
        base_conf  = 40 + (len(prices) // 10) + (n_models * 10)
        conf_pct   = max(10, min(90, base_conf - i * 5))

        dt = datetime.now(timezone.utc) + timedelta(days=i + 1)
        days.append({
            "date":           dt.strftime("%m/%d"),
            "predicted":      round(predicted, 2),
            "high":           day_high,
            "low":            day_low,
            "confidence_pct": conf_pct,
        })

    # ── Analyst narrative ─────────────────────────────────────────────────────
    d1 = days[0]["predicted"]
    d5 = days[-1]["predicted"]
    direction  = "upward" if d5 > last_price else "downward"
    pct_change = abs((d5 - last_price) / last_price * 100)

    active_models = []
    if p_fc is not None:
        active_models.append(f"Prophet (w={w[0]:.0%})")
    if s_fc is not None:
        active_models.append(f"SARIMA (w={w[1]:.0%})")
    if r_fc is not None:
        active_models.append(f"Random Forest (w={w[2]:.0%})")

    vol_label = "high" if vol > 0.03 else "moderate" if vol > 0.015 else "low"
    note = (
        f"5-day ensemble ({', '.join(active_models)}): "
        f"projects a {direction} move of ~{pct_change:.1f}% by {days[-1]['date']}. "
        f"Day-1 target ${d1:.2f} → Day-5 target ${d5:.2f}. "
        f"Annualised volatility is {vol_label} at {stats.get('ann_volatility_pct', 0):.1f}%. "
        f"Price is {abs(stats.get('price_vs_sma20_pct', 0)):.1f}% "
        f"{'above' if stats.get('price_vs_sma20_pct', 0) >= 0 else 'below'} the 20-day SMA."
    )

    overall_high = max(d["high"] for d in days)
    overall_low  = min(d["low"]  for d in days)
    conf_label   = "high" if len(prices) > 100 and len(available) == 3 else \
                   "medium" if len(prices) > 40 else "low"

    return {
        "forecast_days": days,
        "high":          overall_high,
        "low":           overall_low,
        "note":          note,
        "conf":          conf_label,
        "stats":         stats,
    }
