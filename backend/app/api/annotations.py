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

    polygon = Polygon(
        series_id=series_id,
        frame_index=frame_index,
        points=body.points,
        label=body.label,
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
        arr = image_io.read_frame(series.source_type, series.path, frame_index)
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
    db: Session = Depends(get_db),
):
    series = db.get(ImageSeries, series_id)
    if not series:
        raise HTTPException(404, "Series not found")
    try:
        arr = image_io.read_frame(series.source_type, series.path, frame_index)
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc

    model = get_auto_model()
    try:
        predictions = model.predict_frame(arr)
    except SegmentationServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return FramePredictResult(predictions=predictions)
