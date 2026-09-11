# Plain standalone container for the yeast panoptic service (no Nuclio).
#
# The model repo (detectron2 code) is cloned in below, so it's baked into
# the image and PANOPTIC_REPO_PATH already points at it by default. Only
# the fine-tuned checkpoint/config -- machine-specific, not in that repo --
# still needs to be mounted at runtime (normally handled by
# docker-compose.yml at the repo root instead of this by hand):
#
#   docker build -t yeastpanoptic-panoptic panoptic_service
#   docker run -p 8200:8200 \
#     -v /path/to/oneformer_output:/model_dir:ro \
#     -e PANOPTIC_MODEL_DIR=/model_dir \
#     yeastpanoptic-panoptic
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir 'git+https://github.com/cocodataset/panopticapi.git'

RUN git clone --depth 1 https://github.com/wanlanli/PytrochDeepyeast.git /model_repo
ENV PANOPTIC_REPO_PATH=/model_repo

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
