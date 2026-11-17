FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 APP_ENV=production

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://localhost:5000/api/v1/health')" || exit 1

# One worker: APScheduler runs in-process, so extra workers would double-run jobs.
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "60", "--access-logfile", "-"]
