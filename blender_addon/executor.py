from __future__ import annotations

from typing import Any, TypedDict


class BlenderCommand(TypedDict):
    tool: str
    params: dict[str, Any]


class BlenderError(TypedDict):
    code: str
    message: str


class BlenderResult(TypedDict):
    success: bool
    result: dict[str, Any] | None
    error: BlenderError | None


def execute(command: BlenderCommand) -> BlenderResult:
    tool = command.get("tool")
    params = command.get("params", {})

    from blender_addon.handlers import scene as scene_handler

    handlers = {
        "system.ping": _ping,
        "scene.create": scene_handler.scene_create,
        "scene.clear": scene_handler.scene_clear,
        "scene.get_state": scene_handler.scene_get_state,
    }

    handler = handlers.get(tool)
    if not handler:
        return {
            "success": False,
            "result": None,
            "error": {
                "code": "UNKNOWN_TOOL",
                "message": f"未知工具: {tool}",
                "available_tools": list(handlers.keys()),
            },
        }
    return handler(params)


def _ping(params: dict[str, Any]) -> BlenderResult:
    import bpy
    return {
        "success": True,
        "result": {
            "status": "pong",
            "blender_version": ".".join(str(v) for v in bpy.app.version),
        },
        "error": None,
    }
