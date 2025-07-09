# /server/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install build tools and git (for some pip installs)
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the embedding model to prevent runtime network errors
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

ENV PYTHONUNBUFFERED=1

# The CMD is now handled by docker-compose.yml for each service (web/worker)