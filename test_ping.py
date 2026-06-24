#!/usr/bin/env python3
"""Simple script to test connection to Blender"""
import asyncio
import sys
from mcp_server.bridge.blender_client import BlenderClient

async def ping_blender():
    """Ping Blender to check if it's connected and running"""
    print("Pinging Blender...")
    client = BlenderClient()
    result = await client.send({"tool": "system.ping", "params": {}})

    if result.get("success"):
        blender_version = result.get("result", {}).get("blender_version", "unknown")
        status = result.get("result", {}).get("status", "unknown")
        print(f"[SUCCESS] Blender is connected")
        print(f"   Status: {status}")
        print(f"   Blender Version: {blender_version}")
        return 0
    else:
        error = result.get("error", {})
        error_code = error.get("code", "UNKNOWN")
        error_message = error.get("message", "Unknown error")
        print(f"[FAILED] Could not connect to Blender")
        print(f"   Error Code: {error_code}")
        print(f"   Error Message: {error_message}")
        print("\nMake sure:")
        print("   1. Blender is running")
        print("   2. The MCP addon is installed and enabled")
        print("   3. The addon's TCP server is running on port 7890")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(ping_blender())
    sys.exit(exit_code)
