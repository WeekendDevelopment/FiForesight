"""
Forecast Calibration Audit (Feature 30) — read-only "should I trust this forecast?"

Pure transform over data already in InfluxDB (`forecast_record` + `price_outcome`),
the same sources the Insights tab uses. No new data is collected.

It answers three questions over *resolved* forecasts (a forecast joined to the
realized close on/after its target date):

  COVERAGE     — what % of realized prices landed inside the forecast band?
                 We audit the persisted 48h high/low range (`e_d1_low`/`e_d1_high`).
                 Monte-Carlo P10/P90 are computed per /predict but NOT persisted, so
                 on real data `p10`/`p90` default to the stored range; synthetic
                 records may supply explicit percentiles to audit a tighter band.
  DIRECTIONAL  — directional accuracy of the ensemble d1 median (`e_d1`) vs a naive
    EDGE         persistence baseline ("tomorrow's move = yesterday's move").
  BIAS         — mean signed error (p50 − actual): >0 systematically high, <0 low.

`compute_calibration(symbol)` queries the store; `symbol=None`/"ALL" aggregates
across every symbol that has forecast history. The math lives in side-effect-free
helpers (`_score_records` / `_aggregate`) so it is trivially unit-testable.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Optional

from dependencies import forecast_store

logger = logging.getLogger(__name__)

# Lookback window for both queries (days).
_LOOKBACK_DAYS = 90
# Minimum matched (resolved) samples before metrics are trustworthy; below this we
# return a clean empty state (samples + nulls) rather than a misleading number.
MIN_CALIBRATION_SAMPLES = 5
# Well-calibrated coverage target (≈80% of realized prices inside the band).
_COVERAGE_TARGET = 80.0
_COVERAGE_TOLERANCE = 10.0  # ±10 → [70, 90] counts as well-calibrated


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def _num(rec: dict, *keys) -> Optional[float]:
    """First present, finite, parseable value among `keys` (else None)."""
    for k in keys:
        v = rec.get(k)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f):
            continue
        return f
    return None


def _score_records(records: list, outcomes_sorted: list) -> list[dict]:
    """Join one symbol's forecast records to realized closes → per-record scores.

    `records`         — rows as returned by ForecastStore.query_forecast_records
                        (ascending by _time), or synthetic dicts in tests.
    `outcomes_sorted` — sorted [(date, close), ...] from query_price_outcomes.

    For each record matched to an actual close, emits a dict with the optional keys
    inside_band / inside_range / signed_error / direction_correct / naive_correct
    (present only when the underlying fields are valid). Unmatched records are
    dropped. `prev` for the naive baseline is taken from an explicit `prev_price`
    field, else reconstructed from the previous record's last_price (same symbol).
    """
    scored: list[dict] = []
    prev_last: Optional[float] = None

    for rec in records:
        pred_time = rec.get("_time")
        last_price = _num(rec, "last_price")
        # Reconstruct the naive baseline's prior close before any skips so the
        # persistence chain stays aligned with the record order.
        prev_price = _num(rec, "prev_price")
        if prev_price is None:
            prev_price = prev_last
        if last_price is not None and last_price > 0:
            prev_last = last_price

        if pred_time is None or last_price is None or last_price <= 0:
            continue
        try:
            pred_date = pred_time.date()
        except AttributeError:
            # Allow a plain date object too (synthetic records).
            pred_date = pred_time if hasattr(pred_time, "year") else None
        if pred_date is None:
            continue

        # Earliest realized close strictly after the forecast date.
        actual = None
        for d, close in outcomes_sorted:
            if d > pred_date and close > 0:
                actual = float(close)
                break
        if actual is None:
            continue  # unresolved — not a sample yet

        entry: dict = {}
        actual_dir = _sign(actual - last_price)

        # ── Band coverage (high/low 48h range) ──────────────────────────────
        low = _num(rec, "low", "e_d1_low")
        high = _num(rec, "high", "e_d1_high")
        if low is not None and high is not None and low > 0 and high >= low:
            entry["inside_range"] = bool(low <= actual <= high)
            # P10/P90 default to the persisted range when not explicitly supplied.
            p10 = _num(rec, "p10")
            p90 = _num(rec, "p90")
            p10 = low if p10 is None else p10
            p90 = high if p90 is None else p90
            if p10 > 0 and p90 >= p10:
                entry["inside_band"] = bool(p10 <= actual <= p90)

        # ── Directional + bias (ensemble d1 median) ─────────────────────────
        p50 = _num(rec, "p50", "e_d1")
        if p50 is not None and p50 > 0:
            entry["signed_error"] = p50 - actual
            entry["direction_correct"] = _sign(p50 - last_price) == actual_dir

        # ── Naive persistence baseline ──────────────────────────────────────
        if prev_price is not None and prev_price > 0:
            entry["naive_correct"] = _sign(last_price - prev_price) == actual_dir

        scored.append(entry)

    return scored


def _verdict(coverage: Optional[float]) -> Optional[str]:
    if coverage is None:
        return None
    if coverage > _COVERAGE_TARGET + _COVERAGE_TOLERANCE:
        return "underconfident"   # bands too wide — realized price almost always inside
    if coverage < _COVERAGE_TARGET - _COVERAGE_TOLERANCE:
        return "overconfident"    # bands too tight — realized price often escapes
    return "well_calibrated"


def _pct(hits: int, total: int) -> Optional[float]:
    return round(100.0 * hits / total, 1) if total else None


def _aggregate(scored: list[dict]) -> dict:
    """Collapse per-record scores into the calibration report payload."""
    samples = len(scored)

    empty = {
        "samples":                  samples,
        "p10_p90_coverage_pct":     None,
        "range_coverage_pct":       None,
        "directional_accuracy_pct": None,
        "naive_accuracy_pct":       None,
        "edge_pct":                 None,
        "mean_signed_error":        None,
        "calibration_verdict":      None,
        "coverage_target_pct":      _COVERAGE_TARGET,
    }
    if samples < MIN_CALIBRATION_SAMPLES:
        return empty

    band_hits = band_n = range_hits = range_n = 0
    dir_hits = dir_n = naive_hits = naive_n = 0
    signed_errors: list[float] = []

    for e in scored:
        if "inside_band" in e:
            band_n += 1
            band_hits += int(e["inside_band"])
        if "inside_range" in e:
            range_n += 1
            range_hits += int(e["inside_range"])
        if "direction_correct" in e:
            dir_n += 1
            dir_hits += int(e["direction_correct"])
        if "naive_correct" in e:
            naive_n += 1
            naive_hits += int(e["naive_correct"])
        if "signed_error" in e:
            signed_errors.append(e["signed_error"])

    p10_p90_coverage = _pct(band_hits, band_n)
    range_coverage = _pct(range_hits, range_n)
    directional = _pct(dir_hits, dir_n)
    naive = _pct(naive_hits, naive_n)
    edge = round(directional - naive, 1) if directional is not None and naive is not None else None
    mean_signed_error = round(sum(signed_errors) / len(signed_errors), 4) if signed_errors else None

    # Verdict keys off the P10–P90 band when available, else the 48h range.
    verdict = _verdict(p10_p90_coverage if p10_p90_coverage is not None else range_coverage)

    return {
        "samples":                  samples,
        "p10_p90_coverage_pct":     p10_p90_coverage,
        "range_coverage_pct":       range_coverage,
        "directional_accuracy_pct": directional,
        "naive_accuracy_pct":       naive,
        "edge_pct":                 edge,
        "mean_signed_error":        mean_signed_error,
        "calibration_verdict":      verdict,
        "coverage_target_pct":      _COVERAGE_TARGET,
    }


def _compute_calibration(records: list, outcomes: dict) -> dict:
    """Single-symbol pure transform (records + {date: close}) → report dict."""
    return _aggregate(_score_records(records, sorted(outcomes.items())))


async def compute_calibration(symbol: Optional[str]) -> dict:
    """Coverage + directional edge + bias for `symbol`.

    `symbol=None` or "ALL" aggregates across every symbol with forecast history.
    Thin history (< MIN_CALIBRATION_SAMPLES matched samples) → samples + nulls,
    never a 404 (mirrors the analytics.py empty-state convention).
    """
    is_all = symbol is None or symbol.strip().upper() == "ALL"

    if is_all:
        symbols = await asyncio.to_thread(forecast_store.query_forecast_symbols, _LOOKBACK_DAYS)
    else:
        symbols = [symbol]

    # Fan out per-symbol reads with bounded concurrency so the "ALL" aggregate
    # doesn't serialize 2×N blocking queries into the router's 12s timeout.
    semaphore = asyncio.Semaphore(8)

    async def _fetch_symbol(sym: str) -> list[dict]:
        async with semaphore:
            records, outcomes = await asyncio.gather(
                asyncio.to_thread(forecast_store.query_forecast_records, sym, _LOOKBACK_DAYS),
                asyncio.to_thread(forecast_store.query_price_outcomes, sym, _LOOKBACK_DAYS + 10),
            )
        return _score_records(records, sorted(outcomes.items()))

    batches = await asyncio.gather(*(_fetch_symbol(sym) for sym in symbols))
    scored = [entry for batch in batches for entry in batch]

    return _aggregate(scored)
