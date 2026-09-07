# Backend API. Stays torch-free (SAM/panoptic live in their own containers)
# but does need a C/C++ compiler for CellMate's Cython extension (built
# once at container-startup time against THIS image's Python -- see
# docker-entrypoint.sh -- not baked into the image, since CellMate itself
# is mounted in from the host, not part of this repo).
#
# Build: docker build -t yeastpanoptic-backend backend
# (normally built/run via docker-compose.yml instead -- see repo root)
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt Cython

COPY . .
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
