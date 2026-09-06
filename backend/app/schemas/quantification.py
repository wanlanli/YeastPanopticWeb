from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class QuantificationDatasetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str
    uploaded_at: datetime


class FeatureTablePage(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int


class TrackingTree(BaseModel):
    # list of node dicts: {id, parent_id, frame_start, frame_end, label, ...}
    nodes: list[dict[str, Any]]


class TsneResult(BaseModel):
    ids: list[Any]
    x: list[float]
    y: list[float]
    color_by: str | None = None
    color_values: list[Any] | None = None
