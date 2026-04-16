# Build stage for Frontend
FROM node:25-slim AS frontend-builder
WORKDIR /app/frontend

# Install pnpm
RUN npm install -g pnpm

# Accept NEXT_PUBLIC_APP_ENV as a build argument
ARG NEXT_PUBLIC_APP_ENV
ENV NEXT_PUBLIC_APP_ENV=$NEXT_PUBLIC_APP_ENV

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---- Python deps stage ----
FROM python:3.14-slim AS python-deps
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment for Python to keep it clean and set PATH
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy backend requirements and install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# ---- Final image ----
FROM node:25-slim
WORKDIR /app

# Copy root package.json and install dependencies
COPY package.json pnpm-lock.yaml ./

# Copy Python binary + stdlib from python-deps stage
COPY --from=python-deps /usr/local/bin/python3 /usr/local/bin/python3
COPY --from=python-deps /usr/local/lib/python3.14 /usr/local/lib/python3.14

# Copy venv from python-deps stage
COPY --from=python-deps /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV VIRTUAL_ENV=/opt/venv

# Install pnpm
RUN npm install -g pnpm

# Install dependencies
RUN pnpm install --frozen-lockfile

# Copy backend code
COPY backend/ ./backend/

# Next.js standalone — no node_modules needed
COPY --from=frontend-builder /app/frontend/.next/standalone ./
COPY --from=frontend-builder /app/frontend/.next/static ./frontend/.next/static
COPY --from=frontend-builder /app/frontend/public ./frontend/public

EXPOSE 3000
CMD ["pnpm", "run", "app:start"]