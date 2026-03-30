import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
    INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN")
    INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "WeekendDevelopment")
    INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "FiForesightBucket")
    SERP_API_KEY = os.getenv("SERP_API_KEY")
    GOOGLE_GENAI_API_KEY = os.getenv("GOOGLE_GENAI_API_KEY")
    PORT = int(os.getenv("PORT", 8000))
