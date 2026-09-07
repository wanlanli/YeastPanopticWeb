import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import SUPPORTED_IMAGE_EXTENSIONS, UPLOAD_DIR
from app.db import get_db
from app.models.polygon import Polygon
from app.models.quantification import QuantificationDataset
from app.models.series import ImageSeries
from app.schemas.quantification import SeriesTrackingMap
from app.schemas.series import SeriesChannelUpdate, SeriesOut, SeriesRegisterPath
from app.services import image_io, mask_io

router = APIRouter(prefix="/api/series", tags=["series"])


def _series_fields_from_meta(meta: image_io.SeriesMetadata) -> dict:
    return dict(
        frame_count=meta.frame_count,
        width=meta.width,
        height=meta.height,
        dtype=meta.dtype,
        channels=meta.channels,
        channel_count=meta.channel_count,
        channel_names=json.dumps(meta.channel_names) if meta.channel_names else None,
        dic_channel_index=meta.dic_channel_index,
    )


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
        **_series_fields_from_meta(meta),
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
        **_series_fields_from_meta(meta),
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    return series


@router.patch("/{series_id}/channel", response_model=SeriesOut)
def set_series_channel(series_id: int, body: SeriesChannelUpdate, db: Session = Depends(get_db)):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    if body.dic_channel_index < 0 or body.dic_channel_index >= series.channel_count:
        raise HTTPException(400, f"dic_channel_index out of range [0, {series.channel_count})")
    series.dic_channel_index = body.dic_channel_index
    db.commit()
    db.refresh(series)
    return series


@router.get("/{series_id}/frame/{frame_index}")
def get_frame(
    series_id: int,
    frame_index: int,
    vmin: float | None = None,
    vmax: float | None = None,
    channel: int | None = None,
    db: Session = Depends(get_db),
):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    channel_index = channel if channel is not None else (series.dic_channel_index or 0)
    try:
        arr = image_io.read_frame(series.source_type, series.path, frame_index, channel_index)
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not read frame: {exc}") from exc

    png_bytes = image_io.render_frame_png(arr, vmin, vmax)
    return Response(content=png_bytes, media_type="image/png")


def _frame_polygons(db: Session, series_id: int, frame_index: int) -> list[tuple[str, list[list[float]]]]:
    rows = (
        db.query(Polygon)
        .filter(Polygon.series_id == series_id, Polygon.frame_index == frame_index)
        .order_by(Polygon.id)
        .all()
    )
    return [(p.label, p.points) for p in rows]


@router.get("/{series_id}/frame/{frame_index}/mask")
def get_frame_mask(series_id: int, frame_index: int, db: Session = Depends(get_db)):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    if frame_index < 0 or frame_index >= series.frame_count:
        raise HTTPException(404, f"frame_index {frame_index} out of range")

    polygons = _frame_polygons(db, series_id, frame_index)
    mask = mask_io.rasterize_polygons(polygons, series.height, series.width)
    tiff_bytes = mask_io.mask_to_tiff_bytes(mask)
    filename = f"{series.name}_frame{frame_index}_mask.tif"
    return Response(
        content=tiff_bytes,
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{series_id}/tracking", response_model=SeriesTrackingMap)
def get_series_tracking_map(series_id: int, db: Session = Depends(get_db)):
    """The latest computed tracking dataset's frame-by-frame, non-destructive
    label -> track-id map for this series (see quantification_compute) --
    lets the Viewer show "same cell, same id" across frames without touching
    the stored polygon labels. Empty if tracking hasn't been computed yet."""
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")

    dataset = (
        db.query(QuantificationDataset)
        .filter(QuantificationDataset.series_id == series_id, QuantificationDataset.kind == "tracking")
        .order_by(QuantificationDataset.uploaded_at.desc())
        .first()
    )
    if not dataset:
        return SeriesTrackingMap(dataset_id=None, frame_track_map={})

    try:
        raw = json.loads(Path(dataset.file_path).read_text())
    except Exception:
        return SeriesTrackingMap(dataset_id=dataset.id, frame_track_map={})

    frame_track_map = raw.get("frame_track_map", {}) if isinstance(raw, dict) else {}
    return SeriesTrackingMap(dataset_id=dataset.id, frame_track_map=frame_track_map)


@router.get("/{series_id}/mask")
def get_series_mask(series_id: int, db: Session = Depends(get_db)):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")

    frames = []
    for frame_index in range(series.frame_count):
        polygons = _frame_polygons(db, series_id, frame_index)
        frames.append(mask_io.rasterize_polygons(polygons, series.height, series.width))

    tiff_bytes = mask_io.mask_stack_to_tiff_bytes(frames)
    filename = f"{series.name}_mask.tif"
    return Response(
        content=tiff_bytes,
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
