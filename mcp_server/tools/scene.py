


async def create():
    """Create Scene"""
    from mcp_server.bridge.blender_client import BlenderClient
    client = BlenderClient()
    result = await client.send({"tool": "system.ping", "params": {}})
    return result

def clear():
    TODO


def get_state():
    TODO