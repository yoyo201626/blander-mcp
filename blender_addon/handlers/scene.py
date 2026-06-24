from __future__ import annotations

from typing import Any, TypedDict

import bpy


class SceneCreateParams(TypedDict, total=False):
    name: str
    fps: int


class SceneResult(TypedDict):
    success: bool
    result: dict[str, Any]
    error: None


def scene_clear(params: dict[str, Any]) -> dict[str, Any]:
    """删除场景中所有非默认对象（保留默认摄像机和灯光）"""
    deleted: list[str] = []
    for obj in list(bpy.context.scene.objects):
        if obj.type not in ["CAMERA", "LIGHT"]:
            deleted.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)

    return {
        "success": True,
        "result": {"cleared": True, "deleted_count": len(deleted)},
        "deleted_objects": deleted,
        "error": None,
    }


def scene_get_state(params: dict[str, Any]) -> dict[str, Any]:
    """获取当前场景的完整状态"""
    objects = [
        {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        }
        for obj in bpy.context.scene.objects
    ]

    return {
        "success": True,
        "result": {
            "objects": objects,
            "frame_start": bpy.context.scene.frame_start,
            "frame_end": bpy.context.scene.frame_end,
            "frame_current": bpy.context.scene.frame_current,
        },
        "error": None,
    }


def scene_create(params: SceneCreateParams) -> dict[str, Any]:
    """创建新场景或设置场景参数"""
    name = params.get("name", "Scene")
    fps = params.get("fps", 24)

    scene = bpy.context.scene
    scene.name = name
    scene.render.fps = fps

    return {
        "success": True,
        "result": {
            "name": scene.name,
            "fps": scene.render.fps,
        },
        "error": None,
    }
