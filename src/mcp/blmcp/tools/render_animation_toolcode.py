# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Tool-code for rendering a frame sequence and writing a video file.

Video output uses Blender 5.1's ``media_type = 'VIDEO'`` API with an
H.264 / MPEG-4 codec.  Older Blender builds that expose ``file_format``
instead of ``media_type`` fall back to ``file_format = 'FFMPEG'``.
All settings are restored after the render.
"""

__all__ = (
    "Params",
    "Result",
    "main",
)

import contextlib
import typing
from collections.abc import Callable
from typing import NamedTuple


class Params(NamedTuple):
    output_path: str
    frame_start: int | None = None
    frame_end: int | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None


class Result(NamedTuple):
    status: str
    filepath: str | None = None
    frame_start: int | None = None
    frame_end: int | None = None
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    message: str | None = None


# @include_begin: _template_backup_attrs_and_assign_multi.py
@contextlib.contextmanager
def _backup_attrs_and_assign_multi(
        *obj_attrs: tuple[object, dict[str, object]],
) -> typing.Generator[None, None, None]:
    yield
# @include_end


# @include_begin: _template_deferred_tool_check_for_file_output.py
def _deferred_tool_check_for_file_output(
        job_type: str,
        output_path: str,
        restore_attrs: list[tuple[object, str, object]] | None = None,
) -> Callable[[], dict[str, object] | None]:
    return lambda: None
# @include_end


def main(params: Params) -> "Result | Callable[[], dict[str, object] | None]":
    import os
    import bpy  # pylint: disable=import-error,no-name-in-module

    use_deferred = not bpy.app.background
    scene = bpy.context.scene
    rd = scene.render
    image_settings = rd.image_settings

    # Resolve output path: absolute paths are used as-is; relative paths
    # are placed inside the MCP scratch directory.
    if os.path.isabs(params.output_path):
        output_path = params.output_path
    else:
        output_path = os.path.join(
            bpy.app.tempdir,
            "blender_mcp",
            os.path.basename(params.output_path),
        )
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # Build attribute overrides for temporary settings changes.
    obj_attrs: list[tuple[object, dict[str, object]]] = []

    # Optional frame-range overrides.
    scene_attrs: dict[str, object] = {}
    if params.frame_start is not None:
        scene_attrs["frame_start"] = params.frame_start
    if params.frame_end is not None:
        scene_attrs["frame_end"] = params.frame_end
    if scene_attrs:
        obj_attrs.append((scene, scene_attrs))

    # Optional resolution / fps overrides.
    rd_attrs: dict[str, object] = {}
    if params.width is not None and params.width > 0:
        rd_attrs["resolution_x"] = params.width
    if params.height is not None and params.height > 0:
        rd_attrs["resolution_y"] = params.height
    if rd_attrs:
        rd_attrs["resolution_percentage"] = 100
    if params.fps is not None and params.fps > 0:
        rd_attrs["fps"] = params.fps
        rd_attrs["fps_base"] = 1
    if rd_attrs:
        obj_attrs.append((rd, rd_attrs))

    # Video output format.
    # Blender 5.1+: image_settings.media_type = 'VIDEO'
    # Older builds:  image_settings.file_format = 'FFMPEG'
    is_attrs: dict[str, object] = {}
    if hasattr(image_settings, "media_type"):
        is_attrs["media_type"] = "VIDEO"
    else:
        is_attrs["file_format"] = "FFMPEG"
    obj_attrs.append((image_settings, is_attrs))

    # Codec settings (H.264 in MPEG-4 container, no audio).
    # These attributes exist on both old and new Blender builds.
    ffmpeg = rd.ffmpeg
    ffmpeg_attrs: dict[str, object] = {}
    for attr, value in [("format", "MPEG4"), ("codec", "H264"), ("audio_codec", "NONE")]:
        if hasattr(ffmpeg, attr):
            ffmpeg_attrs[attr] = value
    if ffmpeg_attrs:
        obj_attrs.append((ffmpeg, ffmpeg_attrs))

    # NOTE: `filepath` is saved/restored manually (not via the context
    # manager) because the animation render reads it after completion.
    # With `INVOKE_DEFAULT` the context manager would restore it too early.
    orig_filepath = rd.filepath
    rd.filepath = output_path

    render_args: tuple[str, ...] = ('INVOKE_DEFAULT',) if use_deferred else ()

    with _backup_attrs_and_assign_multi(*obj_attrs):
        actual_start = scene.frame_start
        actual_end = scene.frame_end
        actual_w = rd.resolution_x
        actual_h = rd.resolution_y
        actual_fps = rd.fps
        try:
            bpy.ops.render.render(*render_args, animation=True)
        except RuntimeError as ex:
            rd.filepath = orig_filepath
            return Result(status="error", message=str(ex))

    if use_deferred:
        return _deferred_tool_check_for_file_output(
            'RENDER', output_path,
            restore_attrs=[(rd, "filepath", orig_filepath)],
        )

    rd.filepath = orig_filepath
    return Result(
        status="ok",
        filepath=output_path,
        frame_start=actual_start,
        frame_end=actual_end,
        width=actual_w,
        height=actual_h,
        fps=actual_fps,
    )
