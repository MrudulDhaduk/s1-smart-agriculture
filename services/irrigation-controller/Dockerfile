# Build from the REPO ROOT (so the image can see contracts/ and services/web-common/):
#   docker build -f services/irrigation-controller/Dockerfile -t s1/irrigation-controller .
FROM python:3.12-slim

WORKDIR /app
COPY services/irrigation-controller/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --default-timeout=120 --retries 10 -r requirements.txt

# Turn the shared .proto contracts into Python code inside the image (Partition Manager client)
COPY contracts ./contracts
COPY tools/gen_protos.py ./tools/gen_protos.py
RUN python tools/gen_protos.py gen

COPY services/web-common/webcommon.py services/irrigation-controller/app.py \
     services/irrigation-controller/controller.py services/irrigation-controller/backends.py ./

ENV PORT=8080 METRICS_PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8080 8000
USER 65534
CMD ["python", "app.py"]
