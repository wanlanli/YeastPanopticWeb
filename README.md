# YeastPanopticWeb

Microscopy image annotation and quantification viewer: view image
series/movies (8/16-bit TIFF, PNG, JPEG), edit segmentation masks as
polygons, request a mask from a point-prompt model, navigate frames, and
browse precomputed quantification results (feature table, tracking/lineage
tree, t-SNE).

The app is four services: `backend` (FastAPI), `frontend` (Vite/React),
and two optional segmentation services, each its own process so heavy ML
deps stay out of the main API:

- **Point-prompt (SAM)** — click a cell, get one mask back.
- **Whole-frame auto-segmentation** — one click, every instance in the
  frame back (cell/shmoo/zygote/tetrad/lysis/spore), labeled by class.
  Uses the [PytrochDeepyeast](https://github.com/wanlanli/PytrochDeepyeast)
  model.

Only `backend` + `frontend` are required. Either segmentation service
missing or not configured falls back to a classical-CV placeholder, so the
app always runs — segmentation just gets better once a model is wired up.
Quantification uses [CellMate](https://github.com/wanlanli/CellMate).

## Installation

Pick **Docker** or **conda/venv**. Either way, the two companion repos
above are fetched for you automatically — the only thing you need to add
by hand afterward is the model weights (see "Add the model weights"
below).

### Option 1: Docker

```
git clone https://github.com/wanlanli/YeastPanopticWeb.git && cd YeastPanopticWeb
cp .env.docker.example .env.docker   # add your model-weight paths -- see below
docker compose --env-file .env.docker up -d --build
```

Open `http://<this-server-ip>:5173`. The companion repos are cloned in
automatically while the images build; nothing to fetch by hand.

Logs: `docker compose --env-file .env.docker logs -f [service]`. Stop:
`docker compose --env-file .env.docker down`.

**GPU?** Add the `docker-compose.gpu.yml` override (needs the NVIDIA
Container Toolkit on the host — see the comment at the top of that file):

```
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --env-file .env.docker up -d --build
```

No root to install the Container Toolkit? Use `docker-compose.external-ml.yml`
instead — keeps backend+frontend in Docker and runs the segmentation
services as plain host processes with direct GPU access. See the comment
at the top of that file.

### Option 2: conda or venv

```
git clone https://github.com/wanlanli/YeastPanopticWeb.git && cd YeastPanopticWeb
./scripts/setup_venv_envs.sh
```

That one script clones the companion repos, creates a `.venv` per service,
installs every dependency, builds CellMate's Cython extension, runs
`npm install`, and writes `.env` for you. Then just add the model weights
(below) and:

```
./scripts/run_all.sh
```

No `python3-venv` system package (and no root to install it)? Use
`./scripts/setup_conda_envs.sh` instead — same one-command setup, using
conda envs. Either script is safe to re-run if it fails partway through.

Stop everything with `./scripts/stop_all.sh`. Logs land in `logs/*.log`.

### Add the model weights

The one thing that can't be fetched automatically — these are
machine-specific and too large to check into either repo. Both are
optional: skip either one and the app falls back to a classical-CV
placeholder for that feature instead of crashing.

- **Panoptic model weights** — the fine-tuned checkpoint + its matching
  `config.yaml`, saved together. Copy that directory onto this machine
  (e.g. `rsync -avP`) and set `PANOPTIC_MODEL_DIR` (`.env`) /
  `PANOPTIC_MODEL_DIR_HOST` (`.env.docker`) to it.
- **SAM checkpoint** — either copy an existing one and set
  `SAM_CHECKPOINT_PATH` / `SAM_CHECKPOINT_HOST`, or fetch the public
  official weights directly:
  ```
  cd sam_service && python3 scripts/download_checkpoint.py vit_h
  ```
  (`vit_b` is smaller/faster if this machine has no GPU.)

### Accessing it from another machine (by IP)

Only port **5173** needs to be reachable from wherever you're connecting
from — the frontend proxies `/api/*` to the backend internally, so
8000/8100/8200 never need to be open through a firewall. Check this
server's IP with `hostname -I` if it's not obvious.

### Troubleshooting

- **`docker run --gpus all` fails with `could not select device driver
  "nvidia"`, but `nvidia-smi` works on the host** — no root to install the
  NVIDIA Container Toolkit. Use `docker-compose.external-ml.yml` (see
  above) instead of the GPU override.
- **`python3 -m venv` fails with "ensurepip is not available"** — the
  `python3-venv` system package is missing and you have no root to install
  it. Use `./scripts/setup_conda_envs.sh` instead; if conda isn't
  available either, bootstrap pip manually with `python3 -m venv
  --without-pip .venv && source .venv/bin/activate && curl -sS
  https://bootstrap.pypa.io/get-pip.py | python3`, then install by hand.
- **`pip install torch` hangs retrying `pypi.ngc.nvidia.com`** — some
  machines (often NVIDIA NGC-container setups) have pip pointed at that
  internal mirror; it's unreachable outside an actual NGC container. Set
  `PIP_INDEX_URL=https://pypi.org/simple` before running the setup script.
- **Already have working conda/venv envs with these deps under different
  names?** Set `BACKEND_PYTHON` / `SAM_SERVICE_PYTHON` /
  `PANOPTIC_SERVICE_PYTHON` in `.env` to their `python3` paths instead of
  reinstalling into a fresh env — see the comments in `.env.example`.

## Development

Working on just the backend or frontend, without the segmentation
services? These run standalone against the placeholder fallbacks — no
model weights needed.

### Backend

```
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Storage (SQLite DB, registered/uploaded images, quantification files) lives
under `backend/storage/`, created automatically on first run.

To also exercise the real segmentation models instead of the placeholders,
start `sam_service`/`panoptic_service` (see their own READMEs) and point
the backend at them:

```
SAM_SERVICE_URL=http://localhost:8100 \
PANOPTIC_SERVICE_URL=http://localhost:8200 \
uvicorn app.main:app --reload --port 8000
```

#### Sample project

If `sample_data/yeast_demo/` (gitignored -- local test fixtures, not
version controlled) contains an image folder, the backend seeds a "Sample
Project" pointing at it on first startup, so there's something to open
immediately. This is a one-time, idempotent seed keyed by project name --
delete the project from the UI and restart the backend to reseed it, or
just add more folders under `sample_data/` and register them yourself from
the Viewer.

### Frontend

```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to
`http://localhost:8000`.

## Trying it out

1. Create a project on the home page.
2. In the Viewer, register a server-side folder of frames or a `.tif`/`.tiff`
   stack (or upload files directly).
3. Draw polygons, switch to "Point Prompt" and click a cell to get a
   predicted mask, or click "Auto-Segment Frame" to detect every instance
   in the frame at once.
4. In Quantification, upload a features CSV/JSON and/or a tracking CSV/JSON
   (needs `id` and `parent_id` columns) to see the feature table, t-SNE, and
   lineage tree.
