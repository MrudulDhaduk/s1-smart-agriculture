# Build from the REPO ROOT (so the image can see contracts/):
#   docker build -f services/sensor-store/Dockerfile -t sensor-store .
FROM python:3.12-slim

WORKDIR /app
COPY services/sensor-store/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Turn the shared .proto contracts into Python code inside the image
COPY contracts ./contracts
COPY tools/gen_protos.py ./tools/gen_protos.py
RUN python tools/gen_protos.py gen

COPY services/sensor-store/server.py .

ENV DATA_DIR=/data GRPC_PORT=50052 METRICS_PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 50052 8000
CMD ["python", "server.py"]
