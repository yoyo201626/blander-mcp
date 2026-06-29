# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

# pylint: disable=C0114  # See tool doc-string.

__all__ = (
    "register",
)

from blmcp.tools_helpers import (
    toolcode_format_call,
    toolcode_load_from_filepath,
    toolcode_wrap_with_calling_convention,
)
from blmcp.tools_helpers.connection import send_code
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error,no-name-in-module
from mcp.types import ToolAnnotations  # pylint: disable=import-error,no-name-in-module

_TOOL_CALL = toolcode_wrap_with_calling_convention(toolcode_load_from_filepath(__file__))


def register(mcp: FastMCP) -> None:
    @mcp.tool(
        annotations=ToolAnnotations(
            title="Draw Grease Pencil Shape",
            destructiveHint=True,
        )
    )
    def gp_shape_draw(
        object_name: str,
        layer_name: str,
        frame: int,
        shape: str,
        cx: float = 0.0,
        cy: float = 0.0,
        cz: float = 0.0,
        radius: float = 1.0,
        width: float = 2.0,
        height: float = 2.0,
        segments: int = 32,
        mode: str = "replace",
        stroke_radius: float = 0.01,
        material_index: int = 0,
    ) -> dict[str, object]:
        """
        Draw a predefined geometric shape on a Grease Pencil layer (GPv3).

        ``shape`` must be one of ``"rect"`` or ``"circle"``.

        For ``"rect"``: a closed rectangle centred at (cx, cy, cz) in
        the XZ plane. ``width`` is the total X-extent; ``height`` is
        the total Z-extent. Both default to ``2.0``.

        For ``"circle"``: a polygon approximation of a circle centred
        at (cx, cy, cz) in the XZ plane. ``radius`` controls size
        (default ``1.0``); ``segments`` controls smoothness (default
        ``32``).

        For freeform polylines or paths, use ``gp_stroke_draw`` instead.

        ``mode`` controls existing strokes on the frame:

        - ``"replace"``: clears all strokes before drawing.
        - ``"append"``: adds the shape alongside existing strokes.

        ``stroke_radius`` is the point radius in object-space units
        (controls stroke thickness, default ``0.01``).
        ``material_index`` selects the GP material slot (0-based).

        Returns an error if the object, layer, shape, or mode is invalid.
        """
        params = {
            "object_name": object_name,
            "layer_name": layer_name,
            "frame": frame,
            "shape": shape,
            "cx": cx,
            "cy": cy,
            "cz": cz,
            "radius": radius,
            "width": width,
            "height": height,
            "segments": segments,
            "mode": mode,
            "stroke_radius": stroke_radius,
            "material_index": material_index,
        }
        return send_code(toolcode_format_call(_TOOL_CALL, params), strict_json=True)
