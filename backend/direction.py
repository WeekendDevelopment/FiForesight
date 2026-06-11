# backend/direction.py
"""
Next-day direction classifier — estimates the probability that tomorrow's close
will be higher (or lower) than today's.

Fits a lightweight RandomForestClassifier on-the-fly using the same indicator
history that /predict already computes (RSI, BB, MACD, volume).  No serialised
model, no external state.  Returns None when there is insufficient data.
"""
import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_MIN_SAMPLES = 60       # minimum labeled bars before we produce an estimate
_RSI_WINDOW  = 5        # bars for RSI slope
_MACD_WINDOW = 3        # bars for MACD slope


def _safe_div(a: float, b: float, fallback: float = 0.0) -> float:
    return a / b if b != 0 else fallback


def _build_direction_dataset(
    closes: list,
    rsi_series: list,
    bb_upper: list,
    bb_lower: list,
    macd_hist: list,
    volumes: list,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build (X, y) where y=1 if close[i+1] > close[i] else 0.

    Features (10, all dimensionless):
      0  rsi         – RSI value (0-100)
      1  rsi_vs_50   – RSI centered on 50
      2  bb_pct_b    – (close − lower) / (upper − lower), clamped [0,1]
      3  macd_hist   – MACD histogram value
      4  macd_slope  – change in MACD hist over last 3 bars / bar
      5  rsi_slope   – change in RSI over last 5 bars / bar
      6  ret_1d      – 1-day price return
      7  ret_5d      – 5-day price return
      8  ret_10d     – 10-day price return
      9  vol_ratio   – current_vol / 5d_average_vol

    Label:
      1  if close[i+1] > close[i]
      0  otherwise
    """
    n = len(closes)
    rows, labels = [], []

    for i in range(10, n - 1):
        c   = float(closes[i])
        rsi = rsi_series[i]
        bbu = bb_upper[i]
        bbl = bb_lower[i]
        mh  = macd_hist[i]
        vol = float(volumes[i]) if volumes else 1.0

        if None in (rsi, bbu, bbl, mh):
            continue

        bb_pct_b = float(max(0.0, min(1.0, _safe_div(
            c - float(bbl), float(bbu) - float(bbl), 0.5
        ))))

        rsi_vals  = [rsi_series[j] for j in range(i - _RSI_WINDOW, i + 1) if rsi_series[j] is not None]
        rsi_slope = _safe_div(rsi_vals[-1] - rsi_vals[0], len(rsi_vals)) if len(rsi_vals) >= 2 else 0.0

        mh_vals    = [macd_hist[j] for j in range(max(0, i - _MACD_WINDOW + 1), i + 1) if macd_hist[j] is not None]
        macd_slope = _safe_div(mh_vals[-1] - mh_vals[0], len(mh_vals)) if len(mh_vals) >= 2 else 0.0

        c1  = float(closes[i - 1])
        c5  = float(closes[max(0, i - 5)])
        c10 = float(closes[max(0, i - 10)])
        ret_1d  = _safe_div(c - c1, c1)
        ret_5d  = _safe_div(c - c5, c5)
        ret_10d = _safe_div(c - c10, c10)

        vol5      = [float(volumes[j]) for j in range(max(0, i - 5), i + 1) if float(volumes[j]) > 0]
        avg_vol   = sum(vol5) / len(vol5) if vol5 else 1.0
        vol_ratio = _safe_div(vol, avg_vol, 1.0)

        rows.append([
            float(rsi), float(rsi) - 50.0, bb_pct_b,
            float(mh), macd_slope, rsi_slope,
            ret_1d, ret_5d, ret_10d, vol_ratio,
        ])
        labels.append(1 if float(closes[i + 1]) > c else 0)

    return np.array(rows, dtype=np.float32), np.array(labels, dtype=np.int8)


def compute_direction_forecast(
    closes: list,
    rsi_series: list,
    bb_upper: list,
    bb_lower: list,
    macd_hist: list,
    volumes: list,
) -> Optional[dict]:
    """
    Fit a RandomForestClassifier and return the next-day direction prediction.

    Returns a dict:
      direction      – "up" | "down"
      confidence_pct – int 50-100 (predicted-class probability × 100)
      edge_pct       – int, confidence_pct − 50 (edge above coin-flip baseline)
      top_features   – list[str] top-3 model-level signals with current-bar values
      trained_on     – int, number of training samples

    Returns None when there is insufficient data or sklearn is unavailable.
    """
    try:
        from sklearn.ensemble import RandomForestClassifier  # type: ignore
    except ImportError:
        logger.warning("[DIRECTION] scikit-learn not available — skipping")
        return None

    X, y = _build_direction_dataset(closes, rsi_series, bb_upper, bb_lower, macd_hist, volumes)

    if len(X) < _MIN_SAMPLES:
        logger.info("[DIRECTION] Too few samples (%d < %d) — skipping", len(X), _MIN_SAMPLES)
        return None

    n_up   = int(y.sum())
    n_down = len(y) - n_up
    if n_up < 10 or n_down < 10:
        logger.info("[DIRECTION] Class imbalance too severe (up=%d, down=%d) — skipping", n_up, n_down)
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
        logger.warning("[DIRECTION] Training failed: %s", exc)
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
        logger.info("[DIRECTION] Current bar missing indicators — skipping")
        return None

    bb_pct_b = float(max(0.0, min(1.0, _safe_div(
        c - float(bbl), float(bbu) - float(bbl), 0.5
    ))))

    rsi_vals  = [rsi_series[j] for j in range(max(0, i - _RSI_WINDOW), i + 1) if rsi_series[j] is not None]
    rsi_slope = _safe_div(rsi_vals[-1] - rsi_vals[0], len(rsi_vals)) if len(rsi_vals) >= 2 else 0.0

    mh_vals    = [macd_hist[j] for j in range(max(0, i - _MACD_WINDOW + 1), i + 1) if macd_hist[j] is not None]
    macd_slope = _safe_div(mh_vals[-1] - mh_vals[0], len(mh_vals)) if len(mh_vals) >= 2 else 0.0

    c1  = float(closes[max(0, i - 1)])
    c5  = float(closes[max(0, i - 5)])
    c10 = float(closes[max(0, i - 10)])
    ret_1d  = _safe_div(c - c1, c1)
    ret_5d  = _safe_div(c - c5, c5)
    ret_10d = _safe_div(c - c10, c10)

    vol5      = [float(volumes[j]) for j in range(max(0, i - 5), i + 1) if float(volumes[j]) > 0]
    avg_vol   = sum(vol5) / len(vol5) if vol5 else 1.0
    vol_ratio = _safe_div(vol, avg_vol, 1.0)

    x_cur = np.array(
        [[float(rsi), float(rsi) - 50.0, bb_pct_b, float(mh), macd_slope, rsi_slope,
          ret_1d, ret_5d, ret_10d, vol_ratio]],
        dtype=np.float32,
    )

    try:
        proba = clf.predict_proba(x_cur)[0]   # [p_down, p_up] when classes=[0,1]
    except Exception as exc:
        logger.warning("[DIRECTION] Prediction failed: %s", exc)
        return None

    # clf.classes_ may be [0,1] or [1] if only one class survived training
    classes = list(clf.classes_)
    p_up   = float(proba[classes.index(1)]) if 1 in classes else 0.5
    p_down = float(proba[classes.index(0)]) if 0 in classes else 0.5

    direction    = "up" if p_up >= p_down else "down"
    confidence   = round(max(p_up, p_down) * 100)
    edge         = confidence - 50

    # ── Top-3 model-level signals ─────────────────────────────────────────────
    feature_names = [
        "RSI", "RSI vs 50", "BB %B", "MACD hist", "MACD slope",
        "RSI slope", "Ret 1d", "Ret 5d", "Ret 10d", "Vol ratio",
    ]
    top_idx  = np.argsort(clf.feature_importances_)[::-1][:3]
    cur_vals = [float(rsi), float(rsi) - 50.0, bb_pct_b, float(mh), macd_slope,
                rsi_slope, ret_1d, ret_5d, ret_10d, vol_ratio]
    top_features = []
    for idx in top_idx:
        val  = cur_vals[idx]
        name = feature_names[idx]
        if name == "RSI":
            tag = " — overbought" if val > 70 else " — oversold" if val < 30 else ""
            top_features.append(f"RSI {val:.0f}{tag}")
        elif name == "RSI vs 50":
            top_features.append(f"RSI {'above' if val >= 0 else 'below'} midpoint ({val:+.1f})")
        elif name == "BB %B":
            tag = " — near upper band" if val > 0.8 else " — near lower band" if val < 0.2 else ""
            top_features.append(f"BB position {val * 100:.0f}%{tag}")
        elif name == "MACD hist":
            tag = " — decelerating" if macd_slope < 0 else ""
            top_features.append(f"MACD histogram {val:+.4f}{tag}")
        elif name == "MACD slope":
            top_features.append(f"MACD momentum {'weakening' if val < 0 else 'building'}")
        elif name == "RSI slope":
            top_features.append(f"RSI {'falling' if val < 0 else 'rising'}")
        elif name in ("Ret 1d", "Ret 5d", "Ret 10d"):
            period = name.split()[1]
            top_features.append(f"{period} return {val * 100:+.1f}%")
        elif name == "Vol ratio":
            top_features.append(f"Volume {val:.1f}× 5d avg")

    logger.info(
        "[DIRECTION] %s %.0f%% confidence (+%d%% edge) | n=%d up=%d down=%d | %s",
        direction.upper(), confidence, edge, len(X), n_up, n_down,
        " | ".join(top_features[:2]),
    )

    return {
        "direction":      direction,
        "confidence_pct": confidence,
        "edge_pct":       edge,
        "top_features":   top_features,
        "trained_on":     len(X),
    }
