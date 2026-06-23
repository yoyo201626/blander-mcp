from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SceneObject:
    name: str
    type: str          # GPENCIL / MESH / CAMERA / LIGHT
    location: list     # [x, y, z]

@dataclass
class SceneState:
    objects: dict[str, SceneObject] = field(default_factory=dict)
    frame_start: int = 1
    frame_end: int   = 250
    frame_current: int = 1

    def add_object(self, obj: SceneObject):
        self.objects[obj.name] = obj

    def remove_object(self, name: str):
        self.objects.pop(name, None)

    def to_dict(self) -> dict:
        return {
            "objects": [
                {"name": o.name, "type": o.type, "location": o.location}
                for o in self.objects.values()
            ],
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "frame_current": self.frame_current,
        }

# 全局单例
_state = SceneState()

def get_state() -> SceneState:
    return _state

def reset():
    global _state
    _state = SceneState()