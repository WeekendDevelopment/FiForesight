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

# Final production image
FROM node:25-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    make \
    gcc \
    g++

# Install Python and build dependencies
RUN apt install python3 python3-pip python3-venv -y

# This deletes the index — not needed anymore
RUN rm -rf /var/lib/apt/lists/*

# Create a virtual environment for Python to keep it clean and set PATH
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy backend requirements and install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy root package.json and install dependencies
COPY package.json pnpm-lock.yaml ./

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