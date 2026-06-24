from __future__ import annotations

from typing import Protocol

from mcp_server.models.blender import BlenderCommand, BlenderResponse


class BlenderTransport(Protocol):
    async def send(self, command: BlenderCommand) -> BlenderResponse: ...
