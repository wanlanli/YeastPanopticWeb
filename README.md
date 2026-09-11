# YeastPanopticWeb

Microscopy image annotation and quantification viewer: view image
series/movies (8/16-bit TIFF, PNG, JPEG), edit segmentation masks as
polygons, request a mask from a point-prompt model, navigate frames, and
browse precomputed quantification results (feature table, tracking/lineage
tree, t-SNE).

See `PLAN.md`-equivalent context in the original design plan for the full
architecture writeup. Segmentation lives behind swappable interfaces at
`backend/app/services/segmentation/`, with two models, each its own
standalone HTTP service so heavy ML deps stay out of the main API process:

- **Point-prompt (SAM)** — click a cell, get one mask back. Calls out to
  `sam_service/` once running; falls back to a classical-CV placeholder
  (region growing from the clicked point) otherwise.
- **Whole-frame auto-segmentation (yeast panoptic model)** — one click,
  every instance in the frame back (cell/shmoo/zygote/tetrad/lysis/spore),
  each labeled by class. Calls out to `panoptic_service/` once running;
  falls back to a classical-CV placeholder (Otsu threshold + connected
  components, labeled "cell") otherwise.

The app is four services: `backend` (FastAPI), `frontend` (Vite/React),
and the two segmentation services above. Only `backend` + `frontend` are
required — the segmentation services are optional, each falling back to a
classical-CV placeholder when not running (see above).

## Installation

Two ways to install and run this on a machine (your own, or a server):
**Docker Compose**, or **conda/venv** Python environments directly on the
host. Either way you need the same machine-specific config files first
(model repo, checkpoints, CellMate) — see "Config you need to change"
below; every one of them degrades gracefully if left unset, so it's fine
to install first and add them later.

|                | Docker Compose | conda / venv |
|----------------|-----------------|--------------|
| Best for       | more than one machine, or not wanting to manage 3 Python envs by hand | a single machine, quick iteration, no Docker available |
| Isolation      | pins OS + Python version per service | uses whatever Python/OS is already on the host |
| GPU setup      | needs the NVIDIA Container Toolkit (or the `external-ml` escape hatch, see below) | uses the host's driver directly, nothing extra to install |
| CellMate build | automatic, inside the container, on first start | manual, once, matching the host's Python (see below) |

### Option 1: Docker Compose

```
git clone <this repo> && cd YeastPanopticWeb
cp .env.docker.example .env.docker   # edit the paths in it -- see below
docker compose --env-file .env.docker up -d --build
```

Open `http://<this-server-ip>:5173` (only this port is published to the
host -- see "Accessing it from another machine" below). CellMate's Cython
extension is built automatically, once, the
first time the `backend` container starts (verified against a genuinely
fresh CellMate checkout: built cleanly, no manual step needed) -- inside
the container, so it always matches that container's own Python,
regardless of what's on the host.

