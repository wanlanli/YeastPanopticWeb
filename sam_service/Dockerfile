# Plain standalone container for the SAM point-prompt service (no Nuclio).
# Build: docker build -t yeastpanoptic-sam sam_service
# Run:   docker run -p 8100:8100 -v $(pwd)/sam_service/storage:/app/storage yeastpanoptic-sam
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
