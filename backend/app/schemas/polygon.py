from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PolygonCreate(BaseModel):
    points: list[list[float]]
    label: str = ""
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


class PointPrompt(BaseModel):
    x: float
    y: float


class PredictResult(BaseModel):
    polygons: list[list[list[float]]]
