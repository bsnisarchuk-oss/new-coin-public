FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HEALTH_PORT=8080

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    useradd -m -u 1001 botuser && \
    chown -R botuser:botuser /app

USER botuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import json, os, urllib.request; port=os.getenv('HEALTH_PORT', '8080'); data=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=5)); raise SystemExit(0 if data.get('ready') else 1)" || exit 1

CMD ["python", "-m", "app.main"]
