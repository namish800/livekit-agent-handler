FROM python:3.12-slim

WORKDIR /app

# Install system deps (if any LiveKit binary deps are required, add here)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# ---------- deps layer ----------
COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose default port
EXPOSE 8000

# Start the FastAPI server with Uvicorn
CMD ["uvicorn", "api_service:app", "--host", "0.0.0.0", "--port", "8000"] 