# Dedicated Backend Build for Koyeb/Cloud
# Using Python 3.11 slim (Debian) for maximum compatibility with pandas/numpy
FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source code
COPY backend/ .

# Expose the port (FastAPI default)
EXPOSE 8000

# Start command optimized for cloud environments
# Bind to 0.0.0.0 and use the PORT environment variable provided by the host
CMD ["sh", "-c", "python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
