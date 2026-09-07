# Plain standalone container for the yeast panoptic service (no Nuclio).
#
# The model repo and checkpoint/config are NOT baked into this image --
# they're large and/or private. Mount them at runtime and point
# PANOPTIC_REPO_PATH/PANOPTIC_MODEL_DIR at them (normally handled by
# docker-compose.yml at the repo root instead of this by hand):
#
#   docker build -t yeastpanoptic-panoptic panoptic_service
#   docker run -p 8200:8200 \
#     -v /path/to/PytrochDeepyeast:/model_repo:ro \
#     -v /path/to/oneformer_output:/model_dir:ro \
#     -e PANOPTIC_REPO_PATH=/model_repo -e PANOPTIC_MODEL_DIR=/model_dir \
#     yeastpanoptic-panoptic
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir 'git+https://github.com/cocodataset/panopticapi.git'

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
