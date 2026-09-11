# YeastPanopticWeb

Microscopy image annotation and quantification viewer: segment cells
(point-prompt or one-click whole-frame auto-segmentation), edit masks,
track movies, and browse quantification results (feature table, lineage
tree, t-SNE).

## Start

### Docker

```
git clone https://github.com/wanlanli/YeastPanopticWeb.git && cd YeastPanopticWeb
cp .env.docker.example .env.docker   # add your model weight paths
docker compose --env-file .env.docker up -d --build
```

### conda / venv

```
git clone https://github.com/wanlanli/YeastPanopticWeb.git && cd YeastPanopticWeb
./scripts/setup_venv_envs.sh   # or setup_conda_envs.sh if venv isn't available
./scripts/run_all.sh
```

Either way, open `http://<this-server-ip>:5173`. Everything else (the
segmentation/quantification repos, Python/npm deps) is fetched
automatically -- the only thing you add by hand is the model weights (see
`.env.example` / `.env.docker.example`).
