FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system rallyify \
    && useradd --system --gid rallyify --home-dir /app rallyify

COPY --chown=rallyify:rallyify . .

EXPOSE 8000

USER rallyify

CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers \"${GUNICORN_WORKERS:-3}\" --timeout \"${GUNICORN_TIMEOUT_SECONDS:-30}\" --graceful-timeout \"${GUNICORN_GRACEFUL_TIMEOUT_SECONDS:-30}\" --max-requests \"${GUNICORN_MAX_REQUESTS:-1000}\" --max-requests-jitter \"${GUNICORN_MAX_REQUESTS_JITTER:-100}\" --access-logfile - --error-logfile -"]
