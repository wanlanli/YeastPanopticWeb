from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_visitor_session
from app.db import get_db
from app.models.polygon import Polygon
from app.models.prediction import FramePredictionRun
from app.models.session import VisitorSession
from app.models.user import User
from app.schemas.polygon import (
    AcceptPredictionsRequest,
    FramePredictResult,
    PointPrompt,
    PolygonCreate,
    PolygonOut,
    PolygonUpdate,
    PredictResult,
)
from app.services import access, image_io
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
def list_polygons(
    series_id: int,
    frame_index: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_series(db, series_id, user, visitor_session)
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
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_series(db, series_id, user, visitor_session)

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
def delete_frame_polygons(
    series_id: int,
    frame_index: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_series(db, series_id, user, visitor_session)
    deleted = (
        db.query(Polygon)
        .filter(Polygon.series_id == series_id, Polygon.frame_index == frame_index)
        .delete()
    )
    db.commit()
    return {"deleted": deleted}


@router.delete("/{series_id}/polygons")
def delete_series_polygons(
    series_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    access.require_series(db, series_id, user, visitor_session)
    deleted = db.query(Polygon).filter(Polygon.series_id == series_id).delete()
    db.commit()
    return {"deleted": deleted}


@router.put("/polygons/{polygon_id}", response_model=PolygonOut)
def update_polygon(
    polygon_id: int,
    body: PolygonUpdate,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    polygon = access.require_polygon(db, polygon_id, user, visitor_session)
    if body.points is not None:
        polygon.points = body.points
    if body.label is not None:
        polygon.label = body.label
    db.commit()
    db.refresh(polygon)
    return polygon


@router.delete("/polygons/{polygon_id}")
def delete_polygon(
    polygon_id: int,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    polygon = access.require_polygon(db, polygon_id, user, visitor_session)
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
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    series = access.require_series(db, series_id, user, visitor_session)
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
    hole_area_threshold: int | None = None,
    keep_border: bool = False,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """Runs the model once and returns a preview -- this never writes to
    the database. score_threshold/instance_threshold/area_threshold/
    hole_area_threshold/keep_border are user-adjustable filtering knobs
    (see the app's Advanced Settings panel next to Auto-Segment Frame);
    omitted ones fall back to the model's own defaults.

    The response's `result_id`, when present, can be passed to
    `.../refine-frame/{result_id}` to cheaply recompute `predictions` for
    different thresholds without rerunning the model -- that's what the
    Advanced Settings panel calls while a preview is pending acceptance
    (see `.../predict-frame/accept`)."""
    series = access.require_series(db, series_id, user, visitor_session)
    try:
        arr = image_io.read_frame(
            series.source_type, series.path, frame_index, series.dic_channel_index or 0
        )
    except IndexError as exc:
        raise HTTPException(404, str(exc)) from exc

    model = get_auto_model()
    try:
        result = model.predict_frame(
            arr,
            score_threshold=score_threshold,
            instance_threshold=instance_threshold,
            area_threshold=area_threshold,
            hole_area_threshold=hole_area_threshold,
            keep_border=keep_border,
        )
    except SegmentationServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return FramePredictResult(**result)


@router.get(
    "/{series_id}/frame/{frame_index}/refine-frame/{result_id}",
    response_model=FramePredictResult,
)
def refine_frame(
    series_id: int,
    frame_index: int,
    result_id: str,
    score_threshold: float | None = None,
    instance_threshold: float | None = None,
    area_threshold: int | None = None,
    hole_area_threshold: int | None = None,
    keep_border: bool = False,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """Cheaply recompute a pending preview's predictions under new
    thresholds -- no model forward pass, and (unlike `predict-frame`) no
    re-reading of the frame either, as long as the active model supports
    caching (see AutoSegmentationModel.refine_frame). Still never writes
    to the database -- same as `predict-frame`, this only updates what the
    Advanced Settings panel is previewing.

    Falls back to a fresh `predict-frame` call transparently if the active
    model has no cache to refine from (e.g. the classical-CV placeholder) --
    callers don't need to know which case they're in."""
    series = access.require_series(db, series_id, user, visitor_session)
    model = get_auto_model()
    try:
        result = model.refine_frame(
            result_id,
            score_threshold=score_threshold,
            instance_threshold=instance_threshold,
            area_threshold=area_threshold,
            hole_area_threshold=hole_area_threshold,
            keep_border=keep_border,
        )
    except NotImplementedError:
        try:
            arr = image_io.read_frame(
                series.source_type, series.path, frame_index, series.dic_channel_index or 0
            )
        except IndexError as exc:
            raise HTTPException(404, str(exc)) from exc
        try:
            result = model.predict_frame(
                arr,
                score_threshold=score_threshold,
                instance_threshold=instance_threshold,
                area_threshold=area_threshold,
                hole_area_threshold=hole_area_threshold,
                keep_border=keep_border,
            )
        except SegmentationServiceError as exc:
            raise HTTPException(502, str(exc)) from exc
    except SegmentationServiceError as exc:
        raise HTTPException(502, str(exc)) from exc
    return FramePredictResult(**result)


@router.post(
    "/{series_id}/frame/{frame_index}/predict-frame/accept",
    response_model=list[PolygonOut],
)
def accept_predictions(
    series_id: int,
    frame_index: int,
    body: AcceptPredictionsRequest,
    user: User | None = Depends(get_current_user),
    visitor_session: VisitorSession = Depends(get_visitor_session),
    db: Session = Depends(get_db),
):
    """Commits a previewed predict-frame/refine-frame result: one `Polygon`
    row per prediction (labeled the same way a model-sourced polygon always
    is -- see `_next_label_for_class`), plus a `FramePredictionRun` row
    recording which thresholds produced them."""
    access.require_series(db, series_id, user, visitor_session)

    prediction_run = FramePredictionRun(
        series_id=series_id,
        frame_index=frame_index,
        result_id=body.result_id,
        score_threshold=body.score_threshold,
        instance_threshold=body.instance_threshold,
        area_threshold=body.area_threshold,
        hole_area_threshold=body.hole_area_threshold,
        keep_border=body.keep_border,
    )
    db.add(prediction_run)
    db.flush()  # assigns prediction_run.id, needed by the polygons below

    created: list[Polygon] = []
    for pred in body.predictions:
        label = _next_label_for_class(db, series_id, pred.class_id)
        polygon = Polygon(
            series_id=series_id,
            frame_index=frame_index,
            points=pred.points,
            label=label,
            source="model",
            prediction_id=prediction_run.id,
        )
        db.add(polygon)
        db.flush()  # so the next prediction's _next_label_for_class sees it
        created.append(polygon)

    db.commit()
    for polygon in created:
        db.refresh(polygon)
    return created
