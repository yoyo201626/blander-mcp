import asyncio

from mcp.server import Server
from mcp.server.stdio import stdio_server

from mcp_server.bridge.blender_client import BlenderClient
from mcp_server.models.blender import BlenderCommand
from mcp_server.models.scene import PingResult

app = Server("blender-animation-mcp")


@app.tool()
async def system_ping() -> dict:
    """Ping Blender to check connection."""
    client = BlenderClient()
    response = await client.send(BlenderCommand(tool="system.ping"))
    if response.success and response.result:
        return PingResult(
            success=True,
            status=response.result["status"],
            blender_version=response.result["blender_version"],
        ).model_dump()
    return PingResult(success=False, error=response.error).model_dump()


@app.tool()
async def scene_create(name: str = "Scene", fps: int = 24) -> dict:
    """创建或配置场景"""
    from mcp_server.tools import scene
    return (await scene.create(BlenderClient(), name, fps)).model_dump()


@app.tool()
async def scene_clear() -> dict:
    """清空场景中的所有对象"""
    from mcp_server.tools import scene
    return (await scene.clear(BlenderClient())).model_dump()


@app.tool()
async def scene_get_state() -> dict:
    """获取当前场景状态"""
    from mcp_server.tools import scene
    return (await scene.get_state_tool(BlenderClient())).model_dump()


async def main() -> None:
    async with stdio_server() as streams:
        await app.run(
            streams[0], streams[1], app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
