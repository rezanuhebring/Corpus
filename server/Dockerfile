# /server/Dockerfile

# Use a modern, stable Python version
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies needed for building some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Upgrade pip and copy requirements file
RUN pip install --upgrade pip
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
COPY . .

# Set an environment variable to ensure Flask output is visible
ENV PYTHONUNBUFFERED=1

# Run the database initialization command, then start the Gunicorn server
# This ensures the database is ready before the app starts accepting requests.
CMD bash -c "flask init-db && gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 120 app:app"