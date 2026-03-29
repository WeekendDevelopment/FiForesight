# --- Multi-stage build ---

# 1. Frontend Build Stage
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# Build frontend with standalone output for better Docker performance
ENV NEXT_PRIVATE_STANDALONE=true
RUN pnpm build --no-lint

# 2. Final Runtime Stage
# Using Python 3.11 slim as the base because backend has complex compiled dependencies
FROM python:3.11-slim
WORKDIR /app

# Install Node.js in the Python environment (Alpine is too hard for pandas/numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install pnpm
RUN npm install -g pnpm@10.33.0

# Install Backend dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy root config
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --prod --frozen-lockfile

# Copy build artifacts and source code
COPY --from=frontend-builder /app/frontend/.next/standalone ./frontend/
COPY --from=frontend-builder /app/frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend/public
COPY backend/ ./backend/

# Expose only the frontend port (3000)
# Backend will run on 8000 but be unreachable from outside
EXPOSE 3000

# Start script
# We start both but only expose the port for the frontend
CMD ["pnpm", "run", "app:start"]
