from mcp.server import Server
from mcp.server.stdio import stdio_server
import asyncio

app = Server("blender-animation-mcp")

@app.tool()
async def system_ping() -> dict:
    """Ping Blender to check connection."""
    from mcp_server.bridge.blender_client import BlenderClient
    client = BlenderClient()
    result = await client.send({"tool": "system.ping", "params": {}})
    return result

async def main():
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())