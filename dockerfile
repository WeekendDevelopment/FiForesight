# --- Multi-stage build ---

# 1. Frontend Build Stage
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
# Use npm to install pnpm instead of corepack to avoid intermittent socket errors
RUN npm install -g pnpm@10.33.0
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
# Build frontend with standalone output
ENV NEXT_PRIVATE_STANDALONE=true
RUN pnpm build --no-lint

# 2. Final Runtime Stage
FROM python:3.11-slim
WORKDIR /app

# Install Node.js and system tools
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
# Install root dependencies (concurrently)
RUN pnpm install --prod --frozen-lockfile

# Copy build artifacts
# Standalone Next.js creates its own node_modules inside the standalone folder
# We copy the entire folder into /app/frontend
COPY --from=frontend-builder /app/frontend/.next/standalone ./frontend/
COPY --from=frontend-builder /app/frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend/public
COPY backend/ ./backend/

# Expose only the frontend port
EXPOSE 3000

# Start script
CMD ["pnpm", "run", "app:start"]
