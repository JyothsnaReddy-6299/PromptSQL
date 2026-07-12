# --- Stage 1: Build Frontend ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Build Backend & Final Image ---
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend application
COPY backend/ ./backend

# Copy built frontend assets to the backend distribution path
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Expose port (FastAPI will bind to $PORT)
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Command to launch the app
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}
