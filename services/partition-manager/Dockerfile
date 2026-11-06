# Build from the REPO ROOT (so the image can see contracts/):
#   docker build -f services/partition-manager/Dockerfile -t partition-manager .
FROM python:3.12-slim

WORKDIR /app
COPY services/partition-manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Turn the shared .proto contracts into Python code inside the image
COPY contracts ./contracts
COPY tools/gen_protos.py ./tools/gen_protos.py
RUN python tools/gen_protos.py gen

COPY services/partition-manager/ring.py services/partition-manager/membership.py \
     services/partition-manager/server.py services/partition-manager/pmctl.py ./

ENV GRPC_PORT=50051 METRICS_PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 50051 8000
CMD ["python", "server.py"]
