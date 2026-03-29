# Build stage for Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Use corepack for pnpm management
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install
COPY frontend/ ./
RUN pnpm build

# Build stage for Backend
FROM python:3.11-slim AS backend-builder
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./

# Final production image
FROM node:20-alpine
WORKDIR /app

# Install Python
RUN apk add --no-cache python3 py3-pip

# Copy root package.json and install dependencies using corepack
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate && pnpm install

# Copy backend
COPY --from=backend-builder /app/backend /app/backend
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn

# Copy frontend build artifacts (Next.js)
COPY --from=frontend-builder /app/frontend/.next /app/frontend/.next
COPY --from=frontend-builder /app/frontend/node_modules /app/frontend/node_modules
COPY --from=frontend-builder /app/frontend/package.json /app/frontend/package.json

# Expose only the frontend port (Next.js defaults to 3000)
EXPOSE 3000

# Start script using pnpm run
CMD ["pnpm", "run", "app:start"]
