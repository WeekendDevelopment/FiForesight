# backend/reversal.py
"""
Reversal-risk classifier — estimates the probability that the current bar is
a local price peak about to reverse ≥2% down within the next 5 trading days.

Fits a lightweight RandomForestClassifier on-the-fly using the full indicator
history that /predict already computes (RSI, BB, MACD, volume).  No serialised
model, no external state.  Returns None when there is insufficient data.
"""
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_MIN_SAMPLES    = 40     # minimum labeled bars before we produce an estimate
_DROP_THRESHOLD = 0.02   # 2% drop → "peak" label
_HORIZON        = 5      # look-forward window (trading days)
_WINDOW         = 5      # look-back window for slope features


def _safe_div(a: float, b: float, fallback: float = 0.0) -> float:
    return a / b if b != 0 else fallback


def _build_dataset(
    closes: list,
    rsi_series: list,
    bb_upper: list,
    bb_lower: list,
    macd_hist: list,
    volumes: list,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build (X, y) from historical indicator arrays.

    Features (all dimensionless):
      0  rsi            – RSI value (0-100)
      1  bb_pct_b       – (close − lower) / (upper − lower), clamped [0, 1]
      2  macd_hist      – MACD histogram value
      3  macd_slope     – change in MACD hist over last 3 bars / bar
      4  rsi_slope      – change in RSI over last 5 bars / bar
      5  price_mom_5    – 5-day price return
      6  vol_ratio      – current_vol / 5d_average_vol

    Label:
      1  if min(close[i+1 … i+HORIZON]) / close[i] − 1 < −DROP_THRESHOLD
      0  otherwise
    """
    n = len(closes)
    rows, labels = [], []

    for i in range(_WINDOW, n - _HORIZON):
        c   = float(closes[i])
        rsi = rsi_series[i]
        bbu = bb_upper[i]
        bbl = bb_lower[i]
        mh  = macd_hist[i]
        vol = float(volumes[i]) if volumes else 1.0

        if None in (rsi, bbu, bbl, mh):
            continue

        bb_pct_b = float(max(0.0, min(1.0, _safe_div(c - float(bbl), float(bbu) - float(bbl), 0.5))))

        rsi_vals  = [rsi_series[j] for j in range(i - _WINDOW, i + 1) if rsi_series[j] is not None]
        rsi_slope = _safe_div(rsi_vals[-1] - rsi_vals[0], len(rsi_vals)) if len(rsi_vals) >= 2 else 0.0

        mh_vals    = [macd_hist[j] for j in range(max(0, i - 2), i + 1) if macd_hist[j] is not None]
        macd_slope = _safe_div(mh_vals[-1] - mh_vals[0], len(mh_vals)) if len(mh_vals) >= 2 else 0.0

        c5        = float(closes[i - _WINDOW])
        price_mom = _safe_div(c - c5, c5)

        vol5      = [float(volumes[j]) for j in range(i - _WINDOW, i + 1) if float(volumes[j]) > 0]
        avg_vol   = sum(vol5) / len(vol5) if vol5 else 1.0
        vol_ratio = _safe_div(vol, avg_vol, 1.0)

        rows.append([float(rsi), bb_pct_b, float(mh), macd_slope, rsi_slope, price_mom, vol_ratio])

        future = [float(closes[i + k]) for k in range(1, _HORIZON + 1)]
        labels.append(1 if _safe_div(min(future) - c, c) <= -_DROP_THRESHOLD else 0)

    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int8)


def compute_reversal_risk(
    closes: list,
    rsi_series: list,
    bb_upper: list,
    bb_lower: list,
    macd_hist: list,
    volumes: list,
) -> Optional[dict]:
    """
    Fit a RandomForest on historical data and return peak-reversal probability
    for the current (latest) bar.

    Returns a dict:
      risk_pct    – int 0-100
      signal      – "low" | "medium" | "high"
      factors     – list[str] top-3 contributing factor descriptions
      trained_on  – int, number of training samples

    Returns None when there is insufficient data or sklearn is unavailable.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier  # type: ignore
    except ImportError:
        logger.warning("[REVERSAL] scikit-learn not available — skipping")
        return None

    X, y = _build_dataset(closes, rsi_series, bb_upper, bb_lower, macd_hist, volumes)

    if len(X) < _MIN_SAMPLES:
        logger.info("[REVERSAL] Too few samples (%d < %d) — skipping", len(X), _MIN_SAMPLES)
        return None

    n_peaks = int(y.sum())
    if n_peaks < 5 or (len(y) - n_peaks) < 5:
        logger.info("[REVERSAL] Class imbalance too severe (peaks=%d) — skipping", n_peaks)
        return None

    try:
        clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=4,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,
        )
        clf.fit(X, y)
    except Exception as exc:
        logger.warning("[REVERSAL] Training failed: %s", exc)
        return None

    # ── Current-bar features ──────────────────────────────────────────────────
    n = len(closes)
    i = n - 1

    c   = float(closes[i])
    rsi = rsi_series[i]
    bbu = bb_upper[i]
    bbl = bb_lower[i]
    mh  = macd_hist[i]
    vol = float(volumes[i]) if volumes else 1.0

    if None in (rsi, bbu, bbl, mh):
        logger.info("[REVERSAL] Current bar missing indicators — skipping")
        return None

    bb_pct_b = float(max(0.0, min(1.0, _safe_div(c - float(bbl), float(bbu) - float(bbl), 0.5))))

    rsi_vals  = [rsi_series[j] for j in range(max(0, i - _WINDOW), i + 1) if rsi_series[j] is not None]
    rsi_slope = _safe_div(rsi_vals[-1] - rsi_vals[0], len(rsi_vals)) if len(rsi_vals) >= 2 else 0.0

    mh_vals    = [macd_hist[j] for j in range(max(0, i - 2), i + 1) if macd_hist[j] is not None]
    macd_slope = _safe_div(mh_vals[-1] - mh_vals[0], len(mh_vals)) if len(mh_vals) >= 2 else 0.0

    c5        = float(closes[max(0, i - _WINDOW)])
    price_mom = _safe_div(c - c5, c5)

    vol5      = [float(volumes[j]) for j in range(max(0, i - _WINDOW), i + 1) if float(volumes[j]) > 0]
    avg_vol   = sum(vol5) / len(vol5) if vol5 else 1.0
    vol_ratio = _safe_div(vol, avg_vol, 1.0)

    x_cur = np.array(
        [[float(rsi), bb_pct_b, float(mh), macd_slope, rsi_slope, price_mom, vol_ratio]],
        dtype=np.float32,
    )

    try:
        prob_peak = float(clf.predict_proba(x_cur)[0, 1])
    except Exception as exc:
        logger.warning("[REVERSAL] Prediction failed: %s", exc)
        return None

    risk_pct = round(prob_peak * 100)
    signal   = "high" if risk_pct >= 65 else "medium" if risk_pct >= 35 else "low"

    # ── Top-3 model-level signals (feature importances are model-global, not per-sample) ──
    feature_names = ["RSI", "BB %B", "MACD hist", "MACD slope", "RSI slope", "Price 5d", "Vol ratio"]
    top_idx = np.argsort(clf.feature_importances_)[::-1][:3]

    cur_vals = [float(rsi), bb_pct_b, float(mh), macd_slope, rsi_slope, price_mom, vol_ratio]
    top_features = []
    for idx in top_idx:
        val = cur_vals[idx]
        name = feature_names[idx]
        if name == "RSI":
            tag = " — overbought" if val > 70 else " — oversold" if val < 30 else ""
            top_features.append(f"RSI {val:.0f}{tag}")
        elif name == "BB %B":
            tag = " — near upper band" if val > 0.8 else " — near lower band" if val < 0.2 else ""
            top_features.append(f"BB position {val*100:.0f}%{tag}")
        elif name == "MACD hist":
            tag = " — decelerating" if macd_slope < 0 else ""
            top_features.append(f"MACD histogram {val:+.4f}{tag}")
        elif name == "MACD slope":
            top_features.append(f"MACD momentum {'weakening' if val < 0 else 'building'}")
        elif name == "RSI slope":
            top_features.append(f"RSI {'diverging down' if val < -0.5 else 'diverging up' if val > 0.5 else 'flat'}")
        elif name == "Price 5d":
            top_features.append(f"5-day return {val*100:+.1f}%")
        elif name == "Vol ratio":
            top_features.append(f"Volume {val:.1f}× 5d avg")

    logger.info(
        "[REVERSAL] risk=%d%% (%s) | n=%d peaks=%d | %s",
        risk_pct, signal, len(X), n_peaks, " | ".join(top_features[:2]),
    )

    return {
        "risk_pct":    risk_pct,
        "signal":      signal,
        "top_features": top_features,
        "trained_on":  len(X),
    }
