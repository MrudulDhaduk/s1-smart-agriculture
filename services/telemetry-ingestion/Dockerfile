# Build from the repository root so shared proto contracts and web-common are available.
FROM python:3.12-slim

WORKDIR /app
COPY services/telemetry-ingestion/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 10 -r requirements.txt

COPY contracts ./contracts
COPY tools/gen_protos.py ./tools/gen_protos.py
RUN python tools/gen_protos.py gen

COPY services/web-common/webcommon.py services/telemetry-ingestion/app.py ./

ENV PORT=8080 METRICS_PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8080 8000
USER 65534
CMD ["python", "app.py"]
