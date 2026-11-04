from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PolygonCreate(BaseModel):
    points: list[list[float]]
    label: str = ""
    # When set, the backend assigns the label itself -- see
    # annotations.py's create_polygon -- instead of trusting `label` as
    # given, so a new object can never collide with an instance number a
    # concurrent create (or a different frame) already used.
    class_id: int | None = None
    source: str = "manual"


class PolygonUpdate(BaseModel):
    points: list[list[float]] | None = None
    label: str | None = None


class PolygonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int
    frame_index: int
    points: list[list[float]]
    label: str
    source: str
    updated_at: datetime


class Point(BaseModel):
    x: float
    y: float
    label: int = 1  # 1 = include (foreground), 0 = exclude (background)


class PointPrompt(BaseModel):
    points: list[Point]


class PredictResult(BaseModel):
    polygons: list[list[list[float]]]


class FramePrediction(BaseModel):
    class_id: int
    class_name: str
    points: list[list[float]]
    confidence: float


class FramePredictResult(BaseModel):
    # The auto-segmentation service's cache key for this prediction, if it
    # supports cheap re-thresholding -- pass it to .../refine-frame/{id} to
    # recompute `predictions` under new thresholds without rerunning the
    # model. None for a model that doesn't support this (e.g. the classical-
    # CV placeholder, where rerunning is cheap anyway).
    result_id: str | None = None
    predictions: list[FramePrediction]


class AcceptPredictionsRequest(BaseModel):
    """Commits a previewed (predict-frame/refine-frame) result: one
    `Polygon` row per prediction, plus a `FramePredictionRun` row recording
    the thresholds that produced them -- see
    app.api.annotations.accept_predictions."""

    result_id: str | None = None
    predictions: list[FramePrediction]
    score_threshold: float
    instance_threshold: float
    area_threshold: int
    hole_area_threshold: int = 1000
    keep_border: bool = False
