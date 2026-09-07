# SAM point-prompt service

A small standalone HTTP service: POST an image and one or more clicked
points (include/exclude), get back a polygon. Kept separate from `backend/`
so torch/segment-anything don't have to live in the main API process — the
backend calls this over HTTP
(`backend/app/services/segmentation/http_model.py`) once `SAM_SERVICE_URL`
is set.

## Run

```
cd sam_service
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --port 8100
```

Uses the local checkpoint at `/home/wlli/Data/sam_model/sam_vit_h_4b8939.pth` by
default (see Config below) -- run `python3 scripts/download_checkpoint.py
vit_b` first if you'd rather use a smaller/faster model and don't have one
locally.

Then point the backend at it: `SAM_SERVICE_URL=http://localhost:8100 uvicorn app.main:app --reload --port 8000` (from `backend/`).

## Swapping in a different checkpoint

Set `SAM_CHECKPOINT_PATH` (and `SAM_MODEL_TYPE` to match its architecture:
`vit_b` / `vit_l` / `vit_h` -- the checkpoint filename conventionally says
which). Defaults to the official `vit_h` checkpoint at
`/home/wlli/Data/sam_model/sam_vit_h_4b8939.pth` -- the largest/most
accurate SAM variant, at the cost of a slower first click per frame (~25s
on CPU for the image encoder; cached afterwards, so repeat clicks on the
same frame are fast -- see `_ensure_image_embedded` in `model_handler.py`).

## Endpoints

- `GET /health` — `{"status": "ok"}` once the model has loaded.
- `POST /predict-point` — multipart form: `image` (file), `points` (JSON
  string: `[{"x": float, "y": float, "label": 0|1}, ...]`, image pixel
  coordinates, label 1 = include/foreground, 0 = exclude/background).
  Returns `{"polygons": [[[x, y], ...], ...]}`.

## Config (env vars)

- `SAM_CHECKPOINT_PATH` — default `/home/wlli/Data/sam_model/sam_vit_h_4b8939.pth`
- `SAM_MODEL_TYPE` — `vit_h` (default) / `vit_b` / `vit_l`
- `SAM_DEVICE` — auto-detected (`cuda` if available, else `cpu`) unless set explicitly
