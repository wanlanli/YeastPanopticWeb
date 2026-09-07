# Plain standalone container for the yeast panoptic service (no Nuclio).
#
# The model repo (/home/wlli/project/PytrochDeepyeast) is NOT baked into
# this image -- it's large, private, and read-only for this service. Mount
# it at runtime and point PANOPTIC_REPO_PATH/PANOPTIC_CHECKPOINT_PATH at it:
#
#   docker build -t yeastpanoptic-panoptic panoptic_service
#   docker run -p 8200:8200 \
#     -v /home/wlli/project/PytrochDeepyeast:/model_repo:ro \
#     -e PANOPTIC_REPO_PATH=/model_repo \
#     yeastpanoptic-panoptic
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir 'git+https://github.com/cocodataset/panopticapi.git'

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8200"]
