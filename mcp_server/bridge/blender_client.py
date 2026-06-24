import asyncio
import json

from mcp_server.models.blender import BlenderCommand, BlenderError, BlenderResponse

BLENDER_HOST = "127.0.0.1"
BLENDER_PORT = 7890


class BlenderClient:
    async def send(self, command: BlenderCommand) -> BlenderResponse:
        try:
            reader, writer = await asyncio.open_connection(
                BLENDER_HOST, BLENDER_PORT
            )
            payload = json.dumps(command.model_dump()).encode() + b"\n"
            writer.write(payload)
            await writer.drain()
            data = await reader.readline()
            writer.close()
            await writer.wait_closed()
            return BlenderResponse.model_validate(json.loads(data.decode()))
        except ConnectionRefusedError:
            return BlenderResponse(
                success=False,
                error=BlenderError(
                    code="BLENDER_NOT_CONNECTED",
                    message=(
                        "无法连接到 Blender Addon，"
                        "请确认 Blender 已打开且 Addon 已启用。"
                    ),
                ),
            )
