# ── Stage 1: build Vue admin frontend ─────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY admin/frontend/package*.json ./
RUN npm install
COPY admin/frontend/ ./
RUN npm run build

# ── Stage 2: Python runtime + Claude CLI ──────────────────────────────
FROM python:3.11-slim

# System deps + Node.js (for Claude CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g @anthropic-ai/claude-code && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Pre-built admin SPA from stage 1
COPY --from=frontend-builder /build/dist /app/admin/frontend/dist

RUN mkdir -p base data

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8001
