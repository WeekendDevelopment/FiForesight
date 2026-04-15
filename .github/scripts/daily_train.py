"""
Daily training — queries /predict for 20 diverse tickers.
Each call writes a forecast_record and resolves past forecasts,
building the RL feedback loop without user intervention.

Usage:
  python .github/scripts/daily_train.py                                # prod
  python .github/scripts/daily_train.py --url http://localhost:3000    # local
  python .github/scripts/daily_train.py --url http://localhost:8000 --direct  # FastAPI direct

Runs automatically via .github/workflows/daily-train.yml (weekdays after market close).
"""

import argparse
import sys
import time

import httpx

# Diverse 20-ticker training set:
#   5 large-cap tech, 2 finance, 2 healthcare, 2 energy,
#   3 consumer, 2 industrial, 2 ETFs, 2 high-volatility
TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",   # tech
    "JPM", "GS",                                  # finance
    "JNJ", "PFE",                                  # healthcare
    "XOM", "CVX",                                  # energy
    "MCD", "KO", "WMT",                           # consumer
    "CAT", "BA",                                   # industrial
    "SPY", "QQQ",                                  # ETFs
    "TSLA", "COIN",                                # volatile
]


def main() -> None:
    parser = argparse.ArgumentParser(description="FiForesight daily RL training")
    parser.add_argument(
        "--url",
        default="https://fiforesight.duckdns.org",
        help="Base URL of the deployed app (default: prod)",
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Hit FastAPI /predict directly instead of Next.js /api/predict proxy",
    )
    parser.add_argument("--timeout", type=int, default=120, help="Per-request timeout (s)")
    parser.add_argument("--delay", type=int, default=5, help="Pause between tickers (s)")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max attempts per ticker before marking as failed",
    )
    args = parser.parse_args()

    # Validate numeric inputs — negative values break time.sleep / httpx timeout.
    if args.timeout <= 0:
        parser.error(f"--timeout must be > 0, got {args.timeout}")
    if args.delay < 0:
        parser.error(f"--delay must be >= 0, got {args.delay}")
    if args.max_retries < 1:
        parser.error(f"--max-retries must be >= 1, got {args.max_retries}")

    path = "/predict" if args.direct else "/api/predict"
    endpoint = f"{args.url.rstrip('/')}{path}"
    total = len(TICKERS)

    print(f"Daily training — {total} tickers -> {endpoint}")
    print(f"Timeout: {args.timeout}s | Delay: {args.delay}s between tickers\n")

    success = 0
    failed = 0
    errors: list[str] = []

    # Retries only apply to transient problems: network/timeout exceptions and
    # 5xx / 429. A non-retriable 4xx (400/401/403/404) fails immediately.
    RETRIABLE_STATUS = {429, 500, 502, 503, 504}

    for i, ticker in enumerate(TICKERS, 1):
        print(f"[{i:>2}/{total}] {ticker:<6} ... ", end="", flush=True)

        last_err: str | None = None
        resolved = False

        for attempt in range(1, args.max_retries + 1):
            try:
                resp = httpx.post(
                    endpoint,
                    json={"data": ticker},
                    timeout=args.timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    price = data.get("currentPrice", "?")
                    conf = data.get("confidence", "?")
                    forecast_high = data.get("prediction", {}).get("highRange", "?")
                    forecast_low = data.get("prediction", {}).get("lowRange", "?")
                    print(
                        f"${price}  forecast=[{forecast_low}-{forecast_high}]  conf={conf}"
                        + (f"  (attempt {attempt})" if attempt > 1 else "")
                    )
                    success += 1
                    resolved = True
                    break
                elif resp.status_code in RETRIABLE_STATUS and attempt < args.max_retries:
                    msg = resp.text[:80] if resp.text else "no body"
                    last_err = f"HTTP {resp.status_code}: {msg}"
                    backoff = 2 ** (attempt - 1)
                    print(f"retry {attempt}/{args.max_retries - 1} after {backoff}s ({resp.status_code}) ... ", end="", flush=True)
                    time.sleep(backoff)
                    continue
                else:
                    # Non-retriable response, or last attempt of a retriable one.
                    msg = resp.text[:80] if resp.text else "no body"
                    print(f"HTTP {resp.status_code}: {msg}")
                    failed += 1
                    errors.append(f"{ticker}: HTTP {resp.status_code}")
                    resolved = True
                    break
            except Exception as e:
                last_err = str(e)
                if attempt < args.max_retries:
                    backoff = 2 ** (attempt - 1)
                    print(f"retry {attempt}/{args.max_retries - 1} after {backoff}s ({e.__class__.__name__}) ... ", end="", flush=True)
                    time.sleep(backoff)
                    continue
                # Final attempt exhausted
                print(f"ERROR after {args.max_retries} attempts: {e}")
                failed += 1
                errors.append(f"{ticker}: {e}")
                resolved = True
                break

        if not resolved:
            # Defensive: should never hit if max_retries >= 1.
            print(f"ERROR after {args.max_retries} attempts: {last_err}")
            failed += 1
            errors.append(f"{ticker}: {last_err}")

        # Pace requests to avoid rate-limiting yfinance / Groq
        if i < total:
            time.sleep(args.delay)

    print(f"\nDone — {success}/{total} succeeded, {failed} failed")
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  - {err}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
