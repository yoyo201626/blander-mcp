from mcp_server.models.scene import SceneObject


class SceneState:
    def __init__(self) -> None:
        self.objects: dict[str, SceneObject] = {}
        self.frame_start: int = 1
        self.frame_end: int = 250
        self.frame_current: int = 1

    def add_object(self, obj: SceneObject) -> None:
        self.objects[obj.name] = obj

    def remove_object(self, name: str) -> None:
        self.objects.pop(name, None)

    def to_dict(self) -> dict:
        return {
            "objects": [o.model_dump() for o in self.objects.values()],
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "frame_current": self.frame_current,
        }


_state = SceneState()


def get_state() -> SceneState:
    return _state


def reset() -> None:
    global _state
    _state = SceneState()
