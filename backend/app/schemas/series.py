import json

from pydantic import BaseModel, ConfigDict, field_validator


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
    channel_count: int
    channel_names: list[str] | None
    dic_channel_index: int | None
    original_filename: str | None = None

    @field_validator("channel_names", mode="before")
    @classmethod
    def _parse_channel_names(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v


class SeriesChannelUpdate(BaseModel):
    dic_channel_index: int
