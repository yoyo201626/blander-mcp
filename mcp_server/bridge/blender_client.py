import asyncio, json

BLENDER_HOST = "127.0.0.1"
BLENDER_PORT = 7890

class BlenderClient:
    async def send(self, command: dict) -> dict:
        try:
            reader, writer = await asyncio.open_connection(BLENDER_HOST, BLENDER_PORT)
            payload = json.dumps(command).encode() + b"\n"
            writer.write(payload)
            await writer.drain()
            data = await reader.readline()
            writer.close()
            await writer.wait_closed()
            return json.loads(data.decode())
        except ConnectionRefusedError:
            return {
                "success": False,
                "error": {
                    "code": "BLENDER_NOT_CONNECTED",
                    "message": "无法连接到 Blender Addon，请确认 Blender 已打开且 Addon 已启用。"
                }
            }