FROM python:3.13-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Python deps
COPY agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code + analytics data (needed for LOCAL_MODE fallback)
COPY agent/ /app/agent/
COPY analytics/ /app/analytics/
COPY conut_bakery_scaled_data/ /app/conut_bakery_scaled_data/

# Default env
ENV LOCAL_MODE=false
ENV PORT=8000
ENV HOST=0.0.0.0

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["python", "-m", "agent.main"]
