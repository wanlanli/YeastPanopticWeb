import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import SUPPORTED_IMAGE_EXTENSIONS, UPLOAD_DIR
from app.db import get_db
from app.models.series import ImageSeries
from app.schemas.series import SeriesOut, SeriesRegisterPath
from app.services import image_io

router = APIRouter(prefix="/api/series", tags=["series"])


@router.get("", response_model=list[SeriesOut])
def list_series(project_id: int, db: Session = Depends(get_db)):
    return (
        db.query(ImageSeries)
        .filter(ImageSeries.project_id == project_id)
        .order_by(ImageSeries.created_at.desc())
        .all()
    )


@router.get("/{series_id}", response_model=SeriesOut)
def get_series(series_id: int, db: Session = Depends(get_db)):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    return series


@router.post("/register-path", response_model=SeriesOut)
def register_path(body: SeriesRegisterPath, db: Session = Depends(get_db)):
    p = Path(body.path)
    if not p.exists():
        raise HTTPException(400, f"Path does not exist: {body.path}")

    if p.is_dir():
        source_type = "folder"
    elif p.suffix.lower() in (".tif", ".tiff"):
        source_type = "multipage_tiff"
    else:
        raise HTTPException(
            400, "Path must be a directory of frames or a .tif/.tiff stack"
        )

    try:
        meta = image_io.probe_series(source_type, str(p))
    except Exception as exc:
        raise HTTPException(400, f"Could not read series: {exc}") from exc

    series = ImageSeries(
        project_id=body.project_id,
        name=body.name,
        source_type=source_type,
        path=str(p),
        frame_count=meta.frame_count,
        width=meta.width,
        height=meta.height,
        dtype=meta.dtype,
        channels=meta.channels,
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    return series


@router.post("/upload", response_model=SeriesOut)
async def upload_series(
    project_id: int = Form(...),
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "No files uploaded")

    dest_dir = UPLOAD_DIR / str(uuid.uuid4())
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[Path] = []
    for f in files:
        suffix = Path(f.filename or "").suffix.lower()
        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            continue
        dest = dest_dir / Path(f.filename).name
        with dest.open("wb") as out:
            out.write(await f.read())
        saved_paths.append(dest)

    if not saved_paths:
        raise HTTPException(400, "No supported image files in upload")

    if len(saved_paths) == 1 and saved_paths[0].suffix.lower() in (".tif", ".tiff"):
        source_type = "multipage_tiff"
        series_path = saved_paths[0]
    else:
        source_type = "upload"
        series_path = dest_dir

    try:
        meta = image_io.probe_series(source_type, str(series_path))
    except Exception as exc:
        raise HTTPException(400, f"Could not read uploaded series: {exc}") from exc

    series = ImageSeries(
        project_id=project_id,
        name=name,
        source_type=source_type,
        path=str(series_path),
        frame_count=meta.frame_count,
        width=meta.width,
        height=meta.height,
        dtype=meta.dtype,
        channels=meta.channels,
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    return series


@router.get("/{series_id}/frame/{frame_index}")
def get_frame(
    series_id: int,
    frame_index: int,
    vmin: float | None = None,
    vmax: float | None = None,
    db: Session = Depends(get_db),
):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    try:
        arr = image_io.read_frame(series.source_type, series.path, frame_index)
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not read frame: {exc}") from exc

    png_bytes = image_io.render_frame_png(arr, vmin, vmax)
    return Response(content=png_bytes, media_type="image/png")
