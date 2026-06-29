# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Checks that the MCP server exposes the expected tool listing.
"""

__all__ = ()

import asyncio
import os
import sys
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Root of the repository.
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Complete expected tool listing.
# When a tool is added, changed, or removed this must be updated.
# Run with `--update` to regenerate from a live server query.

# BEGIN: EXPECTED_TOOLS
EXPECTED_TOOLS = [
    {
        "name": "execute_blender_code",
        "description": "\n"
        "Execute Python code in the connected Blender instance.\n"
        "\n"
        "The code runs in Blender's Python environment with full access to ``bpy``.\n"
        "To return data, assign a JSON-serialisable dict to a variable named ``result``.\n"
        "Deferred completion via ``check_is_finished`` is only supported by the\n"
        "interactive addon server, and is rejected in background mode.\n",
        "inputSchema": {
            "properties": {
                "code": {
                    "title": "Code",
                    "type": "string"
                }
            },
            "required": [
                "code"
            ],
            "title": "execute_blender_codeArguments",
            "type": "object"
        }
    },
    {
        "name": "execute_blender_code_for_cli",
        "description": "\n"
        "Execute Python code in a background Blender process.\n"
        "\n"
        "Opens *blend_file* with ``blender --background`` and runs *code*.\n"
        "Assign a dict to ``result`` to return data.\n",
        "inputSchema": {
            "properties": {
                "blend_file": {
                    "title": "Blend File",
                    "type": "string"
                },
                "code": {
                    "title": "Code",
                    "type": "string"
                }
            },
            "required": [
                "blend_file",
                "code"
            ],
            "title": "execute_blender_code_for_cliArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_datablocks",
        "description": "\n"
        "Return a summary of the blend file: data-block counts, active workspace, and render engine.\n",
        "inputSchema": {
            "properties": {},
            "title": "get_blendfile_summary_datablocksArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_datablocks_for_cli",
        "description": "\n"
        "Return a data-block summary by opening *blend_file* in background Blender.\n",
        "inputSchema": {
            "properties": {
                "blend_file": {
                    "title": "Blend File",
                    "type": "string"
                }
            },
            "required": [
                "blend_file"
            ],
            "title": "get_blendfile_summary_datablocks_for_cliArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_missing_files",
        "description": "\n"
        "Report external file references that are missing from disk\n"
        "(images, libraries, fonts, sounds, movie clips, caches, sequences).\n",
        "inputSchema": {
            "properties": {},
            "title": "get_blendfile_summary_missing_filesArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_missing_files_for_cli",
        "description": "\n"
        "Report missing file references by opening *blend_file* in background Blender.\n",
        "inputSchema": {
            "properties": {
                "blend_file": {
                    "title": "Blend File",
                    "type": "string"
                }
            },
            "required": [
                "blend_file"
            ],
            "title": "get_blendfile_summary_missing_files_for_cliArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_of_linked_libraries",
        "description": "\n"
        "Return a tree of directly and indirectly linked library files.\n",
        "inputSchema": {
            "properties": {},
            "title": "get_blendfile_summary_of_linked_librariesArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_of_linked_libraries_for_cli",
        "description": "\n"
        "Return linked-library info by opening *blend_file* in background Blender.\n",
        "inputSchema": {
            "properties": {
                "blend_file": {
                    "title": "Blend File",
                    "type": "string"
                }
            },
            "required": [
                "blend_file"
            ],
            "title": "get_blendfile_summary_of_linked_libraries_for_cliArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_path_info",
        "description": "\n"
        "Simple/fast access to the blend file's path, save status, age, and backups.\n",
        "inputSchema": {
            "properties": {},
            "title": "get_blendfile_summary_path_infoArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_path_info_for_cli",
        "description": "\n"
        "Return path info by opening *blend_file* in background Blender.\n",
        "inputSchema": {
            "properties": {
                "blend_file": {
                    "title": "Blend File",
                    "type": "string"
                }
            },
            "required": [
                "blend_file"
            ],
            "title": "get_blendfile_summary_path_info_for_cliArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_usage_guess",
        "description": "\n"
        "Guess the primary use-cases of the current blend file (scored 0-100 with certainty).\n",
        "inputSchema": {
            "properties": {},
            "title": "get_blendfile_summary_usage_guessArguments",
            "type": "object"
        }
    },
    {
        "name": "get_blendfile_summary_usage_guess_for_cli",
        "description": "\n"
        "Guess use-cases by opening *blend_file* in background Blender.\n",
        "inputSchema": {
            "properties": {
                "blend_file": {
                    "title": "Blend File",
                    "type": "string"
                }
            },
            "required": [
                "blend_file"
            ],
            "title": "get_blendfile_summary_usage_guess_for_cliArguments",
            "type": "object"
        }
    },
    {
        "name": "get_object_detail_summary",
        "description": "\n"
        "Return a structured summary of the object identified by *name*.\n"
        "\n"
        "Includes type, transforms, parent, children, modifiers, constraints,\n"
        "materials, visibility, data-block name, and collections.\n",
        "inputSchema": {
            "properties": {
                "name": {
                    "title": "Name",
                    "type": "string"
                }
            },
            "required": [
                "name"
            ],
            "title": "get_object_detail_summaryArguments",
            "type": "object"
        }
    },
    {
        "name": "get_objects_summary",
        "description": "\n"
        "Return the scene's collection hierarchy and their objects.\n"
        "\n"
        "Each collection lists its objects (name, type, parent, data name,\n"
        "selection, visibility) and nested child collections.\n",
        "inputSchema": {
            "properties": {},
            "title": "get_objects_summaryArguments",
            "type": "object"
        }
    },
    {
        "name": "get_python_api_docs",
        "description": "\n"
        "Return the Blender Python API docs for *identifier*, or list\n"
        "modules matching a trailing-``*`` discovery pattern.\n"
        "\n"
        "*identifier* should be a fully-qualified Python name (e.g.\n"
        "``bpy.app`` or ``bpy.types.Scene.frame_current``).\n"
        "The trailing-``*`` forms are supported as discovery entry-points:\n"
        "\n"
        "- ``*`` enumerates the top-level modules (``bpy``, ``bmesh``,\n"
        "  ``mathutils``, ``gpu``, ...).\n"
        "- ``X.*`` enumerates the direct-child identifiers under the\n"
        "  *X* namespace (``bpy.*`` -> ``bpy.app``, ``bpy.context``, ...).\n"
        "\n"
        "Both return a ``namespace`` response even when ``X.rst`` would\n"
        "otherwise resolve to ``exact``; the ``.*`` form lets an agent\n"
        "force the child listing.\n"
        "\n"
        "The response always carries ``kind``, ``found``, and ``identifier``.\n"
        "The remaining keys depend on ``kind``:\n"
        "\n"
        "- ``\"exact\"`` (``found=True``): ``<identifier>.rst`` was read.\n"
        "  Extra keys: ``content`` (RST text), ``examples``. When the\n"
        "  file exceeds 32 KB, ``content`` is replaced with a dot-point\n"
        "  summary of the file's top-level definitions (prefixed by a\n"
        "  header noting the truncation) and ``examples`` is empty -\n"
        "  re-query individual members for their rendered blocks.\n"
        "- ``\"namespace\"`` (``found=True``):\n"
        "  no ``<identifier>.rst`` but ``<identifier>.<child>.rst`` siblings exist.\n"
        "  Extra key: ``submodules`` (list of child identifiers).\n"
        "- ``\"definition\"`` (``found=True``):\n"
        "  *identifier* is defined inside a parent RST\n"
        "  (e.g. ``bpy.props.IntProperty`` lives in ``bpy.props.rst``).\n"
        "  Extra keys: ``content`` (rendered block), ``examples``.\n"
        "- ``\"partial\"`` (``found=False``):\n"
        "  the parent RST was located but the trailing component isn't defined in it.\n"
        "  Extra keys:\n"
        "  - ``parent`` the identifier whose RST was loaded.\n"
        "  - ``available`` top-level definitions in that RST.\n"
        "  - ``submodules`` sibling identifiers ``<parent>.<child>`` with their own RSTs,\n"
        "    filtered to those whose last component contains every character of the missing tail.\n"
        "\n"
        "  For a toctree landing page like ``bpy.types`` ``available`` is empty and ``submodules``\n"
        "  is the near-miss list; for a self-contained module like ``bpy.props`` it's the reverse.\n"
        "- ``\"suggestions\"`` (``found=False``):\n"
        "  no direct match, but *identifier* appears as a component of other files.\n"
        "  Extra key: ``suggestions`` (list of full identifiers).\n"
        "- ``\"missing\"`` (``found=False``): nothing matched.\n"
        "\n"
        "``examples`` (present on the ``exact`` and ``definition`` kinds)\n"
        "is a list of ``{path, content}`` entries referenced from this documentation.\n",
        "inputSchema": {
            "properties": {
                "identifier": {
                    "title": "Identifier",
                    "type": "string"
                }
            },
            "required": [
                "identifier"
            ],
            "title": "get_python_api_docsArguments",
            "type": "object"
        }
    },
    {
        "name": "get_scene_state",
        "description": "\n"
        "Return the current scene's timeline parameters and a flat list of\n"
        "all objects with their name, type, and world-space location.\n"
        "\n"
        "Includes ``frame_start``, ``frame_end``, ``frame_current``, and\n"
        "``fps`` so the AI can plan keyframe placement without a separate\n"
        "query. Works in both background and interactive Blender sessions.\n"
        "\n"
        "Call this at the start of any animation workflow to understand\n"
        "the scene layout and timeline before issuing further tool calls.\n",
        "inputSchema": {
            "properties": {},
            "title": "get_scene_stateArguments",
            "type": "object"
        }
    },
    {
        "name": "get_screenshot_of_area_as_image",
        "description": "\n"
        "Take a screenshot of a single Blender area and return it as a PNG image.\n"
        "\n"
        "*area_ui_type* matches the area's ``ui_type``.\n"
        "\n"
        "*size_limit_in_bytes* caps the image size in bytes.\n"
        "Zero (the default) uses the MCP message size limit.\n",
        "inputSchema": {
            "properties": {
                "area_ui_type": {
                    "enum": [
                        "VIEW_3D",
                        "IMAGE_EDITOR",
                        "UV",
                        "ShaderNodeTree",
                        "CompositorNodeTree",
                        "GeometryNodeTree",
                        "TextureNodeTree",
                        "SEQUENCE_EDITOR",
                        "CLIP_EDITOR",
                        "DOPESHEET_EDITOR",
                        "GRAPH_EDITOR",
                        "NLA_EDITOR",
                        "TEXT_EDITOR",
                        "CONSOLE",
                        "INFO",
                        "TOPBAR",
                        "STATUSBAR",
                        "OUTLINER",
                        "PROPERTIES",
                        "FILE_BROWSER",
                        "SPREADSHEET",
                        "PREFERENCES"
                    ],
                    "title": "Area Ui Type",
                    "type": "string"
                },
                "size_limit_in_bytes": {
                    "default": 0,
                    "title": "Size Limit In Bytes",
                    "type": "integer"
                }
            },
            "required": [
                "area_ui_type"
            ],
            "title": "get_screenshot_of_area_as_imageArguments",
            "type": "object"
        }
    },
    {
        "name": "get_screenshot_of_window_as_image",
        "description": "\n"
        "Take a screenshot of the entire Blender window and return it as a PNG image.\n"
        "\n"
        "*size_limit_in_bytes* caps the image size in bytes.\n"
        "Zero (the default) uses the MCP message size limit.\n",
        "inputSchema": {
            "properties": {
                "size_limit_in_bytes": {
                    "default": 0,
                    "title": "Size Limit In Bytes",
                    "type": "integer"
                }
            },
            "title": "get_screenshot_of_window_as_imageArguments",
            "type": "object"
        }
    },
    {
        "name": "get_screenshot_of_window_as_json",
        "description": "\n"
        "Return a JSON description of the Blender window layout, areas, active object, and selection.\n",
        "inputSchema": {
            "properties": {},
            "title": "get_screenshot_of_window_as_jsonArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_layer_create",
        "description": "\n"
        "Add a new layer to an existing Grease Pencil object.\n"
        "\n"
        "``object_name`` must refer to a ``GREASEPENCIL`` type object\n"
        "already in the scene (use ``gp_object_create`` to create one).\n"
        "``layer_name`` is the display name of the new layer.\n"
        "\n"
        "Returns an error if the object is not found or is not a\n"
        "Grease Pencil object. Duplicate layer names are allowed by\n"
        "Blender and are not treated as errors.\n",
        "inputSchema": {
            "properties": {
                "object_name": {
                    "title": "Object Name",
                    "type": "string"
                },
                "layer_name": {
                    "default": "Layer",
                    "title": "Layer Name",
                    "type": "string"
                }
            },
            "required": [
                "object_name"
            ],
            "title": "gp_layer_createArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_layer_delete",
        "description": "\n"
        "Remove a layer from a Grease Pencil object.\n"
        "\n"
        "All strokes and keyframes stored on the layer are permanently\n"
        "deleted. Use ``gp_layers_list`` first to verify the layer name.\n"
        "\n"
        "Returns an error if the object or layer is not found.\n",
        "inputSchema": {
            "properties": {
                "object_name": {
                    "title": "Object Name",
                    "type": "string"
                },
                "layer_name": {
                    "title": "Layer Name",
                    "type": "string"
                }
            },
            "required": [
                "object_name",
                "layer_name"
            ],
            "title": "gp_layer_deleteArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_layers_list",
        "description": "\n"
        "Return all layers on a Grease Pencil object in their stack order.\n"
        "\n"
        "Each layer entry contains ``name``, ``opacity``, and ``hide``.\n"
        "Layers are listed top-to-bottom as they appear in Blender's\n"
        "layer panel (index 0 = topmost layer).\n"
        "\n"
        "Returns an error if the object is not found or is not a\n"
        "Grease Pencil object.\n",
        "inputSchema": {
            "properties": {
                "object_name": {
                    "title": "Object Name",
                    "type": "string"
                }
            },
            "required": [
                "object_name"
            ],
            "title": "gp_layers_listArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_material_assign",
        "description": "\n"
        "Assign a Grease Pencil material to a GP object's material slots.\n"
        "\n"
        "If the material is already in a slot on ``object_name``, the\n"
        "existing ``slot_index`` is returned without creating a duplicate.\n"
        "Otherwise the material is appended to the end of the slot list.\n"
        "\n"
        "The returned ``slot_index`` (0-based) is the value to pass as\n"
        "``material_index`` when calling ``gp_stroke_draw`` or\n"
        "``gp_shape_draw``.\n"
        "\n"
        "Returns an error if the object is not found, is not a Grease\n"
        "Pencil object, or the material does not exist or is not a GP\n"
        "material (use ``gp_material_create`` to make one).\n",
        "inputSchema": {
            "properties": {
                "object_name": {
                    "title": "Object Name",
                    "type": "string"
                },
                "material_name": {
                    "title": "Material Name",
                    "type": "string"
                }
            },
            "required": [
                "object_name",
                "material_name"
            ],
            "title": "gp_material_assignArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_material_create",
        "description": "\n"
        "Create a Grease Pencil material with stroke and fill colors (GPv3).\n"
        "\n"
        "Colors are RGBA lists with values in ``[0.0, 1.0]``:\n"
        "\n"
        "- ``stroke_color``: outline color, default opaque black\n"
        "  ``[0.0, 0.0, 0.0, 1.0]``.\n"
        "- ``fill_color``: interior fill color, default fully transparent\n"
        "  ``[1.0, 1.0, 1.0, 0.0]``.  Set alpha ``> 0`` to make fill\n"
        "  visible.\n"
        "\n"
        "Blender uses **linear** color space internally; the values you\n"
        "provide are treated as linear, not sRGB.  Pure black\n"
        "``[0, 0, 0, 1]`` and pure white ``[1, 1, 1, 1]`` are\n"
        "unaffected; intermediate colors will appear slightly different\n"
        "from sRGB equivalents.\n"
        "\n"
        "After creation, assign the material to a GP object with\n"
        "``gp_material_assign``, then reference it by slot index when\n"
        "drawing strokes via ``gp_stroke_draw`` or ``gp_shape_draw``.\n"
        "\n"
        "The returned ``name`` is the actual name Blender assigned\n"
        "(may differ if a material with that name already exists).\n",
        "inputSchema": {
            "properties": {
                "name": {
                    "default": "GPMaterial",
                    "title": "Name",
                    "type": "string"
                },
                "stroke_color": {
                    "default": [0.0, 0.0, 0.0, 1.0],
                    "items": {
                        "type": "number"
                    },
                    "title": "Stroke Color",
                    "type": "array"
                },
                "fill_color": {
                    "default": [1.0, 1.0, 1.0, 0.0],
                    "items": {
                        "type": "number"
                    },
                    "title": "Fill Color",
                    "type": "array"
                }
            },
            "title": "gp_material_createArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_object_create",
        "description": "\n"
        "Create a new Grease Pencil object in the active scene.\n"
        "\n"
        "Blender deduplicates names automatically: if an object named\n"
        "``name`` already exists, the new object receives a ``.001`` suffix\n"
        "(or the next available number). The returned ``name`` field always\n"
        "reflects the actual name assigned by Blender.\n"
        "\n"
        "The object is linked to the scene's root collection.\n"
        "Call ``gp_layer_create`` next to add at least one drawing layer.\n",
        "inputSchema": {
            "properties": {
                "name": {
                    "default": "GreasePencil",
                    "title": "Name",
                    "type": "string"
                }
            },
            "title": "gp_object_createArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_shape_draw",
        "description": "\n"
        "Draw a predefined geometric shape on a Grease Pencil layer (GPv3).\n"
        "\n"
        "``shape`` must be one of ``\"rect\"`` or ``\"circle\"``.\n"
        "\n"
        "For ``\"rect\"``: a closed rectangle centred at (cx, cy, cz) in\n"
        "the XZ plane. ``width`` is the total X-extent; ``height`` is\n"
        "the total Z-extent. Both default to ``2.0``.\n"
        "\n"
        "For ``\"circle\"``: a polygon approximation of a circle centred\n"
        "at (cx, cy, cz) in the XZ plane. ``radius`` controls size\n"
        "(default ``1.0``); ``segments`` controls smoothness (default\n"
        "``32``).\n"
        "\n"
        "For freeform polylines or paths, use ``gp_stroke_draw`` instead.\n"
        "\n"
        "``mode`` controls existing strokes on the frame:\n"
        "\n"
        "- ``\"replace\"``: clears all strokes before drawing.\n"
        "- ``\"append\"``: adds the shape alongside existing strokes.\n"
        "\n"
        "``stroke_radius`` is the point radius in object-space units\n"
        "(controls stroke thickness, default ``0.01``).\n"
        "``material_index`` selects the GP material slot (0-based).\n"
        "\n"
        "Returns an error if the object, layer, shape, or mode is invalid.\n",
        "inputSchema": {
            "properties": {
                "object_name": {
                    "title": "Object Name",
                    "type": "string"
                },
                "layer_name": {
                    "title": "Layer Name",
                    "type": "string"
                },
                "frame": {
                    "title": "Frame",
                    "type": "integer"
                },
                "shape": {
                    "title": "Shape",
                    "type": "string"
                },
                "cx": {
                    "default": 0.0,
                    "title": "Cx",
                    "type": "number"
                },
                "cy": {
                    "default": 0.0,
                    "title": "Cy",
                    "type": "number"
                },
                "cz": {
                    "default": 0.0,
                    "title": "Cz",
                    "type": "number"
                },
                "radius": {
                    "default": 1.0,
                    "title": "Radius",
                    "type": "number"
                },
                "width": {
                    "default": 2.0,
                    "title": "Width",
                    "type": "number"
                },
                "height": {
                    "default": 2.0,
                    "title": "Height",
                    "type": "number"
                },
                "segments": {
                    "default": 32,
                    "title": "Segments",
                    "type": "integer"
                },
                "mode": {
                    "default": "replace",
                    "title": "Mode",
                    "type": "string"
                },
                "stroke_radius": {
                    "default": 0.01,
                    "title": "Stroke Radius",
                    "type": "number"
                },
                "material_index": {
                    "default": 0,
                    "title": "Material Index",
                    "type": "integer"
                }
            },
            "required": [
                "object_name",
                "layer_name",
                "frame",
                "shape"
            ],
            "title": "gp_shape_drawArguments",
            "type": "object"
        }
    },
    {
        "name": "gp_stroke_draw",
        "description": "\n"
        "Draw a stroke on a Grease Pencil layer at the given frame (GPv3).\n"
        "\n"
        "``points`` is a list of ``[x, y, z]`` coordinates defining the\n"
        "stroke path. Provide two points for a straight line; three or more\n"
        "for a curve or polyline. Blender uses a right-hand coordinate system:\n"
        "X right, Y into the screen, Z up. For 2D animation draw in the XZ\n"
        "plane (Y = 0) and place the camera along -Y.\n"
        "\n"
        "``mode`` controls existing strokes on that frame:\n"
        "\n"
        "- ``\"replace\"``: clears all existing strokes before drawing.\n"
        "- ``\"append\"``: adds the new stroke alongside existing ones.\n"
        "\n"
        "``stroke_radius`` is the point radius in object-space units; it\n"
        "controls stroke thickness (default ``0.01``).\n"
        "\n"
        "``material_index`` selects the GP material slot (0-based).\n"
        "\n"
        "The frame is created automatically if it does not exist.\n"
        "Returns an error if the object, layer, mode, or points are invalid.\n",
        "inputSchema": {
            "properties": {
                "object_name": {
                    "title": "Object Name",
                    "type": "string"
                },
                "layer_name": {
                    "title": "Layer Name",
                    "type": "string"
                },
                "frame": {
                    "title": "Frame",
                    "type": "integer"
                },
                "points": {
                    "items": {
                        "items": {
                            "type": "number"
                        },
                        "type": "array"
                    },
                    "title": "Points",
                    "type": "array"
                },
                "mode": {
                    "default": "replace",
                    "title": "Mode",
                    "type": "string"
                },
                "stroke_radius": {
                    "default": 0.01,
                    "title": "Stroke Radius",
                    "type": "number"
                },
                "material_index": {
                    "default": 0,
                    "title": "Material Index",
                    "type": "integer"
                }
            },
            "required": [
                "object_name",
                "layer_name",
                "frame",
                "points"
            ],
            "title": "gp_stroke_drawArguments",
            "type": "object"
        }
    },
    {
        "name": "jump_to_tab_by_name",
        "description": "\n"
        "Switch the active workspace tab to *name*.\n",
        "inputSchema": {
            "properties": {
                "name": {
                    "title": "Name",
                    "type": "string"
                }
            },
            "required": [
                "name"
            ],
            "title": "jump_to_tab_by_nameArguments",
            "type": "object"
        }
    },
    {
        "name": "jump_to_tab_by_space_type",
        "description": "\n"
        "Switch to a workspace whose main area matches *space_type*.\n"
        "\n"
        "If *allow_edits* is True and no matching workspace exists, a new one\n"
        "is created by duplicating the current workspace.\n",
        "inputSchema": {
            "properties": {
                "space_type": {
                    "title": "Space Type",
                    "type": "string"
                },
                "allow_edits": {
                    "default": False,
                    "title": "Allow Edits",
                    "type": "boolean"
                }
            },
            "required": [
                "space_type"
            ],
            "title": "jump_to_tab_by_space_typeArguments",
            "type": "object"
        }
    },
    {
        "name": "jump_to_view3d_object_by_name",
        "description": "\n"
        "Move the 3D viewport to focus on an object by *name*.\n"
        "\n"
        "If *allow_edits* is True the object may be un-hidden and its\n"
        "collections enabled to make it visible.\n",
        "inputSchema": {
            "properties": {
                "name": {
                    "title": "Name",
                    "type": "string"
                },
                "allow_edits": {
                    "default": False,
                    "title": "Allow Edits",
                    "type": "boolean"
                }
            },
            "required": [
                "name"
            ],
            "title": "jump_to_view3d_object_by_nameArguments",
            "type": "object"
        }
    },
    {
        "name": "jump_to_view3d_object_data_by_name",
        "description": "\n"
        "Move the 3D viewport to the object whose data block matches *name*.\n"
        "\n"
        "If *allow_edits* is True the object may be un-hidden and its\n"
        "collections enabled to make it visible.\n",
        "inputSchema": {
            "properties": {
                "name": {
                    "title": "Name",
                    "type": "string"
                },
                "allow_edits": {
                    "default": False,
                    "title": "Allow Edits",
                    "type": "boolean"
                }
            },
            "required": [
                "name"
            ],
            "title": "jump_to_view3d_object_data_by_nameArguments",
            "type": "object"
        }
    },
    {
        "name": "ping",
        "description": "\n"
        "Verify that Blender is online and return its version string.\n"
        "\n"
        "Call this before other tools to confirm the Blender addon is running.\n"
        "Returns an error if the connection to Blender cannot be established.\n",
        "inputSchema": {
            "properties": {},
            "title": "pingArguments",
            "type": "object"
        }
    },
    {
        "name": "render_thumbnail_to_path",
        "description": "\n"
        "Render a small, low-quality thumbnail to *output_path* (temporarily overrides settings).\n",
        "inputSchema": {
            "properties": {
                "output_path": {
                    "title": "Output Path",
                    "type": "string"
                }
            },
            "required": [
                "output_path"
            ],
            "title": "render_thumbnail_to_pathArguments",
            "type": "object"
        }
    },
    {
        "name": "render_viewport_to_path",
        "description": "\n"
        "Render the current scene to *output_path* using current render settings.\n",
        "inputSchema": {
            "properties": {
                "output_path": {
                    "title": "Output Path",
                    "type": "string"
                }
            },
            "required": [
                "output_path"
            ],
            "title": "render_viewport_to_pathArguments",
            "type": "object"
        }
    },
    {
        "name": "search_api_docs",
        "description": "\n"
        "Full-text search over the bundled Blender Python API reference.\n"
        "\n"
        "Returns a ranked list of hits. Each hit has:\n"
        "\n"
        "- ``path``: file path relative to the bundled docs.\n"
        "- ``text``: the matching paragraph plus ``context``\n"
        "  paragraphs on either side.\n"
        "- ``breadcrumb``: the section path containing the hit\n"
        "  (``Section > Sub-section > ...``).\n"
        "- ``index``: the hit's position in the result list.\n"
        "- ``score``: a relevance score; higher is better.\n"
        "\n"
        "The query is tokenised on whitespace and matched\n"
        "case-insensitively. Every token must appear somewhere in\n"
        "the paragraph body, the file path, or an enclosing section\n"
        "title - in any order. Common English stop-words (``the``,\n"
        "``a``, ``how``, ``to``, ...) are dropped, so natural\n"
        "phrasings like ``\"how to bake\"`` work as expected. Regular\n"
        "expressions are not supported.\n"
        "\n"
        "Use ``context`` to pull more surrounding paragraphs into\n"
        "each hit (symmetric, default 0). Use ``index`` with the\n"
        "position of a previous hit (same query) to get that hit\n"
        "alone with its text widened to its enclosing section.\n"
        "\n"
        "Read-only; consults bundled RST files only.\n",
        "inputSchema": {
            "properties": {
                "query": {
                    "title": "Query",
                    "type": "string"
                },
                "max_results": {
                    "default": 20,
                    "title": "Max Results",
                    "type": "integer"
                },
                "context": {
                    "default": 0,
                    "title": "Context",
                    "type": "integer"
                },
                "index": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"}
                    ],
                    "default": None,
                    "title": "Index"
                }
            },
            "required": [
                "query"
            ],
            "title": "search_api_docsArguments",
            "type": "object"
        }
    },
    {
        "name": "search_manual_docs",
        "description": "\n"
        "Full-text search over the bundled Blender user manual.\n"
        "\n"
        "Returns a ranked list of hits. Each hit has:\n"
        "\n"
        "- ``path``: file path relative to the bundled docs.\n"
        "- ``text``: the matching paragraph plus ``context``\n"
        "  paragraphs on either side.\n"
        "- ``breadcrumb``: the section path containing the hit\n"
        "  (``Section > Sub-section > ...``).\n"
        "- ``index``: the hit's position in the result list.\n"
        "- ``score``: a relevance score; higher is better.\n"
        "\n"
        "The query is tokenised on whitespace and matched\n"
        "case-insensitively. Every token must appear somewhere in\n"
        "the paragraph body, the file path, or an enclosing section\n"
        "title - in any order. Common English stop-words (``the``,\n"
        "``a``, ``how``, ``to``, ...) are dropped, so natural\n"
        "phrasings like ``\"how to bake\"`` work as expected. Regular\n"
        "expressions are not supported.\n"
        "\n"
        "Use ``context`` to pull more surrounding paragraphs into\n"
        "each hit (symmetric, default 0). Use ``index`` with the\n"
        "position of a previous hit (same query) to get that hit\n"
        "alone with its text widened to its enclosing section.\n"
        "\n"
        "Read-only; consults bundled RST files only.\n",
        "inputSchema": {
            "properties": {
                "query": {
                    "title": "Query",
                    "type": "string"
                },
                "max_results": {
                    "default": 20,
                    "title": "Max Results",
                    "type": "integer"
                },
                "context": {
                    "default": 0,
                    "title": "Context",
                    "type": "integer"
                },
                "index": {
                    "anyOf": [
                        {"type": "integer"},
                        {"type": "null"}
                    ],
                    "default": None,
                    "title": "Index"
                }
            },
            "required": [
                "query"
            ],
            "title": "search_manual_docsArguments",
            "type": "object"
        }
    }
]
# END: EXPECTED_TOOLS


def _list_tools() -> list[dict[str, object]]:
    """
    Starts the MCP server and returns the full tool listing.
    """

    # Async is required because the MCP client SDK is async-only.
    async def _run() -> list[dict[str, object]]:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(_REPO_DIR, "mcp")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "blmcp"],
            env=env,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return [
                    {
                        "name": t.name,
                        "description": t.description,
                        "inputSchema": t.inputSchema,
                    }
                    for t in result.tools
                ]

    return asyncio.run(_run())


class TestToolListing(unittest.TestCase):
    """
    Checks that the live tool listing matches the frozen snapshot.
    """

    _tools: list[dict[str, object]]

    @classmethod
    def setUpClass(cls) -> None:
        cls._tools = _list_tools()

    def test_tools_match_expected(self) -> None:
        """
        Checks that the live tool listing exactly matches ``EXPECTED_TOOLS``.
        """
        self.assertEqual(self._tools, EXPECTED_TOOLS)


def _update_expected_tools() -> None:
    """
    Re-generates the ``EXPECTED_TOOLS`` block from a live server query.
    """
    import json
    import subprocess

    filepath = os.path.abspath(__file__)
    with open(filepath, "r", encoding="utf-8") as fh:
        source = fh.read()
    begin = source.index("# BEGIN: EXPECTED_TOOLS\n") + len("# BEGIN: EXPECTED_TOOLS\n")
    end = source.index("# END: EXPECTED_TOOLS\n")
    formatted = json.dumps(_list_tools(), indent=4)
    formatted = (
        formatted.replace(": true", ": True")
        .replace(": false", ": False")
        .replace(": null", ": None")
    )
    formatted = formatted.replace("\\n", '\\n"\n"')
    # Also handles the `\n"` case (no trailing empty string).
    formatted = formatted.replace('\\n"\n""', '\\n"')
    formatted = "EXPECTED_TOOLS = " + formatted + "\n"
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(source[:begin] + formatted + source[end:])
    subprocess.check_call(["autopep8", "--in-place", filepath])


if __name__ == "__main__":
    if "--update" in sys.argv:
        sys.argv.remove("--update")
        _update_expected_tools()
    else:
        unittest.main()
