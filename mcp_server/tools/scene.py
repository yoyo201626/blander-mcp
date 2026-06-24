from mcp_server.models.blender import BlenderCommand
from mcp_server.models.protocols import BlenderTransport
from mcp_server.models.scene import (
    SceneCreateResult,
    SceneClearResult,
    SceneGetStateResult,
    SceneObject,
    SceneStateDelta,
)
from mcp_server.state.scene_state import get_state, reset


def _parse_objects(raw: list[dict]) -> list[SceneObject]:
    return [SceneObject.model_validate(o) for o in raw]


def _build_delta(removed: list[str] | None = None) -> SceneStateDelta:
    return SceneStateDelta(removed=removed or [])


async def create(
    client: BlenderTransport,
    name: str = "Scene",
    fps: int = 24,
) -> SceneCreateResult:
    """创建场景"""
    response = await client.send(
        BlenderCommand(tool="scene.create", params={"name": name, "fps": fps})
    )
    if response.success and response.result:
        return SceneCreateResult(
            success=True,
            name=response.result["name"],
            fps=response.result["fps"],
        )
    return SceneCreateResult(success=False, error=response.error)


async def clear(client: BlenderTransport) -> SceneClearResult:
    """清空场景"""
    response = await client.send(BlenderCommand(tool="scene.clear"))
    if response.success:
        reset()
        return SceneClearResult(
            success=True,
            scene_state_delta=_build_delta(removed=response.deleted_objects),
        )
    return SceneClearResult(success=False, error=response.error)


async def get_state_tool(client: BlenderTransport) -> SceneGetStateResult:
    """获取场景状态并同步到本地"""
    response = await client.send(BlenderCommand(tool="scene.get_state"))
    if response.success and response.result:
        reset()
        state = get_state()

        objects = _parse_objects(response.result["objects"])
        for obj in objects:
            state.add_object(obj)

        state.frame_current = response.result["frame_current"]
        state.frame_start = response.result["frame_start"]
        state.frame_end = response.result["frame_end"]

        return SceneGetStateResult(
            success=True,
            objects=objects,
            frame_start=state.frame_start,
            frame_end=state.frame_end,
            frame_current=state.frame_current,
        )
    return SceneGetStateResult(success=False, error=response.error)
