"""
MCP server for the Blander AI animation factory.

Provides structured domain tools for Blender, connecting via a TCP bridge.
"""

__all__ = (
    "main",
)

import argparse
import importlib
import os
import pkgutil

import yaml
from mcp.server.fastmcp import FastMCP


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Blander MCP server — AI animation factory."
    )
    parser.add_argument(
        "--transport", "-t",
        choices=("stdio",),
        default="stdio",
        help="Transport protocol (default: stdio).",
    )
    args = parser.parse_args()

    data_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"
    )
    with open(
        os.path.join(data_dir, "prompts.yml"), encoding="utf-8"
    ) as fh:
        prompts = yaml.safe_load(fh)

    mcp = FastMCP(
        "blander-mcp",
        instructions=str(prompts["initial_instructions"]),
    )

    import mcp_server.tools as tools_pkg

    for _importer, modname, _ispkg in pkgutil.iter_modules(
        tools_pkg.__path__
    ):
        if modname.endswith("_toolcode") or modname.startswith("_"):
            continue
        mod = importlib.import_module(
            "mcp_server.tools.{:s}".format(modname)
        )
        if hasattr(mod, "register"):
            mod.register(mcp)

    mcp.run(transport=args.transport)
    return 0
