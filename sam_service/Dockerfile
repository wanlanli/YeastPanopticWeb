# Plain standalone container for the SAM point-prompt service (no Nuclio).
# The checkpoint isn't baked into this image -- mount it at runtime and
# point SAM_CHECKPOINT_PATH at it (normally handled by docker-compose.yml
# at the repo root instead of this by hand):
#
#   docker build -t yeastpanoptic-sam sam_service
#   docker run -p 8100:8100 \
#     -v /path/to/sam_vit_h_4b8939.pth:/models/sam_checkpoint.pth:ro \
#     -e SAM_CHECKPOINT_PATH=/models/sam_checkpoint.pth -e SAM_MODEL_TYPE=vit_h \
#     yeastpanoptic-sam
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
