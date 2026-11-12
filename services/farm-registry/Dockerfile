# Build from the REPO ROOT (so the image can see services/web-common/):
#   docker build -f services/farm-registry/Dockerfile -t s1/farm-registry .
FROM python:3.12-slim

WORKDIR /app
COPY services/farm-registry/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 10 -r requirements.txt

COPY services/web-common/webcommon.py services/farm-registry/app.py ./

ENV PORT=8080 METRICS_PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8080 8000
USER 65534
CMD ["python", "app.py"]
