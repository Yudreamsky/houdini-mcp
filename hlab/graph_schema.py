"""Client-side schema. The host checks all protections again on the Houdini thread."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Create(Operation):
    op: Literal["create"]
    path: str = Field(description="Absolute path of the new node, including its requested name")
    type: str
    template: Literal["fireworks.trails"] | None = None


class Connect(Operation):
    op: Literal["connect"]
    path: str
    input: int = Field(default=0, ge=0)
    source: str | None = Field(description="Absolute upstream path or null to disconnect")
    output: int = Field(default=0, ge=0)


class SetParm(Operation):
    op: Literal["set"]
    path: str
    parm: str
    value: bool | int | float | str
    expect: bool | int | float | str | None = None
    expression: Literal["hscript", "python"] | None = None
    replace_expression: bool = False


class Flags(Operation):
    op: Literal["flags"]
    path: str
    display: bool | None = None
    render: bool | None = None


class Rename(Operation):
    op: Literal["rename"]
    path: str
    name: str


class Delete(Operation):
    op: Literal["delete"]
    path: str


Edit = Create | Connect | SetParm | Flags | Rename | Delete
