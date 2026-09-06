from pydantic import BaseModel, ConfigDict


class SeriesRegisterPath(BaseModel):
    project_id: int
    name: str
    path: str


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    source_type: str
    frame_count: int
    width: int
    height: int
    dtype: str
    channels: int
