bl_info = {
    "name": "Animation MCP Runtime",
    "author": "yourname",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "category": "Animation",
}

import bpy
from . import server

def register():
    server.start()

def unregister():
    server.stop()