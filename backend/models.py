# backend/models.py  # noqa
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import newrelic.agent

# Suppress Prophet's "Importing plotly failed" warning — we don't use Prophet's
# built-in plot() / plot_components() methods; all charting is done by Recharts.
logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("prophet.plot").setLevel(logging.ERROR)

MODELS_AVAILABLE = False
try:
    from statsmodels.tsa.statespace.sarimax import SARIMAX
    from prophet import Prophet
    from sklearn.ensemble import RandomForestRegressor
    MODELS_AVAILABLE = True
    logging.getLogger(__name__).info(
        "[MODELS] ✓ All ML packages loaded — "
        "statsmodels (SARIMAX), prophet (Prophet), scikit-learn (RandomForestRegressor)"
    )
except ImportError as _import_err:
    logging.getLogger(__name__).warning(
        f"[MODELS] ✗ ML package import failed — models unavailable: {_import_err}. "
        "Run: pip install statsmodels prophet scikit-learn"
    )

logger = logging.getLogger(__name__)

FORECAST_DAYS = 5


# ---------------------------------------------------------------------------
# Technical Indicators  (close-based — correct by definition for RSI/MACD/BB/SMA)
# ---------------------------------------------------------------------------
@newrelic.agent.function_trace()
def calculate_macd(
    prices: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Dict:
    """Returns per-point MACD line, signal line, and histogram lists."""
    logger.info(
        f"[MACD] calculate_macd — input: {len(prices)} prices | "
        f"params: fast_ema={fast}, slow_ema={slow}, signal_ema={signal}"
    )
    series      = pd.Series(prices)
    ema_fast    = series.ewm(span=fast,   adjust=False).mean()
    ema_slow    = series.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line
    result = {
        "macd":   [round(v, 4) if not np.isnan(v) else None for v in macd_line],
        "signal": [round(v, 4) if not np.isnan(v) else None for v in signal_line],
        "hist":   [round(v, 4) if not np.isnan(v) else None for v in histogram],
    }
    last_macd   = next((v for v in reversed(result["macd"])   if v is not None), None)
    last_signal = next((v for v in reversed(result["signal"]) if v is not None), None)
    last_hist   = next((v for v in reversed(result["hist"])   if v is not None), None)
    label = (
        "Bullish" if last_macd is not None and last_signal is not None and last_macd > last_signal
        else "Bearish" if last_macd is not None and last_signal is not None
        else "N/A"
    )
    logger.info(
        f"[MACD] ✓ complete — latest: MACD={last_macd}, signal={last_signal}, "
        f"hist={last_hist} ({label})"
    )
    return result

@newrelic.agent.function_trace()
def calculate_bollinger_bands(
    prices: List[float],
    window: int = 20,
    num_std: float = 2.0,
) -> Dict:
    """Returns per-point upper, middle, lower Bollinger Band lists."""
    logger.info(
        f"[BB] calculate_bollinger_bands — input: {len(prices)} prices | "
        f"params: window={window}, num_std={num_std}"
    )
    series = pd.Series(prices)
    middle = series.rolling(window=window).mean()
    std    = series.rolling(window=window).std()
    upper  = middle + num_std * std
    lower  = middle - num_std * std

    def _clean(s):
        return [round(v, 4) if not np.isnan(v) else None for v in s]

    result = {"upper": _clean(upper), "middle": _clean(middle), "lower": _clean(lower)}
    last_upper  = next((v for v in reversed(result["upper"])  if v is not None), None)
    last_middle = next((v for v in reversed(result["middle"]) if v is not None), None)
    last_lower  = next((v for v in reversed(result["lower"])  if v is not None), None)
    logger.info(
        f"[BB] ✓ complete — latest bands: upper={last_upper}, mid={last_middle}, lower={last_lower}"
    )
    return result

@newrelic.agent.function_trace()
def calculate_sma_series(prices: List[float], period: int) -> List:
    """Returns SMA array for given period, None where insufficient data."""
    logger.info(
        f"[SMA{period}] calculate_sma_series — input: {len(prices)} prices, period={period}"
    )
    series = pd.Series(prices)
    sma    = series.rolling(window=period).mean()
    result = [round(v, 4) if not np.isnan(v) else None for v in sma]
    last_val = next((v for v in reversed(result) if v is not None), None)
    logger.info(f"[SMA{period}] ✓ complete — latest SMA{period}={last_val}")
    return result

@newrelic.agent.function_trace()
def calculate_rsi_series(prices: List[float], periods: int = 14) -> List:
    """
    Returns full RSI series (same length as prices), None where insufficient data.
    Uses EWM (Wilder smoothing: alpha = 1/periods, equivalent to com = periods-1).
    """
    logger.info(
        f"[RSI] calculate_rsi_series — input: {len(prices)} prices, periods={periods}"
    )
    series = pd.Series(prices)
    delta  = series.diff()
    gain   = delta.where(delta > 0, 0).ewm(com=periods - 1, min_periods=periods).mean()
    loss   = (-delta.where(delta < 0, 0)).ewm(com=periods - 1, min_periods=periods).mean()
    loss   = loss.replace(0, 1e-9)
    rsi    = 100 - (100 / (1 + gain / loss))
    result = [round(float(v), 2) if not pd.isna(v) else None for v in rsi]
    last_rsi = next((v for v in reversed(result) if v is not None), None)
    logger.info(f"[RSI] ✓ rsi_series complete — latest RSI={last_rsi}")
    return result

@newrelic.agent.function_trace()
def calculate_rsi(prices: List[float], periods: int = 14) -> float:
    """
    Scalar RSI using EWM (Wilder smoothing) — identical method to calculate_rsi_series
    so both functions return consistent values for the same input.

    FIX: was previously using simple rolling mean (different algorithm → 7pt divergence
    vs the EWM series used for charting).  Both now use ewm(com=periods-1).
    """
    logger.info(
        f"[RSI] calculate_rsi (scalar) — input: {len(prices)} prices, periods={periods}"
    )
    if len(prices) < periods + 1:
        logger.warning(
            f"[RSI] Insufficient data ({len(prices)} rows < {periods + 1} required) — "
            f"returning neutral 50.0"
        )
        return 50.0
    series = pd.Series(prices)
    delta  = series.diff()
    gain   = delta.where(delta > 0, 0).ewm(com=periods - 1, min_periods=periods).mean()
    loss   = (-delta.where(delta < 0, 0)).ewm(com=periods - 1, min_periods=periods).mean()
    g      = gain.iloc[-1]
    ls     = loss.iloc[-1]
    if pd.isna(g) or pd.isna(ls):
        logger.warning("[RSI] NaN in gain/loss — returning neutral 50.0")
        return 50.0
    if g == 0 and ls == 0:
        logger.info("[RSI] Flat price (zero gain and zero loss) — returning neutral 50.0")
        return 50.0
    if ls == 0:
        logger.info("[RSI] No losses recorded — returning 100.0 (pure uptrend)")
        return 100.0
    rsi_val = float(100 - (100 / (1 + g / ls)))
    logger.info(f"[RSI] ✓ RSI={rsi_val:.2f} (ewm_gain={g:.4f}, ewm_loss={ls:.4f})")
    return rsi_val

@newrelic.agent.function_trace()
def calculate_support_resistance(
    closes: List[float],
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    lookback: int = 65,
    window: int = 5,
    cluster_tol_pct: float = 1.5,
    max_levels: int = 3,
) -> Dict:
    """
    Identifies key support and resistance levels from recent price history.

    FIX: now uses actual intraday Highs for resistance candidates and intraday
    Lows for support candidates when OHLCV data is available. Previously used
    closing prices for both, which misses real support/resistance since those
    form at intraday extremes, not closes.

    Falls back to close-based detection if highs/lows are not supplied.
    """
    using_ohlcv = (
        highs is not None
        and lows is not None
        and len(highs) == len(closes)
        and len(lows) == len(closes)
    )
    logger.info(
        f"[S/R] calculate_support_resistance — input: {len(closes)} closes | "
        f"ohlcv_mode={'YES — using High for resistance, Low for support' if using_ohlcv else 'NO — close-based fallback'} | "
        f"params: lookback={lookback}, window={window}, "
        f"cluster_tol={cluster_tol_pct}%, max_levels={max_levels}"
    )

    if len(closes) < window * 2 + 2:
        logger.warning(
            f"[S/R] Insufficient data ({len(closes)} rows < {window * 2 + 2} required) — "
            f"returning empty support/resistance"
        )
        return {"support": [], "resistance": []}

    # Use intraday lows for support, highs for resistance when available
    support_src    = np.array((lows  if using_ohlcv else closes)[-lookback:])
    resistance_src = np.array((highs if using_ohlcv else closes)[-lookback:])
    close_arr      = np.array(closes[-lookback:])

    supports:    List[float] = []
    resistances: List[float] = []

    for i in range(window, len(close_arr) - window):
        sup_neighbourhood = support_src[i - window: i + window + 1]
        res_neighbourhood = resistance_src[i - window: i + window + 1]
        if support_src[i]    == sup_neighbourhood.min():
            supports.append(float(support_src[i]))
        if resistance_src[i] == res_neighbourhood.max():
            resistances.append(float(resistance_src[i]))

    logger.info(
        f"[S/R] Raw local extrema — {len(supports)} support candidates "
        f"({'from lows' if using_ohlcv else 'from closes'}), "
        f"{len(resistances)} resistance candidates "
        f"({'from highs' if using_ohlcv else 'from closes'})"
    )

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
    last_price        = closes[-1]

    support_levels = sorted(
        [s for s in support_levels    if s < last_price],
        key=lambda x: abs(x - last_price),
    )[:max_levels]
    resistance_levels = sorted(
        [r for r in resistance_levels if r > last_price],
        key=lambda x: abs(x - last_price),
    )[:max_levels]

    logger.info(
        f"[S/R] ✓ complete — last_close=${last_price:.2f} | "
        f"support={support_levels} | resistance={resistance_levels}"
    )
    return {"support": support_levels, "resistance": resistance_levels}

@newrelic.agent.function_trace()
def calculate_model_stats(prices: List[float]) -> Dict:
    """
    Returns a dict of descriptive statistics used both in the response
    and as context for the AI analysis layer later.
    """
    logger.debug(f"[STATS] calculate_model_stats — input: {len(prices)} prices")
    arr     = np.array(prices)
    returns = np.diff(arr) / arr[:-1]

    ann_vol     = float(np.std(returns) * np.sqrt(252)) if len(returns) > 1 else 0.0
    window_arr  = arr[-20:] if len(arr) >= 20 else arr
    x           = np.arange(len(window_arr))
    slope, _    = np.polyfit(x, window_arr, 1)
    trend_slope = float(slope)
    sma20       = float(np.mean(arr[-20:])) if len(arr) >= 20 else float(np.mean(arr))
    last        = float(arr[-1])
    sma_pct     = ((last - sma20) / sma20 * 100) if sma20 > 0 else 0.0

    stats = {
        "ann_volatility_pct": round(ann_vol * 100, 2),
        "trend_slope":        round(trend_slope, 4),
        "sma_20":             round(sma20, 2),
        "price_vs_sma20_pct": round(sma_pct, 2),
    }
    logger.info(
        f"[STATS] ✓ ann_volatility={stats['ann_volatility_pct']:.2f}% | "
        f"trend_slope={stats['trend_slope']:+.4f}/day | "
        f"SMA20=${stats['sma_20']:.2f} | "
        f"price_vs_SMA20={stats['price_vs_sma20_pct']:+.2f}%"
    )
    return stats


# ---------------------------------------------------------------------------
# Per-model forecast helpers
# ---------------------------------------------------------------------------

def _prophet_forecast(
    prices: List[float],
    steps: int,
    volumes: Optional[List[float]] = None,
    hl_ranges: Optional[List[float]] = None,
) -> np.ndarray:
    """
    Prophet univariate forecast on closing prices.
    When volumes and hl_ranges (intraday High-Low / Close ratio) are supplied,
    they are added as additional regressors so Prophet can incorporate volume
    context and intraday volatility into the trend decomposition.
    Future regressor values are estimated as the mean of the last 5 known days.
    """
    use_regressors = (
        volumes   is not None and len(volumes)   == len(prices) and
        hl_ranges is not None and len(hl_ranges) == len(prices)
    )
    logger.debug(
        f"[PROPHET] Fitting — training_rows={len(prices)}, forecast_steps={steps} | "
        f"config: changepoint_prior_scale=0.05, weekly_seasonality=True, "
        f"daily_seasonality=False, interval_width=0.80 | "
        f"extra_regressors={'volume_log + hl_range' if use_regressors else 'none (closes only)'}"
    )
    logger.debug(
        f"[PROPHET] Input price range: ${min(prices):.2f} – ${max(prices):.2f} | "
        f"last_close=${prices[-1]:.2f}"
    )

    # Snap end to last business day to guarantee len(ds) == len(prices)
    end = pd.Timestamp.now().normalize()
    if end.day_of_week >= 5:
        end = end - pd.tseries.offsets.BDay(1)

    df = pd.DataFrame({
        "ds": pd.date_range(end=end, periods=len(prices), freq="B"),
        "y":  prices,
    })

    if use_regressors:
        # Log-scale volume — reduces magnitude spread (e.g. 1M → 13.8)
        vol_arr = np.array(volumes, dtype=float)
        vol_arr = np.where(vol_arr <= 0, np.nan, vol_arr)
        vol_fill = np.nanmean(vol_arr) if not np.all(np.isnan(vol_arr)) else 1.0
        vol_arr = np.where(np.isnan(vol_arr), vol_fill, vol_arr)
        df["volume_log"] = np.log1p(vol_arr)
        df["hl_range"]   = hl_ranges
        logger.debug(
            f"[PROPHET] Regressors — volume_log: mean={df['volume_log'].mean():.3f}, "
            f"std={df['volume_log'].std():.3f} | "
            f"hl_range: mean={df['hl_range'].mean():.4f}, "
            f"std={df['hl_range'].std():.4f}"
        )

    m = Prophet(
        daily_seasonality=False,
        weekly_seasonality=True,
        changepoint_prior_scale=0.05,
        interval_width=0.80,
    )
    if use_regressors:
        m.add_regressor("volume_log")
        m.add_regressor("hl_range")
    m.fit(df)

    future = m.make_future_dataframe(periods=steps, freq="B")
    if use_regressors:
        # Estimate future regressor values from mean of last 5 known days
        vol_future = float(df["volume_log"].iloc[-5:].mean())
        hlr_future = float(df["hl_range"].iloc[-5:].mean())
        future["volume_log"] = vol_future
        future["hl_range"]   = hlr_future
        logger.debug(
            f"[PROPHET] Future regressor estimates (mean of last 5d) — "
            f"volume_log={vol_future:.3f}, hl_range={hlr_future:.4f}"
        )

    fc     = m.predict(future).tail(steps)
    result = fc[["yhat", "yhat_lower", "yhat_upper"]].values   # shape (steps, 3)

    logger.info(
        f"[PROPHET] ✓ Forecast complete — "
        f"Day-1: predicted=${result[0, 0]:.2f} [{result[0, 1]:.2f}–{result[0, 2]:.2f}] | "
        f"Day-{steps}: predicted=${result[-1, 0]:.2f} [{result[-1, 1]:.2f}–{result[-1, 2]:.2f}]"
    )
    return result


def _sarima_forecast(
    prices: List[float],
    steps: int,
    volumes: Optional[List[float]] = None,
    hl_ranges: Optional[List[float]] = None,
) -> np.ndarray:
    """
    SARIMAX(1,1,1) on closing prices.
    When volumes and hl_ranges are available they are passed as exogenous variables
    (the X in SARIMAX), giving the model additional context for each timestep.
    Volume is z-score normalised to prevent it dominating the coefficient scale.
    Future exog values are approximated as the mean of the last 5 training days.
    """
    use_exog = (
        volumes   is not None and len(volumes)   == len(prices) and
        hl_ranges is not None and len(hl_ranges) == len(prices)
    )
    logger.debug(
        f"[SARIMA] Fitting — training_rows={len(prices)}, forecast_steps={steps} | "
        f"order=(p=1, d=1, q=1), enforce_stationarity=False, enforce_invertibility=False | "
        f"exog={'volume_zscore + hl_range' if use_exog else 'none (closes only)'}"
    )
    logger.debug(
        f"[SARIMA] Input price range: ${min(prices):.2f} – ${max(prices):.2f} | "
        f"last_close=${prices[-1]:.2f}"
    )

    exog        = None
    exog_future = None

    if use_exog:
        vol_arr  = np.array(volumes,   dtype=float)
        hl_arr   = np.array(hl_ranges, dtype=float)

        # Z-score normalise volume so it's on the same scale as hl_range
        vol_mean = vol_arr.mean()
        vol_std  = vol_arr.std() + 1e-8
        vol_norm = (vol_arr - vol_mean) / vol_std

        exog = np.column_stack([vol_norm, hl_arr])

        # Future exog: mean of last 5 trading days
        future_row  = exog[-5:].mean(axis=0)
        exog_future = np.tile(future_row, (steps, 1))

        logger.debug(
            f"[SARIMA] Exog training — vol_zscore: mean≈0 std=1 (normalised) | "
            f"hl_range: mean={hl_arr.mean():.4f}, std={hl_arr.std():.4f} | "
            f"exog_future (mean of last 5d): vol_z={future_row[0]:.4f}, "
            f"hl_range={future_row[1]:.4f}"
        )

    model  = SARIMAX(prices, exog=exog, order=(1, 1, 1),
                     enforce_stationarity=False, enforce_invertibility=False)
    fit    = model.fit(disp=False)
    fc     = fit.get_forecast(steps=steps, exog=exog_future)

    mean_raw = fc.predicted_mean
    mean     = mean_raw.values if hasattr(mean_raw, "values") else np.asarray(mean_raw)
    ci_raw   = fc.conf_int(alpha=0.20)
    ci       = ci_raw.values if hasattr(ci_raw, "values") else np.asarray(ci_raw)
    result   = np.column_stack([mean, ci[:, 0], ci[:, 1]])   # shape (steps, 3)

    logger.info(
        f"[SARIMA] ✓ Forecast complete — "
        f"Day-1: predicted=${result[0, 0]:.2f} CI(80%)=[{result[0, 1]:.2f}–{result[0, 2]:.2f}] | "
        f"Day-{steps}: predicted=${result[-1, 0]:.2f} CI(80%)=[{result[-1, 1]:.2f}–{result[-1, 2]:.2f}]"
    )
    return result


def _rf_forecast(
    prices: List[float],
    steps: int,
    opens: Optional[List[float]] = None,
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    volumes: Optional[List[float]] = None,
) -> np.ndarray:
    """
    Random Forest on a sliding window of past observations.

    OHLCV mode (when all four arrays are supplied):
      Feature matrix = last `window` rows × 5 columns (O, H, L, C, V).
      Each column is independently z-score normalised before training and
      prediction so that volume (millions) doesn't dominate Close (hundreds).
      Window roll during multi-step prediction carries forward the last known
      Open/High/Low/Volume while updating only the Close with each prediction.

    Closes-only mode (fallback):
      Feature matrix = last `window` close prices — same as before.

    Band estimation: historical 20-day coefficient of variation × 1.5.
    """
    window    = 10
    use_ohlcv = all(
        v is not None and len(v) == len(prices)
        for v in [opens, highs, lows, volumes]
    )
    logger.debug(
        f"[RF] Preparing — input_prices={len(prices)}, forecast_steps={steps}, "
        f"feature_window={window} | "
        f"mode={'OHLCV (5 cols × {window} steps = {5*window} features)' if use_ohlcv else f'closes-only ({window} features)'}"
    )

    if len(prices) < window + 1:
        logger.warning(
            f"[RF] Insufficient training data ({len(prices)} rows < {window + 1} required) — "
            f"returning flat estimate at last_price=${prices[-1]:.2f}"
        )
        last = prices[-1]
        return np.column_stack([
            np.full(steps, last),
            np.full(steps, last),
            np.full(steps, last),
        ])

    vol = np.std(prices[-20:]) / np.mean(prices[-20:]) if len(prices) >= 20 else 0.02

    if use_ohlcv:
        logger.debug(
            f"[RF] Input price range: ${min(prices):.2f} – ${max(prices):.2f} | "
            f"last_close=${prices[-1]:.2f} | "
            f"vol range: ${min(volumes):.0f} – ${max(volumes):.0f}"
        )
        # Stack into (n, 5): Open, High, Low, Close, Volume
        raw  = np.column_stack([
            np.array(opens,   dtype=float),
            np.array(highs,   dtype=float),
            np.array(lows,    dtype=float),
            np.array(prices,  dtype=float),
            np.array(volumes, dtype=float),
        ])
        # Column-wise z-score normalisation
        col_means = raw.mean(axis=0)
        col_stds  = raw.std(axis=0) + 1e-8
        norm      = (raw - col_means) / col_stds

        logger.debug(
            f"[RF] OHLCV normalisation (z-score per column) — "
            f"col_means: O={col_means[0]:.2f}, H={col_means[1]:.2f}, "
            f"L={col_means[2]:.2f}, C={col_means[3]:.2f}, V={col_means[4]:.0f}"
        )

        X, y = [], []
        for i in range(len(prices) - window):
            X.append(norm[i: i + window].flatten())   # 10 × 5 = 50 features
            y.append(prices[i + window])
        X, y = np.array(X), np.array(y)

        logger.debug(
            f"[RF] Training — samples={len(X)}, features_per_sample={X.shape[1]}, "
            f"n_estimators=100, random_state=42 | hist_vol(20d)={vol:.4f}, band_mult=1.5"
        )
        rf = RandomForestRegressor(n_estimators=100, random_state=42)
        rf.fit(X, y)

        preds           = []
        last_window_raw = raw[-window:].copy()   # shape (window, 5)
        for step_i in range(steps):
            window_norm = ((last_window_raw - col_means) / col_stds).flatten()
            p           = float(rf.predict([window_norm])[0])
            preds.append(p)
            # Roll: shift window up, copy last row, update only Close (col 3)
            new_row    = last_window_raw[-1].copy()
            new_row[3] = p
            last_window_raw = np.vstack([last_window_raw[1:], new_row])
            logger.debug(
                f"[RF] Step {step_i + 1}/{steps} (OHLCV) — predicted=${p:.2f} | "
                f"carried: open=${new_row[0]:.2f}, high=${new_row[1]:.2f}, "
                f"low=${new_row[2]:.2f}, vol={new_row[4]:.0f}"
            )
    else:
        logger.debug(
            f"[RF] Input price range: ${min(prices):.2f} – ${max(prices):.2f} | "
            f"last_close=${prices[-1]:.2f}"
        )
        X, y = [], []
        for i in range(len(prices) - window):
            X.append(prices[i: i + window])
            y.append(prices[i + window])
        X, y = np.array(X), np.array(y)

        logger.debug(
            f"[RF] Training — samples={len(X)}, features_per_sample={window} (closes only), "
            f"n_estimators=100, random_state=42 | hist_vol(20d)={vol:.4f}, band_mult=1.5"
        )
        rf = RandomForestRegressor(n_estimators=100, random_state=42)
        rf.fit(X, y)

        preds       = []
        last_window = list(prices[-window:])
        for step_i in range(steps):
            p = float(rf.predict([last_window])[0])
            preds.append(p)
            last_window = last_window[1:] + [p]
            logger.debug(f"[RF] Step {step_i + 1}/{steps} (closes) — predicted=${p:.2f}")

    preds  = np.array(preds)
    band   = preds * vol * 1.5
    result = np.column_stack([preds, preds - band, preds + band])

    logger.info(
        f"[RF] ✓ Forecast complete — "
        f"Day-1: predicted=${result[0, 0]:.2f} band=[{result[0, 1]:.2f}–{result[0, 2]:.2f}] | "
        f"Day-{steps}: predicted=${result[-1, 0]:.2f} band=[{result[-1, 1]:.2f}–{result[-1, 2]:.2f}]"
    )
    return result


# ---------------------------------------------------------------------------
# Monte Carlo GBM simulation
# ---------------------------------------------------------------------------

def run_monte_carlo(
    closes: List[float],
    steps: int = 5,
    n_sims: int = 1000,
) -> Optional[Dict]:
    """
    Geometric Brownian Motion Monte Carlo price path simulation.

    S_t = S_0 × exp((μ - σ²/2)×t + σ×√t×Z),  Z ~ N(0,1)

    μ and σ are estimated from daily log-returns of closes.
    Uses np.random.default_rng(seed=42) for reproducibility.
    Returns None gracefully when fewer than 10 price points are available.
    """
    if len(closes) < 10:
        logger.warning(
            f"[MC] Insufficient data ({len(closes)} closes < 10 minimum) — returning None"
        )
        return None
    try:
        arr         = np.array(closes, dtype=float)
        log_returns = np.diff(np.log(arr))
        mu          = float(np.mean(log_returns))
        sigma       = float(np.std(log_returns))
        S0          = float(arr[-1])

        rng = np.random.default_rng(seed=42)
        Z   = rng.standard_normal((n_sims, steps))
        t   = np.arange(1, steps + 1, dtype=float)

        # Closed-form GBM: log-price at step t relative to S_0
        drift      = mu - 0.5 * sigma ** 2
        log_paths  = drift * t[np.newaxis, :] + sigma * np.sqrt(t)[np.newaxis, :] * Z
        paths      = S0 * np.exp(log_paths)   # shape (n_sims, steps)

        final     = paths[:, -1]
        p10       = float(np.percentile(final, 10))
        p50       = float(np.percentile(final, 50))
        p90       = float(np.percentile(final, 90))
        prob_gain = float(np.mean(final > S0) * 100)
        var_95    = float(S0 - np.percentile(final, 5))

        # 50 representative paths for the 2D fan chart
        sample_idx   = rng.choice(n_sims, size=min(50, n_sims), replace=False)
        paths_sample = [
            [round(float(paths[i, j]), 4) for j in range(steps)]
            for i in sample_idx
        ]

        # Per-day percentile surface (used by both fan chart and 3D surface)
        price_range_by_day = []
        for d in range(steps):
            dp = paths[:, d]
            price_range_by_day.append({
                "day": d + 1,
                "p10": round(float(np.percentile(dp, 10)), 4),
                "p25": round(float(np.percentile(dp, 25)), 4),
                "p50": round(float(np.percentile(dp, 50)), 4),
                "p75": round(float(np.percentile(dp, 75)), 4),
                "p90": round(float(np.percentile(dp, 90)), 4),
            })

        logger.info(
            f"[MC] ✓ n_sims={n_sims}, steps={steps} | "
            f"S0=${S0:.2f} → p10=${p10:.2f}, p50=${p50:.2f}, p90=${p90:.2f} | "
            f"prob_gain={prob_gain:.1f}%, VaR95=${var_95:.2f}"
        )
        return {
            "p10":               round(p10,       4),
            "p50":               round(p50,       4),
            "p90":               round(p90,       4),
            "prob_gain":         round(prob_gain, 2),
            "var_95":            round(var_95,    4),
            "paths_sample":      paths_sample,
            "price_range_by_day": price_range_by_day,
            "n_sims":            n_sims,
        }
    except Exception as exc:
        logger.warning(f"[MC] run_monte_carlo failed: {exc} — returning None")
        return None


# ---------------------------------------------------------------------------
# Main ensemble entry point
# ---------------------------------------------------------------------------

def run_ensemble_forecast(
    closes: List[float],
    symbol: str,
    opens: Optional[List[float]] = None,
    highs: Optional[List[float]] = None,
    lows: Optional[List[float]] = None,
    volumes: Optional[List[float]] = None,
    historical_weights: Optional[List[float]] = None,
    sample_count: int = 0,
    ensemble_mae: Optional[Dict] = None,
) -> Dict:
    """
    Ensemble of Prophet + SARIMAX + RandomForest forecasting closing price.

    Now accepts full OHLCV arrays. Each model uses what it can:
      - Prophet:  close (target) + volume_log + hl_range as regressors
      - SARIMAX:  close (endogenous) + volume_zscore + hl_range as exog
      - RF:       full OHLCV feature matrix (50 features) or close-only fallback

    FIX: horizon_factor now correctly widens the *distance from predicted*,
    not the absolute dollar value. Old formula multiplied the price by 1.20
    on day 5, producing absurd ±20% bands for stable stocks.

    Returns:
        forecast_days : list of FORECAST_DAYS dicts
        high          : overall 5-day high
        low           : overall 5-day low
        note          : analyst narrative
        conf          : 'high' | 'medium' | 'low'
        stats         : descriptive statistics dict
    """
    logger.info(f"[ENSEMBLE] ══════════ Starting forecast for {symbol} ══════════")

    last_price = float(closes[-1]) if closes else 100.0
    vol        = np.std(closes[-10:]) / np.mean(closes[-10:]) if len(closes) >= 10 else 0.02
    stats      = calculate_model_stats(closes) if len(closes) >= 5 else {}
    mc_result  = run_monte_carlo(closes, steps=FORECAST_DAYS)

    ohlcv_available = all(
        v is not None and len(v) == len(closes)
        for v in [opens, highs, lows, volumes]
    )
    logger.debug(
        f"[ENSEMBLE] Input — price_points={len(closes)}, last_price=${last_price:.2f}, "
        f"vol(10d)={vol:.4f} ({vol * 100:.2f}%), MODELS_AVAILABLE={MODELS_AVAILABLE}, "
        f"ohlcv_supplied={ohlcv_available}"
    )
    logger.debug(
        f"[ENSEMBLE] Closes sent to models — closes[0]=${closes[0]:.2f} ... "
        f"closes[-10]={', '.join(f'${p:.2f}' for p in closes[-10:])}"
    )
    if ohlcv_available:
        logger.debug(
            f"[ENSEMBLE] OHLCV context — "
            f"last_open=${opens[-1]:.2f}, last_high=${highs[-1]:.2f}, "
            f"last_low=${lows[-1]:.2f}, last_vol={volumes[-1]:.0f}"
        )

    # ── Compute HL range (intraday vol proxy) ─────────────────────────────────
    hl_ranges: Optional[List[float]] = None
    if ohlcv_available:
        hl_ranges = [
            (h - lo) / c if c > 0 else 0.0
            for h, lo, c in zip(highs, lows, closes)
        ]
        logger.debug(
            f"[ENSEMBLE] HL range (intraday vol proxy = (H-L)/C) — "
            f"mean={float(np.mean(hl_ranges)):.4f}, "
            f"last={hl_ranges[-1]:.4f}"
        )

    # ── Fallback: models unavailable or insufficient data ────────────────────
    if not MODELS_AVAILABLE or len(closes) < 20:
        reason = (
            "ML packages not installed (statsmodels/prophet/scikit-learn)"
            if not MODELS_AVAILABLE
            else f"insufficient price history ({len(closes)} rows < 20 minimum)"
        )
        logger.warning(
            f"[ENSEMBLE] ⚠ FALLBACK ACTIVE — {reason} | "
            f"using volatility-only estimate (vol={vol:.4f})"
        )
        days = []
        for i in range(1, FORECAST_DAYS + 1):
            dt        = datetime.now(timezone.utc) + timedelta(days=i)
            predicted = round(last_price * (1 + (vol * 0.3 * (1 if i % 2 == 0 else -0.5))), 2)
            days.append({
                "date":           dt.strftime("%m/%d"),
                "predicted":      predicted,
                "high":           round(predicted * (1 + vol), 2),
                "low":            round(predicted * (1 - vol), 2),
                "confidence_pct": 30,
            })
        overall_high = max(d["high"] for d in days)
        overall_low  = min(d["low"]  for d in days)
        logger.info(
            f"[ENSEMBLE] Fallback result — "
            f"5d high=${overall_high:.2f}, 5d low=${overall_low:.2f}, conf=low"
        )
        return {
            "forecast_days": days, "high": overall_high, "low": overall_low,
            "note": "Insufficient history for full model run — using volatility estimate.",
            "conf": "low", "stats": stats,
            "weights":       {"prophet": 0.0, "sarima": 0.0, "rf": 0.0},
            "per_model_d1":  {"prophet": None, "sarima": None, "rf": None},
            "monte_carlo":   mc_result,
        }

    logger.debug(
        f"[ENSEMBLE] Fallback path SKIPPED — "
        f"MODELS_AVAILABLE=True, price_points={len(closes)} ≥ 20"
    )

    # ── Run all three models concurrently ────────────────────────────────────
    p_fc = s_fc = r_fc = None
    errors: List[str] = []

    logger.info("[ENSEMBLE] Running Prophet + SARIMAX + RF concurrently ...")

    def _run_prophet():
        return _prophet_forecast(closes, FORECAST_DAYS, volumes=volumes, hl_ranges=hl_ranges)

    def _run_sarima():
        return _sarima_forecast(closes, FORECAST_DAYS, volumes=volumes, hl_ranges=hl_ranges)

    def _run_rf():
        return _rf_forecast(closes, FORECAST_DAYS, opens=opens, highs=highs, lows=lows, volumes=volumes)

    model_fns = [
        ("Prophet", _run_prophet),
        ("SARIMA",  _run_sarima),
        ("RF",      _run_rf),
    ]

    with ThreadPoolExecutor(max_workers=3) as pool:
        future_map = {pool.submit(fn): name for name, fn in model_fns}
        results = {}
        for fut in as_completed(future_map):
            name = future_map[fut]
            try:
                results[name] = fut.result()
                logger.info(f"[{name}] ✓ complete")
            except Exception as e:
                results[name] = None
                errors.append(f"{name}: {e}")
                logger.warning(f"[{name}] ✗ FAILED: {e} — weight=0.0 in ensemble")

    p_fc = results.get("Prophet")
    s_fc = results.get("SARIMA")
    r_fc = results.get("RF")

    available = [fc for fc in [p_fc, s_fc, r_fc] if fc is not None]
    n_success = len(available)
    logger.info(
        f"[ENSEMBLE] Model run summary — {n_success}/3 succeeded | "
        f"Prophet={'✓' if p_fc is not None else '✗'}, "
        f"SARIMA={'✓' if s_fc is not None else '✗'}, "
        f"RF={'✓' if r_fc is not None else '✗'}"
        + (f" | failures: {errors}" if errors else "")
    )

    # ── Emergency fallback if ALL models failed ───────────────────────────────
    if not available:
        logger.error(
            f"[ENSEMBLE] ✗ ALL 3 MODELS FAILED for {symbol} — "
            f"emergency volatility fallback triggered | errors: {errors}"
        )
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
            "high":          max(d["high"] for d in days),
            "low":           min(d["low"]  for d in days),
            "note":          f"Model errors: {'; '.join(errors)}. Using fallback estimate.",
            "conf":          "low", "stats": stats,
            "weights":       {"prophet": 0.0, "sarima": 0.0, "rf": 0.0},
            "per_model_d1":  {"prophet": None, "sarima": None, "rf": None},
            "monte_carlo":   mc_result,
        }

    # ── Dynamic weights: inverse day-1 error (realtime) ──────────────────────
    raw_weights = []
    for fc in [p_fc, s_fc, r_fc]:
        if fc is None:
            raw_weights.append(0.0)
        else:
            err = abs(fc[0, 0] - last_price)
            raw_weights.append(1.0 / (err + 1e-6))

    rt_total    = sum(raw_weights)
    realtime_w  = [rw / rt_total if rt_total > 0 else 0.0 for rw in raw_weights]

    # ── Blend with historical accuracy weights (RL feedback) ─────────────────
    # α ramps 0→0.7 over the first 10 resolved samples.
    # historical_weights are derived from inverse per-model MAE stored in InfluxDB.
    if (
        historical_weights is not None
        and len(historical_weights) == 3
        and sample_count > 0
    ):
        alpha   = min(0.7, sample_count / 10.0 * 0.7)
        blended = [
            alpha * hw + (1.0 - alpha) * rw
            for hw, rw in zip(historical_weights, realtime_w)
        ]
        # Zero out any model that failed (keep realtime zero respected)
        blended = [b if rt > 0 else 0.0 for b, rt in zip(blended, realtime_w)]
        b_total = sum(blended)
        w       = [b / b_total if b_total > 0 else 0.0 for b in blended]
        logger.info(
            f"[ENSEMBLE] RL weight blending — α={alpha:.2f} ({sample_count} samples) | "
            f"historical: {[f'{v:.3f}' for v in historical_weights]} | "
            f"realtime:   {[f'{v:.3f}' for v in realtime_w]} | "
            f"blended:    {[f'{v:.3f}' for v in w]}"
        )
    else:
        w = realtime_w
        logger.info(
            "[ENSEMBLE] Realtime inverse-error weighting — "
            "w = 1/(|day1_pred - last_price| + 1e-6), normalised"
            + (" | RL blending SKIPPED (no historical samples yet)" if not historical_weights else "")
        )

    for label, fc, wi, rw in zip(
        ["Prophet", "SARIMA ", "RF     "], [p_fc, s_fc, r_fc], w, raw_weights
    ):
        if fc is not None:
            err = abs(fc[0, 0] - last_price)
            logger.debug(
                f"[ENSEMBLE]   {label}: day1_pred=${fc[0, 0]:.2f}, "
                f"err_vs_last={err:.4f}, raw_w={rw:.6f}, final_w={wi:.4f} ({wi:.1%})"
            )
        else:
            logger.debug(f"[ENSEMBLE]   {label}: FAILED → raw_w=0.000000, final_w=0.0000 (0.0%)")

    # ── Build per-day weighted forecast ──────────────────────────────────────
    days = []
    for i in range(FORECAST_DAYS):
        predicted = high_sum = low_sum = w_used = 0.0

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

        # ── FIX: widen the DISTANCE from predicted, not the absolute price ──
        # Old: day_high = max(high_sum, predicted) * horizon_factor  ← wrong
        #      multiplied a $310 price by 1.20 → $372, an absurd +20% absolute
        # New: day_high = predicted + (raw_high - predicted) * horizon_factor
        #      widens only the band width by 5% per extra day
        horizon_factor = 1 + i * 0.05
        raw_high = max(high_sum, predicted)
        raw_low  = min(low_sum,  predicted)
        day_high = round(predicted + (raw_high - predicted) * horizon_factor, 2)
        day_low  = round(predicted - (predicted - raw_low)  * horizon_factor, 2)

        n_models  = len(available)
        horizon_key = f"ensemble_d{i + 1}"
        hor_data    = (ensemble_mae or {}).get(horizon_key, {})
        hor_mae     = hor_data.get("mae", 0.0)
        hor_samples = hor_data.get("samples", 0)
        if hor_samples > 0 and hor_mae > 0 and predicted > 0:
            # MAE as % of current price — lower = more accurate = higher confidence.
            # 1% error → ~91% conf, 3% → ~73%, 5% → ~55%, 10% → ~10% (floor).
            mae_pct  = (hor_mae / predicted) * 100
            conf_pct = max(10, min(95, round(95 - mae_pct * 8.5)))
        else:
            # No historical data yet — use heuristic, improves automatically over time
            base_conf = 40 + (len(closes) // 10) + (n_models * 10)
            conf_pct  = max(10, min(90, base_conf - i * 5))

        dt = datetime.now(timezone.utc) + timedelta(days=i + 1)
        days.append({
            "date":           dt.strftime("%m/%d"),
            "predicted":      round(predicted, 2),
            "high":           day_high,
            "low":            day_low,
            "confidence_pct": conf_pct,
        })

    # ── Log 5-day forecast table ──────────────────────────────────────────────
    logger.info(f"[ENSEMBLE] 5-day forecast table ({symbol}):")
    logger.info(f"[ENSEMBLE]   {'Day':<4}  {'Date':<6}  {'Predicted':>10}  {'High':>10}  {'Low':>10}  {'Conf%':>6}  {'Band±':>8}")
    logger.info(f"[ENSEMBLE]   {'───':<4}  {'──────':<6}  {'─────────':>10}  {'────':>10}  {'───':>10}  {'─────':>6}  {'──────':>8}")
    for i, d in enumerate(days):
        band_size = (d["high"] - d["low"]) / 2
        logger.info(
            f"[ENSEMBLE]   {i+1:<4}  {d['date']:<6}  "
            f"${d['predicted']:>9.2f}  ${d['high']:>9.2f}  ${d['low']:>9.2f}  "
            f"{d['confidence_pct']:>5}%  ±${band_size:>6.2f}"
        )

    # ── Analyst narrative ─────────────────────────────────────────────────────
    d1         = days[0]["predicted"]
    d5         = days[-1]["predicted"]
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
    # Derive top-level confidence from the mean of per-horizon conf_pct values.
    # When MAE data exists these are calibrated; otherwise they use the heuristic.
    avg_conf_pct = sum(d["confidence_pct"] for d in days) / len(days) if days else 50
    conf_label   = "high" if avg_conf_pct >= 70 else "medium" if avg_conf_pct >= 45 else "low"

    logger.info(
        f"[ENSEMBLE] ✓ Result — "
        f"5d high=${overall_high:.2f}, 5d low=${overall_low:.2f} | "
        f"direction={direction} ({pct_change:.2f}%) | "
        f"conf={conf_label} (avg={avg_conf_pct:.0f}%) | models_used={len(available)}/3 | "
        f"ohlcv_used={ohlcv_available}"
    )
    logger.info(f"[ENSEMBLE] ══════════ Forecast for {symbol} done ══════════")

    return {
        "forecast_days": days,
        "high":          overall_high,
        "low":           overall_low,
        "note":          note,
        "conf":          conf_label,
        "stats":         stats,
        "weights":       {"prophet": w[0], "sarima": w[1], "rf": w[2]},
        "per_model_d1":  {
            "prophet": float(p_fc[0, 0]) if p_fc is not None else None,
            "sarima":  float(s_fc[0, 0]) if s_fc is not None else None,
            "rf":      float(r_fc[0, 0]) if r_fc is not None else None,
        },
        "monte_carlo":   mc_result,
    }
