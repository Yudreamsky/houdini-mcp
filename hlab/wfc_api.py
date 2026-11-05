from pydantic import BaseModel, ConfigDict, Field


class Sockets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    west: str
    east: str
    south: str
    north: str


class Tile(Sockets):
    name: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0, allow_inf_nan=False)


class Cell(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int
    y: int
    allow: list[str] = Field(min_length=1)
