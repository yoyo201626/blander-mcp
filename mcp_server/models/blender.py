from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BlenderCommand(BaseModel):
    tool: str
    params: dict[str, Any] = {}


class BlenderError(BaseModel):
    code: str
    message: str


class BlenderResponse(BaseModel):
    success: bool
    result: dict[str, Any] | None = None
    error: BlenderError | None = None
    deleted_objects: list[str] = []
