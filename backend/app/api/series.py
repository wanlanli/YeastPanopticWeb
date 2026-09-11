import io
import json
import uuid
import zipfile
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_visitor_session
from app.config import SUPPORTED_IMAGE_EXTENSIONS, UPLOAD_DIR
from app.db import get_db
from app.models.polygon import Polygon
from app.models.quantification import QuantificationDataset
from app.models.series import ImageSeries
from app.models.session import VisitorSession
from app.models.user import User
from app.schemas.quantification import FrameMeasureResult, SeriesTrackingMap
from app.schemas.series import SeriesChannelUpdate, SeriesOut, SeriesRegisterPath
from app.services import access, image_io, mask_io
from app.services import quantification_compute
from app.services.series_delete import delete_series_cascade

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
def list_series(
    project_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_project(db, project_id, user, visitor_session)
    return (
        db.query(ImageSeries)
        .filter(ImageSeries.project_id == project_id)
        .order_by(ImageSeries.created_at.desc())
        .all()
    )


@router.get("/{series_id}", response_model=SeriesOut)
def get_series(
    series_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    return access.require_series(db, series_id, user, visitor_session)


@router.delete("/{series_id}")
def delete_series(
    series_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    series = access.require_series(db, series_id, user, visitor_session)
    delete_series_cascade(db, series)
    return {"ok": True}


@router.post("/register-path", response_model=SeriesOut)
def register_path(
    body: SeriesRegisterPath,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_project(db, body.project_id, user, visitor_session)
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
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_project(db, project_id, user, visitor_session)
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
def set_series_channel(
    series_id: int,
    body: SeriesChannelUpdate,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    series = access.require_series(db, series_id, user, visitor_session)
    if body.dic_channel_index < 0 or body.dic_channel_index >= series.channel_count:
        raise HTTPException(400, f"dic_channel_index out of range [0, {series.channel_count})")
    series.dic_channel_index = body.dic_channel_index
    db.commit()
    db.refresh(series)
    return series


@router.get("/{series_id}/frame-names")
def get_frame_names(
    series_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """The original filename for each frame, for series registered from a
    folder/upload of separate image files (one file = one frame). None for
    multipage_tiff series, which have no such per-frame file identity."""
    series = access.require_series(db, series_id, user, visitor_session)
    if series.source_type not in ("folder", "upload"):
        return {"names": None}
    files = image_io.sorted_frame_files(Path(series.path))
    return {"names": [f.name for f in files]}


@router.get("/{series_id}/frame/{frame_index}")
def get_frame(
    series_id: int,
    frame_index: int,
    vmin: float | None = None,
    vmax: float | None = None,
    channel: int | None = None,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    series = access.require_series(db, series_id, user, visitor_session)
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


def _source_stem(series: ImageSeries, frame_index: int | None = None) -> str:
    """Best available real source name for a download filename: the
    frame's own original file (folder/upload of many files), else the
    series' single source file, else just the series' display name."""
    if frame_index is not None and series.source_type in ("folder", "upload"):
        files = image_io.sorted_frame_files(Path(series.path)) if Path(series.path).is_dir() else []
        if 0 <= frame_index < len(files):
            return files[frame_index].stem
    if series.original_filename:
        return Path(series.original_filename).stem
    return series.name


@router.get("/{series_id}/frame/{frame_index}/mask")
def get_frame_mask(
    series_id: int,
    frame_index: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    series = access.require_series(db, series_id, user, visitor_session)
    if frame_index < 0 or frame_index >= series.frame_count:
        raise HTTPException(404, f"frame_index {frame_index} out of range")

    polygons = _frame_polygons(db, series_id, frame_index)
    h, w = image_io.frame_shape(series.source_type, series.path, frame_index)
    mask = mask_io.rasterize_polygons(polygons, h, w)
    tiff_bytes = mask_io.mask_to_tiff_bytes(mask)
    filename = f"{_source_stem(series, frame_index)}_mask.tif"
    return Response(
        content=tiff_bytes,
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _latest_tracking_dataset(db: Session, series_id: int) -> QuantificationDataset | None:
    return (
        db.query(QuantificationDataset)
        .filter(QuantificationDataset.series_id == series_id, QuantificationDataset.kind == "tracking")
        .order_by(QuantificationDataset.uploaded_at.desc())
        .first()
    )


def _load_frame_track_map(db: Session, series_id: int) -> tuple[int | None, dict]:
    """(dataset_id, {str(frame_index): {str(original_label): track_id}}) for
    the latest computed tracking dataset, or (None, {}) if there isn't one."""
    dataset = _latest_tracking_dataset(db, series_id)
    if not dataset:
        return None, {}
    try:
        raw = json.loads(Path(dataset.file_path).read_text())
    except Exception:
        return dataset.id, {}
    frame_track_map = raw.get("frame_track_map", {}) if isinstance(raw, dict) else {}
    return dataset.id, frame_track_map


@router.get("/{series_id}/tracking", response_model=SeriesTrackingMap)
def get_series_tracking_map(
    series_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """The latest computed tracking dataset's frame-by-frame, non-destructive
    label -> track-id map for this series (see quantification_compute) --
    lets the Viewer show "same cell, same id" across frames without touching
    the stored polygon labels. Empty if tracking hasn't been computed yet."""
    access.require_series(db, series_id, user, visitor_session)

    dataset_id, frame_track_map = _load_frame_track_map(db, series_id)
    return SeriesTrackingMap(dataset_id=dataset_id, frame_track_map=frame_track_map)


@router.get("/{series_id}/frame/{frame_index}/measure", response_model=FrameMeasureResult)
def measure_frame(
    series_id: int,
    frame_index: int,
    pixel_size: float = 1.0,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """Lightweight, on-demand per-object geometry (area, skeleton lengths,
    ...) for this frame's currently saved polygons -- no intensity, no
    tracking, nothing persisted. For the full series-wide pipeline
    (intensity, cross-frame tracking), see POST /api/quantification/compute.

    `pixel_size` ("resolution" in the UI) is the physical size of one pixel
    (e.g. um/px); area/length columns come back already scaled by it --
    leave at 1.0 for raw pixels."""
    series = access.require_series(db, series_id, user, visitor_session)
    if frame_index < 0 or frame_index >= series.frame_count:
        raise HTTPException(404, f"frame_index {frame_index} out of range")

    mask = quantification_compute.frame_mask(db, series, frame_index)
    try:
        table = quantification_compute.compute_geometry(mask, pixel_size=pixel_size)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc

    rows = table.replace({np.nan: None}).to_dict(orient="records")
    return FrameMeasureResult(columns=list(table.columns), rows=rows)


@router.get("/{series_id}/mask")
def get_series_mask(
    series_id: int,
    tracked: bool = False,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """Mask export for the whole series, matching the input's own layout:
    a folder/upload of separate frame files exports one mask file per frame
    (zipped together), while a single multipage-tiff stack exports one mask
    stack -- so the output can drop back in next to the source the same way
    it came out.

    `tracked=true` burns each object's stable CellMate track id into the
    mask instead of its own per-frame label, so the same physical cell has
    the same pixel value across every frame of the exported stack -- the
    per-frame label (1000*class+instance) only guarantees uniqueness within
    a series, not "same cell = same id" across frames; that's what tracking
    (see the Viewer's Tracking tab) adds. Requires tracking to already be
    computed for this series."""
    series = access.require_series(db, series_id, user, visitor_session)

    frame_track_map: dict = {}
    if tracked:
        _dataset_id, frame_track_map = _load_frame_track_map(db, series_id)
        if not frame_track_map:
            raise HTTPException(
                400, "No tracking computed for this series yet -- run Tracking in the Viewer first."
            )

    frames = []
    for frame_index in range(series.frame_count):
        polygons = _frame_polygons(db, series_id, frame_index)
        if tracked:
            frame_map = frame_track_map.get(str(frame_index), {})
            polygons = [
                (str(frame_map[label]) if label in frame_map else label, points) for label, points in polygons
            ]
        h, w = image_io.frame_shape(series.source_type, series.path, frame_index)
        frames.append(mask_io.rasterize_polygons(polygons, h, w))

    suffix = "_tracked" if tracked else ""

    if series.source_type in ("folder", "upload"):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for frame_index, mask in enumerate(frames):
                zf.writestr(
                    f"{_source_stem(series, frame_index)}_mask{suffix}.tif", mask_io.mask_to_tiff_bytes(mask)
                )
        filename = f"{_source_stem(series)}_masks{suffix}.zip"
        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    tiff_bytes = mask_io.mask_stack_to_tiff_bytes(frames)
    filename = f"{_source_stem(series)}_mask{suffix}.tif"
    return Response(
        content=tiff_bytes,
        media_type="image/tiff",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
