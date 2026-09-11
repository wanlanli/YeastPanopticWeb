# Backend API. Stays torch-free (SAM/panoptic live in their own
# containers). CellMate is cloned in and its Cython extension built below,
# both at image-build time, against this image's own Python -- so
# CELLMATE_PATH already points at a working checkout by default and there's
# nothing to mount or build at container-startup time.
#
# Build: docker build -t yeastpanoptic-backend backend
# (normally built/run via docker-compose.yml instead -- see repo root)
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt Cython

RUN git clone --depth 1 https://github.com/wanlanli/CellMate.git /cellmate \
    && cd /cellmate/cellmate/image_measure/measure \
    && python3 setup.py build_ext --inplace
ENV CELLMATE_PATH=/cellmate

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
