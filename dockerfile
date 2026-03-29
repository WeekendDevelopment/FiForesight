# Build stage for Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Use corepack for pnpm management
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install
COPY frontend/ ./
RUN pnpm build

# Final production image
FROM node:20-alpine
WORKDIR /app

# Install Python and build dependencies
RUN apk add --no-cache python3 py3-pip

# Create a virtual environment for Python to keep it clean and set PATH
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Copy backend requirements and install
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r ./backend/requirements.txt

# Copy root package.json and install dependencies
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && corepack prepare pnpm@10.33.0 --activate && pnpm install

# Copy backend code
COPY backend/ ./backend/

# Copy frontend build artifacts
COPY --from=frontend-builder /app/frontend/.next /app/frontend/.next
COPY --from=frontend-builder /app/frontend/node_modules /app/frontend/node_modules
COPY --from=frontend-builder /app/frontend/package.json /app/frontend/package.json

# Expose only the frontend port (Next.js defaults to 3000)
EXPOSE 3000

# Start script using pnpm run
CMD ["pnpm", "run", "app:start"]
