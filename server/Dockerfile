# /server/Dockerfile (Final, Pre-Baked Model Version)

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Python packages
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- THIS IS THE DEFINITIVE FIX ---
# Pre-download and cache the sentence-transformer model during the build.
# This prevents rate-limiting errors and makes the application start much faster.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
# --- END OF FIX ---

# Copy the rest of the application code
COPY . .

ENV PYTHONUNBUFFERED=1

# The CMD remains the same
CMD bash -c "flask init-db && gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app"