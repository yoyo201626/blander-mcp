from mcp.server.fastmcp import FastMCP

app = FastMCP("blender-animation-mcp")

@app.tool()
async def system_ping() -> dict:
    """Ping Blender to check connection."""
    from mcp_server.bridge.blender_client import BlenderClient
    client = BlenderClient()
    result = await client.send({"tool": "system.ping", "params": {}})
    return result

if __name__ == "__main__":
    app.run()