Logs: `docker compose --env-file .env.docker logs -f [service]`. Stop:
`docker compose --env-file .env.docker down` (add `-v` to also drop the
backend's database/upload volume).

**Using a GPU?** By default Docker never exposes the host's GPU to any
container -- that's true regardless of this project, not something to fix
in `docker-compose.yml` alone. If this server has an NVIDIA GPU, add the
`docker-compose.gpu.yml` override (see the comment at the top of that file
for the one-time host prerequisite -- the NVIDIA Container Toolkit -- and
how to verify it's working before trying this):

```
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --env-file .env.docker up -d --build
```

Confirm it's actually using the GPU (should print `True`):
```
docker compose --env-file .env.docker exec sam_service python3 -c "import torch; print(torch.cuda.is_available())"
```

**No root, so can't install the NVIDIA Container Toolkit?** (symptom:
`docker run --gpus all ...` or the command above fails with `could not
select device driver "nvidia"`, even though `nvidia-smi` works fine
directly on the host.) There's no rootless workaround for that specific
piece -- it registers a device-driver hook with the Docker daemon itself.
Use `docker-compose.external-ml.yml` instead: it keeps backend+frontend in
Docker (no GPU needed there) and runs sam_service/panoptic_service as
plain host processes -- same GPU access `nvidia-smi` already has, zero
Docker/root involvement, and if you already have conda envs with
torch/detectron2/segment-anything installed, reuse them as-is. See the
comment at the top of that file for the exact commands.

### Option 2: conda or .venv (plain Python environments)

One-time setup, then one script starts everything. Pick **venv** (needs
the `python3-venv` system package) or **conda** (no system package
needed, works if conda is already installed) -- both install the exact
same things, just into different kinds of environment.

**Using venv:**

```
git clone <this repo> && cd YeastPanopticWeb

cd backend          && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
cd sam_service       && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && deactivate && cd ..
cd panoptic_service  && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && pip install 'git+https://github.com/cocodataset/panopticapi.git' && deactivate && cd ..
cd frontend          && npm install && cd ..

cp .env.example .env   # then edit the paths in it -- see below
./scripts/run_all.sh   # starts all 4 services, prints the URL to open
```

**Using conda** (if `python3 -m venv` fails with "ensurepip is not
available" -- that's the `python3-venv` system package missing, which
normally needs `apt install`/root to fix -- or if conda is already what
you use):

```
git clone <this repo> && cd YeastPanopticWeb

./scripts/setup_conda_envs.sh
# creates yeastpanoptic-backend / -sam_service / -panoptic_service (python 3.10)
# and installs each service's requirements.txt into the matching one.
# Safe to re-run: skips any env that already exists, so a partial failure
# (e.g. a network blip mid-install) doesn't lose what already installed.

cd frontend && npm install && cd ..

cp .env.example .env
# then edit the paths in it -- see below -- and add:
#   PYTHON_ENV_MANAGER=conda
./scripts/run_all.sh   # starts all 4 services, prints the URL to open
```

No conda either? `python3 -m venv --without-pip .venv && source
.venv/bin/activate && curl -sS https://bootstrap.pypa.io/get-pip.py |
python3` bootstraps pip manually, no new system packages needed (just
outbound network access) -- then continue with the venv steps above.

`torch` (in `sam_service`/`panoptic_service`) installs with GPU support
automatically from PyPI -- no special index/CUDA setup needed, for either
venv or conda. If this machine has an NVIDIA GPU + driver, it's used
automatically (`torch.cuda.is_available()`); otherwise everything runs on
CPU. Confirm with:

```
<env>/bin/python3 -c "import torch; print(torch.cuda.is_available())"
```

(`<env>` is `sam_service/.venv` for venv, or the path `conda info --base`
prints joined with `envs/yeastpanoptic-sam_service`, for conda.)

Stop everything with `./scripts/stop_all.sh`. Logs land in `logs/*.log`.

### Config you need to change (`.env` / `.env.docker`)

None of these live in this git repo -- they're large, machine-specific, or
private, so a fresh checkout has none of them. Same underlying files
either way; `.env.example` (plain envs) uses the path directly, e.g.
`CELLMATE_PATH=/path/to/CellMate`, while `.env.docker.example` (Docker)
uses a `_HOST` suffix for the same thing, e.g. `CELLMATE_HOST=...`, since
that's a host-machine path being mounted into a container rather than a
path the app reads directly. See whichever `.example` file you're using
for the full list; the short version:

- **panoptic model repo** (`PANOPTIC_REPO_PATH` / `PANOPTIC_REPO_HOST`) — a
  separate private repo (detectron2 code the panoptic model needs).
  Copy/clone it onto this machine first.
- **panoptic model dir** (`PANOPTIC_MODEL_DIR` / `PANOPTIC_MODEL_DIR_HOST`)
  — the fine-tuned checkpoint + its matching `config.yaml`, saved together.
  Copy this directory over (e.g. `rsync -avP` from wherever it currently
  lives).
- **SAM checkpoint** (`SAM_CHECKPOINT_PATH` / `SAM_CHECKPOINT_HOST`, plus
  `SAM_MODEL_TYPE`) — either copy an existing checkpoint here, or run `cd
  sam_service && python3 scripts/download_checkpoint.py vit_h` (or `vit_b`
  for a smaller/faster model if this server has no GPU) to fetch the
  official one directly.
- **CellMate** (`CELLMATE_PATH` / `CELLMATE_HOST`) — a checkout of the
  CellMate quantification library. With Docker, its Cython extension
  builds itself automatically inside the container on first start (see
  above). Without Docker, **it must already be built for this machine's
  own Python version** (a `.so` built elsewhere won't load if the Python
  version differs) -- `pip install Cython` then `python3 setup.py
  build_ext --inplace` in `cellmate/image_measure/measure/`. Without this
  set, quantification features return a clear error but everything else
  still works.
- `SAM_SERVICE_URL` / `PANOPTIC_SERVICE_URL` (plain envs only -- Docker
  Compose wires these up automatically via container names) can usually
  stay as `http://localhost:8100` / `:8200` -- only change these if you're
  running those services on a different machine than the backend.

Any of the above left unset degrades gracefully rather than crashing:
without the panoptic repo/model dir, `panoptic_service` starts but
`/health` reports why it can't load, and the backend falls back to a
classical-CV placeholder for auto-segmentation; same idea for SAM and
CellMate.

### Accessing it from another machine (by IP)

Either option only needs port **5173** reachable from wherever you're
connecting from -- the frontend dev server proxies `/api/*` to the backend
internally, so the other three ports (8000/8100/8200) don't need to be
open through any firewall (Docker Compose doesn't even publish them to the
host at all by default -- see `docker-compose.yml`). `scripts/run_all.sh`
binds every service to `0.0.0.0` and prints the URL to use
(`http://<this-server-ip>:5173`); Docker Compose's `frontend` service does
the same via its `ports:` mapping. Check the server's own IP with
`hostname -I` if it's not obvious (e.g. it changed, or you're on a
different network).

## Development

Working on just the backend or frontend, without the segmentation
services? These run standalone against the placeholder fallbacks -- no
model checkpoints needed.

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

`sam_service` works out of the box with the official SAM weights;
`panoptic_service` additionally needs the private fine-tuned model repo
and checkpoint (see its README) before it'll actually load.

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
