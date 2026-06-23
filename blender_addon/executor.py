def execute(command: dict) -> dict:
    tool   = command.get("tool")
    params = command.get("params", {})

    handlers = {
        "system.ping": _ping,
    }

    handler = handlers.get(tool)
    if not handler:
        return {
            "success": False,
            "error": {
                "code": "UNKNOWN_TOOL",
                "message": f"未知工具: {tool}",
                "available_tools": list(handlers.keys())
            }
        }
    return handler(params)

def _ping(params):
    import bpy
    return {
        "success": True,
        "result": {
            "status": "pong",
            "blender_version": ".".join(str(v) for v in bpy.app.version)
        }
    }