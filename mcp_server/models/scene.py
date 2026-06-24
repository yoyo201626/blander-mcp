from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from mcp_server.models.blender import BlenderError


class SceneObject(BaseModel):
    name: str
    type: str
    location: list[float]

    @field_validator("location")
    @classmethod
    def validate_location(cls, v: list[float]) -> list[float]:
        if len(v) != 3:
            raise ValueError("location must have 3 elements [x, y, z]")
        return v


class SceneStateDelta(BaseModel):
    added: list[str] = []
    modified: list[str] = []
    removed: list[str] = []


class PingResult(BaseModel):
    success: bool
    status: str = ""
    blender_version: str = ""
    error: BlenderError | None = None


class SceneCreateResult(BaseModel):
    success: bool
    name: str = ""
    fps: int = 0
    scene_state_delta: SceneStateDelta = Field(default_factory=SceneStateDelta)
    error: BlenderError | None = None


class SceneClearResult(BaseModel):
    success: bool
    scene_state_delta: SceneStateDelta = Field(default_factory=SceneStateDelta)
    error: BlenderError | None = None


class SceneGetStateResult(BaseModel):
    success: bool
    objects: list[SceneObject] = []
    frame_start: int = 1
    frame_end: int = 250
    frame_current: int = 1
    scene_state_delta: SceneStateDelta = Field(default_factory=SceneStateDelta)
    error: BlenderError | None = None
