# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tool-code for listing opacity keyframes on a Grease Pencil layer (GPv3).
"""

__all__ = (
    "Params",
    "Result",
    "main",
)

from typing import Any, NamedTuple

# @include_begin: _template_tool_error.py
# @include_end


class Params(NamedTuple):
    object_name: str
    layer_name: str


class Result(NamedTuple):
    status: str
    object_name: str
    layer_name: str
    keyframes: list[dict[str, Any]]


def _get_gp_object_names() -> list[str]:
    import bpy  # pylint: disable=import-error,no-name-in-module
    return sorted(
        obj.name for obj in bpy.data.objects if obj.type == "GREASEPENCIL"
    )


def main(params: Params) -> "Result | ErrorResult":
    import bpy  # pylint: disable=import-error,no-name-in-module

    obj = bpy.data.objects.get(params.object_name)
    if obj is None:
        return ErrorResult(
            status="error",
            error_code="OBJECT_NOT_FOUND",
            message="Object {!r} not found.".format(params.object_name),
            current_state={"available_gp_objects": _get_gp_object_names()},
            hint=(
                "Use `gp_object_create` to create a Grease Pencil object, "
                "or pick from `current_state.available_gp_objects`."
            ),
        )

    if obj.type != "GREASEPENCIL":
        return ErrorResult(
            status="error",
            error_code="INVALID_OBJECT_TYPE",
            message="Object {!r} is type {!r}, expected 'GREASEPENCIL'.".format(
                params.object_name, obj.type
            ),
            current_state={"available_gp_objects": _get_gp_object_names()},
            hint="Pick a Grease Pencil object from `current_state.available_gp_objects`.",
        )

    layer = obj.data.layers.get(params.layer_name)
    if layer is None:
        available = [la.name for la in obj.data.layers]
        return ErrorResult(
            status="error",
            error_code="LAYER_NOT_FOUND",
            message="Layer {!r} not found on object {!r}.".format(
                params.layer_name, params.object_name
            ),
            current_state={"available_layers": available},
            hint=(
                "Use `gp_layer_create` to create a layer, "
                "or pick from `current_state.available_layers`."
            ),
        )

    keyframes: list[dict[str, Any]] = []
    gp_data = obj.data
    anim_data = gp_data.animation_data

    if anim_data and anim_data.action:
        target_path = layer.path_from_id("opacity")
        for fcurve in anim_data.action.fcurves:
            if fcurve.data_path == target_path:
                for kp in fcurve.keyframe_points:
                    keyframes.append({
                        "frame": int(round(kp.co[0])),
                        "opacity": round(float(kp.co[1]), 6),
                    })
                break

    keyframes.sort(key=lambda k: k["frame"])

    return Result(
        status="ok",
        object_name=obj.name,
        layer_name=layer.name,
        keyframes=keyframes,
    )
