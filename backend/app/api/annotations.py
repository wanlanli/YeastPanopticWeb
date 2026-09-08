from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.polygon import Polygon
from app.models.series import ImageSeries
from app.schemas.polygon import (
    FramePredictResult,
    PointPrompt,
    PolygonCreate,
    PolygonOut,
    PolygonUpdate,
    PredictResult,
)
from app.services import image_io
from app.services.segmentation import get_auto_model, get_model
from app.services.segmentation.http_model import SegmentationServiceError

router = APIRouter(prefix="/api/series", tags=["annotations"])


def _next_label_for_class(db: Session, series_id: int, class_id: int) -> str:
    """Next unique `1000*class_id + instance` label for this series --
    scanned across every frame of the series, not just the one a new
    polygon is being created on. Labels double as stable per-object
    tracking ids across the whole movie (the `1000*class+instance` scheme,
    matching CellMate's own DIVISION=1000 convention) -- a brand-new object
    must never reuse an instance number some other object (model- or
    manually-created, on any frame) already has, or the two become
    indistinguishable to tracking/quantification."""
    max_instance = 0
    for (label,) in db.query(Polygon.label).filter(Polygon.series_id == series_id):
        try:
            label_int = int(label)
        except (TypeError, ValueError):
            continue
        c = label_int // 1000
        if c != class_id:
            continue
        max_instance = max(max_instance, label_int - c * 1000)
    return str(class_id * 1000 + max_instance + 1)


@router.get(
    "/{series_id}/frame/{frame_index}/polygons", response_model=list[PolygonOut]
)
def list_polygons(series_id: int, frame_index: int, db: Session = Depends(get_db)):
    return (
        db.query(Polygon)
        .filter(Polygon.series_id == series_id, Polygon.frame_index == frame_index)
        .all()
    )


@router.post(
    "/{series_id}/frame/{frame_index}/polygons", response_model=PolygonOut
)
def create_polygon(
    series_id: int,
    frame_index: int,
    body: PolygonCreate,
    db: Session = Depends(get_db),
):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")

    label = _next_label_for_class(db, series_id, body.class_id) if body.class_id is not None else body.label

    polygon = Polygon(
        series_id=series_id,
        frame_index=frame_index,
        points=body.points,
        label=label,
        source=body.source,
    )
    db.add(polygon)
    db.commit()
    db.refresh(polygon)
    return polygon


@router.delete("/{series_id}/frame/{frame_index}/polygons")
def delete_frame_polygons(series_id: int, frame_index: int, db: Session = Depends(get_db)):
    deleted = (
        db.query(Polygon)
        .filter(Polygon.series_id == series_id, Polygon.frame_index == frame_index)
        .delete()
    )
    db.commit()
    return {"deleted": deleted}


@router.delete("/{series_id}/polygons")
def delete_series_polygons(series_id: int, db: Session = Depends(get_db)):
    deleted = db.query(Polygon).filter(Polygon.series_id == series_id).delete()
    db.commit()
    return {"deleted": deleted}


@router.put("/polygons/{polygon_id}", response_model=PolygonOut)
def update_polygon(
    polygon_id: int, body: PolygonUpdate, db: Session = Depends(get_db)
):
    polygon = db.get(Polygon, polygon_id)
    if not polygon:
        raise HTTPException(404, "Polygon not found")
    if body.points is not None:
        polygon.points = body.points
    if body.label is not None:
        polygon.label = body.label
    db.commit()
    db.refresh(polygon)
    return polygon


@router.delete("/polygons/{polygon_id}")
def delete_polygon(polygon_id: int, db: Session = Depends(get_db)):
    polygon = db.get(Polygon, polygon_id)
    if not polygon:
        raise HTTPException(404, "Polygon not found")
    db.delete(polygon)
    db.commit()
    return {"ok": True}


@router.post(
    "/{series_id}/frame/{frame_index}/predict-point", response_model=PredictResult
)
def predict_point(
    series_id: int,
    frame_index: int,
    body: PointPrompt,
    db: Session = Depends(get_db),
):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    try:
        arr = image_io.read_frame(
            series.source_type, series.path, frame_index, series.dic_channel_index or 0
        )
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc

    model = get_model()
    points = [(p.x, p.y, p.label) for p in body.points]
    try:
        polygons = model.predict_point(arr, points)
    except SegmentationServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return PredictResult(polygons=polygons)


@router.post(
    "/{series_id}/frame/{frame_index}/predict-frame", response_model=FramePredictResult
)
def predict_frame(
    series_id: int,
    frame_index: int,
    score_threshold: float | None = None,
    instance_threshold: float | None = None,
    area_threshold: int | None = None,
    keep_border: bool = False,
    db: Session = Depends(get_db),
):
    """score_threshold/instance_threshold/area_threshold/keep_border are
    user-adjustable filtering knobs (see the app's Advanced Settings panel
    next to Auto-Segment Frame); omitted ones fall back to the model's own
    defaults."""
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    try:
        arr = image_io.read_frame(
            series.source_type, series.path, frame_index, series.dic_channel_index or 0
        )
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc

    model = get_auto_model()
    try:
        predictions = model.predict_frame(
            arr,
            score_threshold=score_threshold,
            instance_threshold=instance_threshold,
            area_threshold=area_threshold,
            keep_border=keep_border,
        )
    except SegmentationServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return FramePredictResult(predictions=predictions)
