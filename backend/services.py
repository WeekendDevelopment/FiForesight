import re
import logging
import httpx
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from config import Config

logger = logging.getLogger(__name__)

class InfluxService:
    def __init__(self):
        self.client = InfluxDBClient(url=Config.INFLUXDB_URL, token=Config.INFLUXDB_TOKEN, org=Config.INFLUXDB_ORG)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    def write_price(self, symbol: str, price: float):
        try:
            p = Point("market_data").tag("symbol", symbol).field("close", float(price))
            p.time(datetime.now(timezone.utc), WritePrecision.NS)
            self.write_api.write(bucket=Config.INFLUXDB_BUCKET, org=Config.INFLUXDB_ORG, record=p)
        except Exception as e:
            logger.error(f"InfluxDB Write Error: {e}")

    def query_history(self, symbol: str) -> list:
        query = f'from(bucket: "{Config.INFLUXDB_BUCKET}") |> range(start: -100d) |> filter(fn: (r) => r["_measurement"] == "market_data" and r["symbol"] == "{symbol}") |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value") |> sort(columns: ["_time"], desc: false)'
        try:
            tables = self.query_api.query(query)
            return [r.values for t in tables for r in t.records]
        except Exception as e:
            logger.error(f"InfluxDB Query Error: {e}")
            return []

class SerpService:
    @staticmethod
    def clean_price(price_str):
        if price_str is None: return 0.0
        if isinstance(price_str, (int, float)): return float(price_str)
        cleaned = re.sub(r'[^\d.-]', '', str(price_str))
        try: return float(cleaned)
        except ValueError: return 0.0

    async def fetch_data(self, query: str) -> dict:
        async with httpx.AsyncClient(timeout=25.0) as client:
            params = {"engine": "google_finance", "q": query, "api_key": Config.SERP_API_KEY}
            resp = await client.get("https://serpapi.com/search.json", params=params)
            return resp.json() if resp.status_code == 200 else {}
