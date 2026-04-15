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
    args = parser.parse_args()

    path = "/predict" if args.direct else "/api/predict"
    endpoint = f"{args.url.rstrip('/')}{path}"
    total = len(TICKERS)

    print(f"Daily training — {total} tickers -> {endpoint}")
    print(f"Timeout: {args.timeout}s | Delay: {args.delay}s between tickers\n")

    success = 0
    failed = 0
    errors: list[str] = []

    for i, ticker in enumerate(TICKERS, 1):
        print(f"[{i:>2}/{total}] {ticker:<6} ... ", end="", flush=True)
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
                print(f"${price}  forecast=[{forecast_low}-{forecast_high}]  conf={conf}")
                success += 1
            else:
                msg = resp.text[:80] if resp.text else "no body"
                print(f"HTTP {resp.status_code}: {msg}")
                failed += 1
                errors.append(f"{ticker}: HTTP {resp.status_code}")
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1
            errors.append(f"{ticker}: {e}")

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
