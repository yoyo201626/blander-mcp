# SPDX-FileCopyrightText: 2026 Blender Authors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Integration test for MCP & Blender.

Verifies: Mock-LLM-Client -> MCP server -> Blender addon -> Blender.

The "Mock-LLM-Client" simply sends requests to the MCP server,
the "useful" part of these tests is that it connects to a real Blender instance
and runs the MCP tools verifying they give correct results.

This runs in both background & foreground mode (headless)
where it's possible to check that taking screenshots works properly.

Defaults to ``blender`` and ``blender-mcp`` from ``PATH``.
Override with ``BLENDER_BIN`` and ``BLENDER_MCP`` environment variables.

Foreground tests run headless via a Wayland display server (Weston).
Set ``BLENDER_MCP_FOREGROUND=1`` to use the real display instead.
"""

__all__ = ()

import base64
import glob
import inspect
import json
import os
import shlex
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import textwrap
import threading
import time
import unittest

import sys

import atexit

# Root of the repository.
_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure the repository root is on the path so `tests` resolves as a package.
if _REPO_DIR not in sys.path:
    sys.path.insert(0, _REPO_DIR)

from src.tests.mcp_client import MCPClient

# Fixed ports for the test servers (background and foreground).
_PORT_BACKGROUND = 9876
_PORT_FOREGROUND = 9877
_PORT_INTERACTIVE = 9878

# Scale all timeouts (e.g. `GLOBAL_TIMEOUT_SCALE=2` doubles every limit).
_TIMEOUT_SCALE = float(os.environ.get("GLOBAL_TIMEOUT_SCALE", "1"))

# Maximum time to wait for Blender to start (seconds).
_TIMEOUT_STARTUP = int(int(os.environ.get("BLENDER_MCP_TIMEOUT", "10")) * _TIMEOUT_SCALE)

# Maximum time to wait for a local process to respond or exit (seconds).
_TIMEOUT_LOCAL_PROC = int(10 * _TIMEOUT_SCALE)

# Tool coverage tracking.
_all_tools: set[str] = set()
_tested_tools: set[str] = set()


def _print_untested_tools() -> None:
    """
    Print tools that were not exercised by any test.
    """
    untested = sorted(_all_tools - _tested_tools)
    if not untested:
        return
    print("\nUntested tools ({:d}/{:d}):".format(len(untested), len(_all_tools)))
    for name in untested:
        print("  - {:s}".format(name))


atexit.register(_print_untested_tools)


def _python_fn_body_as_string(fn: object) -> str:
    """
    Return the body of *fn* as a dedented string.
    """
    source = inspect.getsource(fn)
    lines = source.splitlines()
    body_lines = lines[1:]
    code = textwrap.dedent("\n".join(body_lines))
    assert code.strip(), "Function body is empty"
    return code


def _blender_env(tmpdir: str) -> dict[str, str]:
    """
    Return an environment dict for Blender sub-processes.

    Sets ``HOME`` to *tmpdir* so that Blender reads and writes its
    configuration there instead of touching the real user directory.
    Disables ASAN leak checking so debug builds exit cleanly.
    """
    env = os.environ.copy()
    env["HOME"] = tmpdir
    env["ASAN_OPTIONS"] = ":".join(filter(None, [
        env.get("ASAN_OPTIONS", ""),
        "alloc_dealloc_mismatch=0",
        "leak_check_at_exit=0",
    ]))
    return env


def _run_blender(args: list[str], env: dict[str, str]) -> None:
    """
    Run a Blender command and raise on failure, including stderr in the message.
    """
    result = subprocess.run(args, capture_output=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed (exit {:d}):\n  {:s}\n{:s}".format(
                result.returncode,
                " ".join(args),
                result.stderr.decode("utf-8", errors="replace"),
            )
        )


def _drain_stdout(proc: "subprocess.Popen[bytes]") -> list[str]:
    """
    Read *proc* stdout in a daemon thread, collecting lines.

    This prevents the pipe buffer from filling up and blocking the child.
    Returns a list that is appended to from the reader thread.
    """
    lines: list[str] = []

    def _reader() -> None:
        assert proc.stdout is not None
        for raw in proc.stdout:
            lines.append(raw.decode("utf-8", errors="replace"))

    threading.Thread(target=_reader, daemon=True).start()
    return lines


def _start_headless_display(env: dict[str, str]) -> "subprocess.Popen[bytes]":
    """
    Start a headless Wayland display server and add ``WAYLAND_DISPLAY`` to *env*.

    Returns the weston process. The caller must call
    ``_stop_headless_display`` when done.
    """
    from src.tests.utils.blender_headless import backend_wayland

    weston_socket = "wl-blmcp-{:d}".format(os.getpid())
    weston_bin = os.environ.get("WESTON_BIN", "weston")
    weston_env, weston_ini = backend_wayland._weston_env_and_ini()

    ini_fd, ini_path = tempfile.mkstemp(prefix="weston_", suffix=".ini")
    with os.fdopen(ini_fd, "w", encoding="utf-8") as fh:
        fh.write(weston_ini)

    cmd = [
        weston_bin,
        "--socket={:s}".format(weston_socket),
        "--backend=headless",
        "--width=800",
        "--height=600",
        "--config={:s}".format(ini_path),
    ]
    weston_kw: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if weston_env is not None:
        weston_kw["env"] = weston_env

    proc = subprocess.Popen(cmd, **weston_kw)

    if not backend_wayland._wait_for_wayland_server(
        socket=weston_socket, timeout=_TIMEOUT_LOCAL_PROC,
    ):
        proc.send_signal(signal.SIGINT)
        proc.communicate()
        os.remove(ini_path)
        raise RuntimeError("Failed to start headless Wayland display server")

    env["WAYLAND_DISPLAY"] = weston_socket
    # Store for cleanup.
    proc._weston_ini_path = ini_path  # type: ignore[attr-defined]
    return proc


def _stop_headless_display(proc: "subprocess.Popen[bytes]") -> None:
    """
    Stop the headless Wayland display server started by ``_start_headless_display``.
    """
    proc.send_signal(signal.SIGINT)
    proc.communicate(timeout=_TIMEOUT_LOCAL_PROC)
    ini_path = getattr(proc, "_weston_ini_path", None)
    if ini_path is not None and os.path.exists(ini_path):
        os.remove(ini_path)


def _check_port_reachable(port: int) -> None:
    """
    Verify *port* on localhost is open; raise ``RuntimeError`` if not.

    Used in reuse mode to confirm an existing Blender MCP addon is listening
    before attempting to connect.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            sock.connect(("localhost", port))
    except (ConnectionRefusedError, OSError) as ex:
        raise RuntimeError(
            "BLENDER_MCP_REUSE=1 but port {:d} is not reachable: {:s}\n"
            "Make sure Blender is open with the MCP addon enabled "
            "and listening on that port.".format(port, str(ex))
        ) from ex


def _wait_for_port(
        port: int,
        timeout: int,
        proc: "subprocess.Popen[bytes]",
        output: list[str],
) -> None:
    """
    Block until a TCP connection to *port* on localhost succeeds.

    Checks *proc* on each iteration so an early crash is reported
    immediately instead of waiting for the full timeout.
    Raises ``RuntimeError`` if *timeout* seconds elapse or *proc* exits.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rc = proc.poll()
        if rc is not None:
            raise RuntimeError(
                "Blender exited with code {:d} before the server became reachable\n{:s}".format(
                    rc, "".join(output[-50:]),
                )
            )
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(1)
                sock.connect(("localhost", port))
                return
        except (ConnectionRefusedError, OSError):
            time.sleep(0.2)
    raise RuntimeError(
        "Port {:d} not reachable within {:d}s\n{:s}".format(
            port, timeout, "".join(output[-50:]),
        )
    )


class _TestServerMixin:
    """
    Shared setup, cleanup, helpers and test methods for both background
    and foreground server modes.

    Concrete subclasses set ``_background`` and ``_port`` as class variables.
    """

    _background: bool
    _interactive: bool = False
    _port: int

    _reuse_mode: bool = False

    @classmethod
    def setUpClass(cls) -> None:
        blender_bin = os.environ.get("BLENDER_BIN", "blender")
        blender_mcp = os.environ.get("BLENDER_MCP", "blender-mcp")

        cls._tmpdir = tempfile.TemporaryDirectory()
        tmpdir = cls._tmpdir.name
        cls.addClassCleanup(cls._tmpdir.cleanup)

        if cls._reuse_mode:
            # Reuse mode: skip build / install / Blender launch.
            # Connect directly to the already-running Blender MCP addon.
            _check_port_reachable(cls._port)
            mcp_env = os.environ.copy()
            mcp_env["BLENDER_MCP_PORT"] = str(cls._port)
            mcp_env["BLENDER_PATH"] = blender_bin
        else:
            env = _blender_env(tmpdir)

            # Build the extension zip.
            addon_src = os.path.join(_REPO_DIR, "addon", "blender_mcp_addon")
            _run_blender(
                [
                    blender_bin, "--command", "extension", "build",
                    "--source-dir=" + addon_src,
                    "--output-dir=" + tmpdir,
                ],
                env=env,
            )

            zips = glob.glob(os.path.join(tmpdir, "mcp-*.zip"))
            if not zips:
                raise RuntimeError("Extension build did not produce a zip")

            # Install the extension into the isolated HOME.
            _run_blender(
                [
                    blender_bin, "--online-mode", "--background", "--factory-startup",
                    "--command", "extension", "install-file",
                    zips[0], "--repo", "user_default", "--enable",
                ],
                env=env,
            )

            if cls._interactive:
                # Save preferences before launching so the autostart timer
                # reads the correct port with no delay.
                # This could be supported more generically by passing arbitrary
                # preference overrides, but port and delay are all we need for now.
                _run_blender(
                    [
                        blender_bin, "--background",
                        "--python-expr",
                        (
                            "import bpy; "
                            "prefs = bpy.context.preferences.addons"
                            "['bl_ext.user_default.mcp'].preferences; "
                            "prefs.port = {:d}; "
                            "prefs.autostart_delay = 0.0; "
                            "bpy.ops.wm.save_userpref()"
                        ).format(cls._port),
                    ],
                    env=env,
                )

            # Start a headless display server for non-background tests.
            # Registered before Blender so cleanup order is Blender first,
            # then the display server (LIFO).
            if not cls._background and not os.environ.get("BLENDER_MCP_FOREGROUND"):
                cls._weston_proc = _start_headless_display(env)
                cls.addClassCleanup(_stop_headless_display, cls._weston_proc)

            # Start Blender with the installed addon.
            # Omit `--factory-startup` so saved preferences (with the
            # extension enabled) are loaded from the isolated HOME.
            blender_args = [blender_bin, "--online-mode"]
            if cls._background:
                blender_args.append("--background")
            # Use Vulkan when not in background mode. OpenGL (llvmpipe) is known
            # to crash during shader JIT compilation under headless Weston with
            # recent LLVM/Mesa versions.
            if not cls._background:
                blender_args.extend(["--gpu-backend", "vulkan"])
            if not cls._interactive:
                blender_args.extend([
                    "--command", "blender_mcp", "--port", str(cls._port),
                ])

            cls._blender_proc = subprocess.Popen(
                blender_args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
            )
            cls.addClassCleanup(cls._cleanup_blender)

            output = _drain_stdout(cls._blender_proc)
            _wait_for_port(cls._port, _TIMEOUT_STARTUP, cls._blender_proc, output)

            mcp_env = _blender_env(tmpdir)
            mcp_env["BLENDER_MCP_PORT"] = str(cls._port)
            mcp_env["BLENDER_PATH"] = blender_bin

        cls._client = MCPClient(shlex.split(blender_mcp), env=mcp_env)
        cls.addClassCleanup(cls._client.close)
        cls._client.initialize()
        _all_tools.update(cls._client.list_tools())

        # Save a blend file for CLI tools.
        cls._blend_path = os.path.join(tmpdir, "test.blend")
        cls._client.call_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "bpy.ops.wm.save_as_mainfile(filepath={!r})\n"
                "result = {{'saved': True}}\n"
            ).format(cls._blend_path),
        })

    @classmethod
    def _cleanup_blender(cls) -> None:
        """
        Terminate Blender and close its stdout pipe.
        """
        cls._blender_proc.terminate()
        cls._blender_proc.wait(timeout=_TIMEOUT_LOCAL_PROC)
        if cls._blender_proc.stdout is not None:
            cls._blender_proc.stdout.close()

    def _call_tool(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        """
        Call a tool, verify the response is not an error, and return the content list.
        """
        _tested_tools.add(name)
        result = self._client.call_tool(name, arguments)
        content = result.get("content", [])
        self.assertFalse(
            result.get("isError", False),
            "Tool {:s} returned an error: {!r}".format(name, content),
        )
        self.assertIsInstance(content, list)
        self.assertTrue(
            len(content) > 0,
            "Expected at least one content item for {:s}".format(name),
        )
        return content

    def _call_tool_expect_error(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        """
        Call a tool and assert that the response is an MCP-level error.
        """
        _tested_tools.add(name)
        result = self._client.call_tool(name, arguments)
        self.assertTrue(
            result.get("isError", False),
            "Expected {:s} to return isError".format(name),
        )
        return result.get("content", [])

    def _test_tool(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """
        Call a tool that returns text and return the parsed JSON result.

        When the response contains ``"status": "ok"`` the ``"result"``
        value is returned directly. Error responses are returned as-is.
        """
        content = self._call_tool(name, arguments)
        text_item = content[0]
        self.assertEqual(
            text_item.get("type"), "text",
            "Expected text content for {:s}, got {!r}".format(
                name, text_item.get("type"),
            ),
        )
        data = json.loads(text_item["text"])
        if data.get("status") == "ok":
            # Tools that run code in Blender wrap their response in
            # `{"status": "ok", "result": ...}`, but toolcode-based
            # tools may omit the `result` key.
            return data.get("result", data)
        return data

    def setUp(self) -> None:
        """Reload the default scene so each test starts from a clean state."""
        self._client.call_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "bpy.ops.wm.read_homefile(use_empty=False)\n"
                "result = {'reset': True}\n"
            ),
        })

    # -----------------------------------------------------------------
    # Interactive tools.

    def test_execute_blender_code(self) -> None:
        data = self._test_tool("execute_blender_code", {
            "code": "result = {'value': 1 + 1}",
        })
        self.assertEqual(data["value"], 2)

    def test_get_blendfile_summary_datablocks(self) -> None:
        data = self._test_tool("get_blendfile_summary_datablocks")
        self.assertEqual(data["scene_name"], "Scene")
        self.assertIn("Layout", data["workspaces"])
        self.assertIsInstance(data["datablock_counts"], dict)

    def test_get_blendfile_summary_missing_files(self) -> None:
        data = self._test_tool("get_blendfile_summary_missing_files")
        self.assertIsInstance(data["missing_files"], list)
        self.assertEqual(data["missing_files"], [])

    def test_get_blendfile_summary_of_linked_libraries(self) -> None:
        data = self._test_tool("get_blendfile_summary_of_linked_libraries")
        self.assertEqual(data["total_library_count"], 0)
        self.assertEqual(data["direct_libraries"], [])
        self.assertEqual(data["indirect_libraries"], [])

    def test_get_blendfile_summary_path_info(self) -> None:
        data = self._test_tool("get_blendfile_summary_path_info")
        self.assertEqual(data["filepath"], "")
        self.assertFalse(data["is_saved"])
        self.assertIsNone(data["age_seconds"])
        self.assertIsNone(data["file_size_bytes"])
        self.assertIsNone(data["backups"])

    def test_get_blendfile_summary_usage_guess(self) -> None:
        data = self._test_tool("get_blendfile_summary_usage_guess")
        guesses = data["usage_guesses"]
        self.assertIn("Animation", guesses)
        self.assertIn("Modeling", guesses)
        for scores in guesses.values():
            self.assertIn("score", scores)
            self.assertIn("certainty", scores)

    def _call_tool_screenshot(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        _tested_tools.add(name)
        result = self._client.call_tool(name, arguments)
        content = result.get("content", [])
        if not self._interactive:
            # Non-interactive modes (--background and --command) have
            # bpy.app.background == True, so screenshots are unavailable.
            self.assertTrue(
                result.get("isError", False),
                "Expected {:s} to fail in non-interactive mode".format(name),
            )
        else:
            self.assertFalse(
                result.get("isError", False),
                "Tool {:s} returned an error: {!r}".format(name, content),
            )
            self.assertEqual(content[0].get("type"), "image")
            image_data = content[0].get("data", "")
            self.assertTrue(len(image_data) > 0)
            width, height = self._image_size(image_data)
            self.assertGreater(width, 1)
            self.assertLess(width, 4096)
            self.assertGreater(height, 1)
            self.assertLess(height, 4096)
        return content

    @staticmethod
    def _image_size(image_base64: str) -> tuple[int, int]:
        """Return (width, height) of a base64-encoded PNG by reading the IHDR chunk."""
        data = base64.b64decode(image_base64)
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return (-1, -1)
        width, height = struct.unpack(">II", data[16:24])
        return (width, height)

    def test_get_screenshot_of_area_as_image(self) -> None:
        self._call_tool_screenshot("get_screenshot_of_area_as_image", {
            "area_ui_type": "VIEW_3D",
        })

    def test_get_screenshot_of_area_as_image_error(self) -> None:
        self._call_tool_expect_error("get_screenshot_of_area_as_image", {
            "area_ui_type": "NONEXISTENT",
        })

    def test_get_screenshot_of_window_as_image(self) -> None:
        self._call_tool_screenshot("get_screenshot_of_window_as_image")

    def test_get_screenshot_of_window_as_image_size_limit(self) -> None:
        size_limit = 16 * 1024  # 16 KB.
        content = self._call_tool_screenshot("get_screenshot_of_window_as_image", {
            "size_limit_in_bytes": size_limit,
        })
        if self._interactive:
            image_data = content[0].get("data", "")
            raw_bytes = base64.b64decode(image_data)
            self.assertLessEqual(
                len(raw_bytes), size_limit,
                "Screenshot exceeds {:d} byte limit ({:d} bytes)".format(size_limit, len(raw_bytes)),
            )

    def test_get_screenshot_of_window_as_json(self) -> None:
        data = self._test_tool("get_screenshot_of_window_as_json")
        if not self._interactive:
            self.assertEqual(data["status"], "error")
        else:
            self.assertEqual(data["scene"], "Scene")
            self.assertIsInstance(data["areas"], list)
            self.assertTrue(len(data["areas"]) > 0)
            self.assertIsNotNone(data["active_object"])
            self.assertIn("name", data["active_object"])

    # -----------------------------------------------------------------
    # CLI tools.

    def test_execute_blender_code_for_cli(self) -> None:
        data = self._test_tool("execute_blender_code_for_cli", {
            "blend_file": self._blend_path,
            "code": "result = {'version': 1}",
        })
        self.assertEqual(data["version"], 1)

    def test_get_blendfile_summary_datablocks_for_cli(self) -> None:
        data = self._test_tool("get_blendfile_summary_datablocks_for_cli", {
            "blend_file": self._blend_path,
        })
        self.assertEqual(data["scene_name"], "Scene")
        self.assertIsInstance(data["datablock_counts"], dict)

    def test_get_blendfile_summary_missing_files_for_cli(self) -> None:
        data = self._test_tool("get_blendfile_summary_missing_files_for_cli", {
            "blend_file": self._blend_path,
        })
        self.assertEqual(data["missing_files"], [])

    def test_get_blendfile_summary_of_linked_libraries_for_cli(self) -> None:
        data = self._test_tool("get_blendfile_summary_of_linked_libraries_for_cli", {
            "blend_file": self._blend_path,
        })
        self.assertEqual(data["total_library_count"], 0)

    def test_get_blendfile_summary_path_info_for_cli(self) -> None:
        data = self._test_tool("get_blendfile_summary_path_info_for_cli", {
            "blend_file": self._blend_path,
        })
        self.assertTrue(data["is_saved"])
        self.assertTrue(data["filepath"].endswith(".blend"))

    def test_get_blendfile_summary_usage_guess_for_cli(self) -> None:
        data = self._test_tool("get_blendfile_summary_usage_guess_for_cli", {
            "blend_file": self._blend_path,
        })
        guesses = data["usage_guesses"]
        self.assertIn("Animation", guesses)
        self.assertIn("Modeling", guesses)

    # -----------------------------------------------------------------
    # Object inspection tools.

    def test_get_object_detail_summary(self) -> None:
        data = self._test_tool("get_object_detail_summary", {"name": "Cube"})
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "Cube")
        self.assertEqual(data["type"], "MESH")
        self.assertEqual(data["data_name"], "Cube")
        self.assertEqual(data["location"], [0.0, 0.0, 0.0])
        self.assertEqual(data["rotation"], [0.0, 0.0, 0.0])
        self.assertEqual(data["scale"], [1.0, 1.0, 1.0])
        self.assertEqual(data["dimensions"], [2.0, 2.0, 2.0])
        self.assertIsNone(data["parent"])
        self.assertEqual(data["children"], [])
        self.assertEqual(data["modifiers"], [])
        self.assertEqual(data["constraints"], [])
        self.assertEqual(data["materials"], ["Material"])
        self.assertEqual(data["visibility"], {
            "hide_viewport": False,
            "hide_render": False,
            "hide_get": False,
        })
        self.assertIn("Collection", data["collections"])

    def test_get_object_detail_summary_error(self) -> None:
        data = self._test_tool("get_object_detail_summary", {"name": "NonExistent"})
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")
        self.assertIn("'NonExistent'", data["message"])
        self.assertIn("Cube", data["current_state"]["available_objects"])
        self.assertIsInstance(data["hint"], str)
        self.assertTrue(data["hint"])

    def test_get_objects_summary(self) -> None:
        data = self._test_tool("get_objects_summary")
        self.assertEqual(data, {
            "status": "ok",
            "scene_name": "Scene",
            "active_workspace": "Layout",
            "active_object": "Cube",
            "object_mode": "OBJECT",
            "camera_object": "Camera",
            "collections": [
                {
                    "name": "Scene Collection",
                    "exclude": False,
                    "hide_viewport": False,
                    "objects": [],
                    "children": [
                        {
                            "name": "Collection",
                            "exclude": False,
                            "hide_viewport": False,
                            "objects": [
                                {
                                    "name": "Camera",
                                    "type": "CAMERA",
                                    "parent": None,
                                    "data_name": "Camera",
                                    "selected": False,
                                    "visible": True,
                                    "hide_viewport": False,
                                },
                                {
                                    "name": "Cube",
                                    "type": "MESH",
                                    "parent": None,
                                    "data_name": "Cube",
                                    "selected": True,
                                    "visible": True,
                                    "hide_viewport": False,
                                },
                                {
                                    "name": "Light",
                                    "type": "LIGHT",
                                    "parent": None,
                                    "data_name": "Light",
                                    "selected": False,
                                    "visible": True,
                                    "hide_viewport": False,
                                },
                            ],
                            "children": [],
                        },
                    ],
                },
            ],
        })

    def test_get_scene_state(self) -> None:
        data = self._test_tool("get_scene_state")
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["scene_name"], "Scene")
        # Frame info.
        self.assertIsInstance(data["frame_start"], int)
        self.assertIsInstance(data["frame_end"], int)
        self.assertIsInstance(data["frame_current"], int)
        self.assertGreaterEqual(data["frame_end"], data["frame_start"])
        self.assertIsInstance(data["fps"], (int, float))
        self.assertGreater(data["fps"], 0)
        # Objects.
        objects = data["objects"]
        self.assertIsInstance(objects, list)
        names = [o["name"] for o in objects]
        self.assertIn("Camera", names)
        self.assertIn("Cube", names)
        self.assertIn("Light", names)
        for obj in objects:
            self.assertIn("name", obj)
            self.assertIn("type", obj)
            location = obj["location"]
            self.assertIsInstance(location, list)
            self.assertEqual(len(location), 3)
            for coord in location:
                self.assertIsInstance(coord, float)

    def test_get_scene_state_frame_info(self) -> None:
        """Verify that frame_current and frame_end reflect live Blender state."""
        self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "bpy.context.scene.frame_current = 42\n"
                "bpy.context.scene.frame_end = 120\n"
                "result = {'done': True}\n"
            ),
        })
        data = self._test_tool("get_scene_state")
        self.assertEqual(data["frame_current"], 42)
        self.assertEqual(data["frame_end"], 120)

    # -----------------------------------------------------------------
    # Grease Pencil tools (REQ-03).

    def test_gp_object_create(self) -> None:
        data = self._test_tool("gp_object_create", {"name": "Canvas"})
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "Canvas")
        self.assertIsInstance(data["collection"], str)

    def test_gp_object_create_deduplication(self) -> None:
        """Second object with the same name gets a .001 suffix."""
        self._test_tool("gp_object_create", {"name": "Canvas"})
        data = self._test_tool("gp_object_create", {"name": "Canvas"})
        self.assertEqual(data["status"], "ok")
        self.assertNotEqual(data["name"], "Canvas")
        self.assertTrue(data["name"].startswith("Canvas"))

    def test_gp_layer_create(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        data = self._test_tool("gp_layer_create", {
            "object_name": "Canvas",
            "layer_name": "Lines",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "Canvas")
        self.assertEqual(data["layer_name"], "Lines")

    def test_gp_layers_list(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        self._test_tool("gp_layer_create", {
            "object_name": "Canvas", "layer_name": "Lines",
        })
        self._test_tool("gp_layer_create", {
            "object_name": "Canvas", "layer_name": "Fill",
        })
        data = self._test_tool("gp_layers_list", {"object_name": "Canvas"})
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "Canvas")
        names = [l["name"] for l in data["layers"]]
        self.assertIn("Lines", names)
        self.assertIn("Fill", names)
        for layer in data["layers"]:
            self.assertIn("name", layer)
            self.assertIn("opacity", layer)
            self.assertIn("hide", layer)

    def test_gp_layer_delete(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        self._test_tool("gp_layer_create", {
            "object_name": "Canvas", "layer_name": "Lines",
        })
        data = self._test_tool("gp_layer_delete", {
            "object_name": "Canvas",
            "layer_name": "Lines",
        })
        self.assertEqual(data["status"], "ok")
        # Verify the layer is gone.
        list_data = self._test_tool("gp_layers_list", {"object_name": "Canvas"})
        names = [l["name"] for l in list_data["layers"]]
        self.assertNotIn("Lines", names)

    def test_gp_object_create_error_not_gp(self) -> None:
        """gp_layer_create rejects non-GP objects."""
        data = self._test_tool("gp_layer_create", {
            "object_name": "Cube",
            "layer_name": "Lines",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_OBJECT_TYPE")
        self.assertIsInstance(data["hint"], str)

    def test_gp_layer_create_object_not_found(self) -> None:
        data = self._test_tool("gp_layer_create", {
            "object_name": "NonExistent",
            "layer_name": "Lines",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")
        self.assertIsInstance(data["current_state"]["available_gp_objects"], list)

    def test_gp_layer_delete_layer_not_found(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        data = self._test_tool("gp_layer_delete", {
            "object_name": "Canvas",
            "layer_name": "DoesNotExist",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "LAYER_NOT_FOUND")
        self.assertIsInstance(data["current_state"]["available_layers"], list)

    # -----------------------------------------------------------------
    # Stroke drawing tools (REQ-04).

    def _setup_gp_canvas(self) -> None:
        """Create a fresh GP object named 'Canvas' with one layer 'Strokes'."""
        self._test_tool("gp_object_create", {"name": "Canvas"})
        self._test_tool("gp_layer_create", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
        })

    def test_gp_stroke_draw_basic(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "points": [[-1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "Canvas")
        self.assertEqual(data["layer_name"], "Strokes")
        self.assertEqual(data["frame"], 1)
        self.assertGreaterEqual(data["stroke_count"], 1)

    def test_gp_stroke_draw_replace(self) -> None:
        self._setup_gp_canvas()
        self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            "mode": "replace",
        })
        data = self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "points": [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
            "mode": "replace",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["stroke_count"], 1)

    def test_gp_stroke_draw_append(self) -> None:
        self._setup_gp_canvas()
        self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            "mode": "replace",
        })
        data = self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "points": [[0.0, 0.0, 1.0], [1.0, 0.0, 1.0]],
            "mode": "append",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["stroke_count"], 2)

    def test_gp_stroke_draw_error_layer_not_found(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        data = self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "NoSuchLayer",
            "frame": 1,
            "points": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "LAYER_NOT_FOUND")
        self.assertIsInstance(data["current_state"]["available_layers"], list)
        self.assertIsInstance(data["hint"], str)

    def test_gp_stroke_draw_error_invalid_points(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_stroke_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "points": [],
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_POINTS")

    def test_gp_shape_draw_rect(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_shape_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "shape": "rect",
            "cx": 0.0, "cy": 0.0, "cz": 0.0,
            "width": 2.0, "height": 1.0,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["shape"], "rect")
        self.assertEqual(data["point_count"], 5)

    def test_gp_shape_draw_circle(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_shape_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "shape": "circle",
            "cx": 0.0, "cy": 0.0, "cz": 0.0,
            "radius": 1.5,
            "segments": 16,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["shape"], "circle")
        self.assertEqual(data["point_count"], 17)

    def test_gp_shape_draw_line(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_shape_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "shape": "line",
            "x1": 0.0, "y1": 0.0, "z1": 0.0,
            "x2": 2.0, "y2": 0.0, "z2": 1.0,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["shape"], "line")
        self.assertEqual(data["point_count"], 2)

    def test_gp_shape_draw_line_with_points_count(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_shape_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "shape": "line",
            "x1": -1.0, "y1": 0.0, "z1": 0.0,
            "x2": 1.0, "y2": 0.0, "z2": 0.0,
            "points_count": 5,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["point_count"], 5)

    def test_gp_shape_draw_error_invalid_shape(self) -> None:
        self._setup_gp_canvas()
        data = self._test_tool("gp_shape_draw", {
            "object_name": "Canvas",
            "layer_name": "Strokes",
            "frame": 1,
            "shape": "triangle",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_SHAPE")

    # -----------------------------------------------------------------
    # Material tools (REQ-05).

    def test_gp_material_create_basic(self) -> None:
        data = self._test_tool("gp_material_create", {
            "name": "TestMat",
            "stroke_color": [1.0, 0.0, 0.0, 1.0],
            "fill_color": [0.0, 1.0, 0.0, 0.5],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "TestMat")
        self.assertIsInstance(data["stroke_color"], list)
        self.assertEqual(len(data["stroke_color"]), 4)
        self.assertIsInstance(data["fill_color"], list)

    def test_gp_material_create_deduplication(self) -> None:
        self._test_tool("gp_material_create", {"name": "MatA"})
        data = self._test_tool("gp_material_create", {"name": "MatA"})
        self.assertEqual(data["status"], "ok")
        self.assertNotEqual(data["name"], "MatA")

    def test_gp_material_create_error_invalid_color(self) -> None:
        data = self._test_tool("gp_material_create", {
            "name": "Bad",
            "stroke_color": [1.0, 0.0],
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_COLOR")

    def test_gp_material_assign_basic(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        self._test_tool("gp_material_create", {"name": "Ink"})
        data = self._test_tool("gp_material_assign", {
            "object_name": "Canvas",
            "material_name": "Ink",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "Canvas")
        self.assertEqual(data["material_name"], "Ink")
        self.assertIsInstance(data["slot_index"], int)
        self.assertGreaterEqual(data["slot_index"], 0)

    def test_gp_material_assign_idempotent(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        self._test_tool("gp_material_create", {"name": "Ink"})
        d1 = self._test_tool("gp_material_assign", {
            "object_name": "Canvas",
            "material_name": "Ink",
        })
        d2 = self._test_tool("gp_material_assign", {
            "object_name": "Canvas",
            "material_name": "Ink",
        })
        self.assertEqual(d1["slot_index"], d2["slot_index"])

    def test_gp_material_assign_error_material_not_found(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        data = self._test_tool("gp_material_assign", {
            "object_name": "Canvas",
            "material_name": "NoSuchMaterial",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "MATERIAL_NOT_FOUND")
        self.assertIsInstance(data["current_state"]["available_gp_materials"], list)

    def test_gp_material_assign_error_not_gp_material(self) -> None:
        self._test_tool("gp_object_create", {"name": "Canvas"})
        # Create a plain (non-GP) material via execute_blender_code
        self._test_tool("execute_blender_code", {
            "code": "import bpy\nbpy.data.materials.new('PlainMat')\n",
        })
        data = self._test_tool("gp_material_assign", {
            "object_name": "Canvas",
            "material_name": "PlainMat",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "NOT_GP_MATERIAL")

    # -----------------------------------------------------------------
    # Layer animation tools (REQ-06).

    def _setup_gp_anim_canvas(self) -> None:
        """Create GP object 'AnimCanvas' with layer 'Outline' for animation tests."""
        self._test_tool("gp_object_create", {"name": "AnimCanvas"})
        self._test_tool("gp_layer_create", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
        })

    def test_gp_layer_opacity_set_basic(self) -> None:
        self._setup_gp_anim_canvas()
        data = self._test_tool("gp_layer_opacity_set", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
            "frame": 1,
            "opacity": 1.0,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "AnimCanvas")
        self.assertEqual(data["layer_name"], "Outline")
        self.assertEqual(data["frame"], 1)
        self.assertAlmostEqual(data["opacity"], 1.0, places=5)

    def test_gp_layer_opacity_set_multiple_frames(self) -> None:
        self._setup_gp_anim_canvas()
        self._test_tool("gp_layer_opacity_set", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
            "frame": 1,
            "opacity": 1.0,
        })
        data = self._test_tool("gp_layer_opacity_set", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
            "frame": 30,
            "opacity": 0.0,
        })
        self.assertEqual(data["status"], "ok")
        self.assertAlmostEqual(data["opacity"], 0.0, places=5)

    def test_gp_layer_opacity_set_error_out_of_range(self) -> None:
        self._setup_gp_anim_canvas()
        data = self._test_tool("gp_layer_opacity_set", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
            "frame": 1,
            "opacity": 1.5,
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_OPACITY")
        self.assertIn("current_opacity", data["current_state"])

    def test_gp_layer_keyframes_list_empty(self) -> None:
        self._setup_gp_anim_canvas()
        data = self._test_tool("gp_layer_keyframes_list", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
        })
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["keyframes"], list)
        self.assertEqual(len(data["keyframes"]), 0)

    def test_gp_layer_keyframes_list_after_set(self) -> None:
        self._setup_gp_anim_canvas()
        self._test_tool("gp_layer_opacity_set", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
            "frame": 1,
            "opacity": 1.0,
        })
        self._test_tool("gp_layer_opacity_set", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
            "frame": 60,
            "opacity": 0.0,
        })
        data = self._test_tool("gp_layer_keyframes_list", {
            "object_name": "AnimCanvas",
            "layer_name": "Outline",
        })
        self.assertEqual(data["status"], "ok")
        kfs = data["keyframes"]
        self.assertEqual(len(kfs), 2)
        self.assertEqual(kfs[0]["frame"], 1)
        self.assertAlmostEqual(kfs[0]["opacity"], 1.0, places=4)
        self.assertEqual(kfs[1]["frame"], 60)
        self.assertAlmostEqual(kfs[1]["opacity"], 0.0, places=4)

    def test_gp_layer_keyframes_list_error_layer_not_found(self) -> None:
        self._test_tool("gp_object_create", {"name": "AnimCanvas"})
        data = self._test_tool("gp_layer_keyframes_list", {
            "object_name": "AnimCanvas",
            "layer_name": "DoesNotExist",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "LAYER_NOT_FOUND")
        self.assertIsInstance(data["current_state"]["available_layers"], list)

    # -----------------------------------------------------------------
    # Navigation tools.

    def test_jump_to_tab_by_name(self) -> None:
        data = self._test_tool("jump_to_tab_by_name", {"name": "Layout"})
        if not self._interactive:
            self.assertEqual(data["status"], "error")
            return
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["workspace"], "Layout")

    def test_jump_to_tab_by_space_type(self) -> None:
        data = self._test_tool("jump_to_tab_by_space_type", {"space_type": "VIEW_3D"})
        if not self._interactive:
            self.assertEqual(data["status"], "error")
            return
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["space_type"], "VIEW_3D")

    def test_jump_to_view3d_object_by_name(self) -> None:
        data = self._test_tool("jump_to_view3d_object_by_name", {"name": "Cube"})
        if not self._interactive:
            self.assertEqual(data["status"], "error")
            return
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object"], "Cube")
        self.assertEqual(data["type"], "MESH")

    def test_jump_to_view3d_object_data_by_name(self) -> None:
        data = self._test_tool("jump_to_view3d_object_data_by_name", {"name": "Cube"})
        if not self._interactive:
            self.assertEqual(data["status"], "error")
            return
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data_name"], "Cube")
        self.assertEqual(data["type"], "MESH")

    # -----------------------------------------------------------------
    # 3D mesh primitive tools (REQ-08).

    def test_mesh_primitive_add_cube(self) -> None:
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "CUBE",
            "name": "MyCube",
            "location": [1.0, 2.0, 3.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "MyCube")
        self.assertEqual(data["primitive_type"], "CUBE")
        loc = data["location"]
        self.assertAlmostEqual(loc[0], 1.0, places=4)
        self.assertAlmostEqual(loc[1], 2.0, places=4)
        self.assertAlmostEqual(loc[2], 3.0, places=4)

    def test_mesh_primitive_add_sphere(self) -> None:
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "SPHERE",
            "name": "MySphere",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "MySphere")
        self.assertEqual(data["primitive_type"], "SPHERE")
        self.assertIsInstance(data["location"], list)
        self.assertEqual(len(data["location"]), 3)

    def test_mesh_primitive_add_plane(self) -> None:
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "PLANE",
            "name": "MyPlane",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "MyPlane")
        self.assertEqual(data["primitive_type"], "PLANE")

    def test_mesh_primitive_add_cylinder(self) -> None:
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "CYLINDER",
            "name": "MyCylinder",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["name"], "MyCylinder")
        self.assertEqual(data["primitive_type"], "CYLINDER")

    def test_mesh_primitive_add_default_name(self) -> None:
        """Omitting name gives Blender a default name."""
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "CUBE",
        })
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["name"], str)
        self.assertTrue(len(data["name"]) > 0)

    def test_mesh_primitive_add_name_deduplication(self) -> None:
        """Second object with the same name gets a .001 suffix."""
        self._test_tool("mesh_primitive_add", {
            "primitive_type": "CUBE",
            "name": "SharedName",
        })
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "SPHERE",
            "name": "SharedName",
        })
        self.assertEqual(data["status"], "ok")
        self.assertNotEqual(data["name"], "SharedName")
        self.assertTrue(data["name"].startswith("SharedName"))

    def test_mesh_primitive_add_object_in_scene(self) -> None:
        """Verify the created object is visible in scene state."""
        self._test_tool("mesh_primitive_add", {
            "primitive_type": "CUBE",
            "name": "SceneCheckCube",
        })
        state = self._test_tool("get_scene_state")
        names = [o["name"] for o in state["objects"]]
        self.assertIn("SceneCheckCube", names)

    def test_mesh_primitive_add_error_invalid_type(self) -> None:
        data = self._test_tool("mesh_primitive_add", {
            "primitive_type": "TORUS",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_PRIMITIVE_TYPE")
        self.assertIsInstance(data["current_state"]["supported_types"], list)
        self.assertIsInstance(data["hint"], str)

    # -----------------------------------------------------------------
    # Transform keyframe tools (REQ-09).

    def _setup_mesh_cube(self, name: str = "KFCube") -> None:
        """Create a mesh cube for keyframe tests."""
        self._test_tool("mesh_primitive_add", {
            "primitive_type": "CUBE",
            "name": name,
        })

    def test_object_keyframe_insert_location(self) -> None:
        self._setup_mesh_cube()
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 1,
            "location": [1.0, 2.0, 3.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "KFCube")
        self.assertEqual(data["frame"], 1)
        self.assertIn("location", data["inserted"])
        self.assertEqual(data["interpolation"], "BEZIER")

    def test_object_keyframe_insert_rotation(self) -> None:
        self._setup_mesh_cube()
        import math
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 10,
            "rotation": [0.0, 0.0, math.pi / 2],
        })
        self.assertEqual(data["status"], "ok")
        self.assertIn("rotation_euler", data["inserted"])

    def test_object_keyframe_insert_scale(self) -> None:
        self._setup_mesh_cube()
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 5,
            "scale": [2.0, 2.0, 2.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertIn("scale", data["inserted"])

    def test_object_keyframe_insert_all_channels(self) -> None:
        """Insert location + rotation + scale in one call."""
        self._setup_mesh_cube()
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 20,
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
            "scale": [1.0, 1.0, 1.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertIn("location", data["inserted"])
        self.assertIn("rotation_euler", data["inserted"])
        self.assertIn("scale", data["inserted"])

    def test_object_keyframe_insert_linear_interpolation(self) -> None:
        self._setup_mesh_cube()
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 1,
            "location": [0.0, 0.0, 0.0],
            "interpolation": "LINEAR",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["interpolation"], "LINEAR")

    def test_object_keyframe_insert_error_object_not_found(self) -> None:
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "NoSuchObject",
            "frame": 1,
            "location": [0.0, 0.0, 0.0],
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")
        self.assertIsInstance(data["current_state"]["available_objects"], list)

    def test_object_keyframe_insert_error_no_properties(self) -> None:
        self._setup_mesh_cube()
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 1,
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "NO_PROPERTIES")

    def test_object_keyframe_insert_error_invalid_interpolation(self) -> None:
        self._setup_mesh_cube()
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 1,
            "location": [0.0, 0.0, 0.0],
            "interpolation": "EASE_IN",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_INTERPOLATION")

    def test_object_fcurve_list_empty(self) -> None:
        """Object with no animation returns empty curves."""
        self._setup_mesh_cube()
        data = self._test_tool("object_fcurve_list", {
            "object_name": "KFCube",
            "data_path": "location",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data_path"], "location")
        self.assertIsInstance(data["curves"], list)
        self.assertEqual(len(data["curves"]), 0)

    def test_object_fcurve_list_after_insert(self) -> None:
        """F-Curve data matches what was inserted."""
        self._setup_mesh_cube()
        self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 1,
            "location": [0.0, 0.0, 0.0],
            "interpolation": "LINEAR",
        })
        self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 30,
            "location": [3.0, 0.0, 0.0],
            "interpolation": "LINEAR",
        })
        data = self._test_tool("object_fcurve_list", {
            "object_name": "KFCube",
            "data_path": "location",
        })
        self.assertEqual(data["status"], "ok")
        # Should have 3 curves (X, Y, Z).
        self.assertEqual(len(data["curves"]), 3)
        # Find X axis (array_index 0).
        x_curve = next(c for c in data["curves"] if c["array_index"] == 0)
        kfs = x_curve["keyframes"]
        self.assertEqual(len(kfs), 2)
        self.assertEqual(kfs[0]["frame"], 1)
        self.assertAlmostEqual(kfs[0]["value"], 0.0, places=4)
        self.assertEqual(kfs[0]["interpolation"], "LINEAR")
        self.assertEqual(kfs[1]["frame"], 30)
        self.assertAlmostEqual(kfs[1]["value"], 3.0, places=4)

    def test_object_fcurve_list_rotation(self) -> None:
        """rotation_euler data_path is accepted."""
        self._setup_mesh_cube()
        self._test_tool("object_keyframe_insert", {
            "object_name": "KFCube",
            "frame": 1,
            "rotation": [0.0, 0.0, 0.0],
        })
        data = self._test_tool("object_fcurve_list", {
            "object_name": "KFCube",
            "data_path": "rotation_euler",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(len(data["curves"]), 3)

    def test_object_fcurve_list_error_invalid_data_path(self) -> None:
        self._setup_mesh_cube()
        data = self._test_tool("object_fcurve_list", {
            "object_name": "KFCube",
            "data_path": "color",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_DATA_PATH")
        self.assertIsInstance(data["current_state"]["supported_data_paths"], list)

    def test_object_fcurve_list_error_object_not_found(self) -> None:
        data = self._test_tool("object_fcurve_list", {
            "object_name": "NoSuchObject",
            "data_path": "location",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")

    # -----------------------------------------------------------------
    # Modifier tools (REQ-11).

    def test_object_modifier_add_subsurf(self) -> None:
        data = self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "SUBSURF",
            "name": "MySub",
            "params": {"levels": 2, "render_levels": 3},
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "Cube")
        self.assertEqual(data["modifier_name"], "MySub")
        self.assertEqual(data["modifier_type"], "SUBSURF")
        self.assertIn("levels", data["applied_params"])
        self.assertIn("render_levels", data["applied_params"])

    def test_object_modifier_add_wave(self) -> None:
        data = self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "WAVE",
            "params": {"height": 0.5, "width": 1.5, "speed": 2.0},
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["modifier_type"], "WAVE")
        self.assertIn("height", data["applied_params"])
        self.assertIn("width", data["applied_params"])
        self.assertIn("speed", data["applied_params"])

    def test_object_modifier_add_default_name(self) -> None:
        """Omitting name auto-generates one."""
        data = self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "SOLIDIFY",
        })
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["modifier_name"], str)
        self.assertTrue(len(data["modifier_name"]) > 0)

    def test_object_modifier_add_no_params(self) -> None:
        """Modifier added without any params has empty applied/failed lists."""
        data = self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "BEVEL",
        })
        self.assertEqual(data["status"], "ok")
        self.assertIsInstance(data["applied_params"], list)
        self.assertIsInstance(data["failed_params"], list)

    def test_object_modifier_add_error_object_not_found(self) -> None:
        data = self._test_tool("object_modifier_add", {
            "object_name": "NoSuchObject",
            "modifier_type": "SUBSURF",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")

    def test_object_modifier_add_error_invalid_type(self) -> None:
        data = self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "FAKE_MOD",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_MODIFIER_TYPE")
        self.assertIsInstance(data["hint"], str)

    def test_object_modifiers_list_empty(self) -> None:
        """Fresh mesh object has no modifiers."""
        self._test_tool("mesh_primitive_add", {
            "primitive_type": "PLANE",
            "name": "CleanPlane",
        })
        data = self._test_tool("object_modifiers_list", {
            "object_name": "CleanPlane",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "CleanPlane")
        self.assertIsInstance(data["modifiers"], list)
        self.assertEqual(len(data["modifiers"]), 0)

    def test_object_modifiers_list_after_add(self) -> None:
        """Modifier added via object_modifier_add is returned by list."""
        self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "SUBSURF",
            "name": "ListCheck",
            "params": {"levels": 2},
        })
        data = self._test_tool("object_modifiers_list", {
            "object_name": "Cube",
        })
        self.assertEqual(data["status"], "ok")
        names = [m["name"] for m in data["modifiers"]]
        self.assertIn("ListCheck", names)
        sub_mod = next(m for m in data["modifiers"] if m["name"] == "ListCheck")
        self.assertEqual(sub_mod["type"], "SUBSURF")
        self.assertIsInstance(sub_mod["params"], dict)
        self.assertEqual(sub_mod["params"].get("levels"), 2)

    def test_object_modifiers_list_params_roundtrip(self) -> None:
        """Params set via object_modifier_add are read back correctly."""
        self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "WAVE",
            "name": "WaveCheck",
            "params": {"height": 0.75, "speed": 1.5},
        })
        data = self._test_tool("object_modifiers_list", {
            "object_name": "Cube",
        })
        wave = next(
            (m for m in data["modifiers"] if m["name"] == "WaveCheck"), None,
        )
        self.assertIsNotNone(wave)
        self.assertAlmostEqual(wave["params"].get("height"), 0.75, places=4)
        self.assertAlmostEqual(wave["params"].get("speed"), 1.5, places=4)

    def test_object_modifiers_list_error_object_not_found(self) -> None:
        data = self._test_tool("object_modifiers_list", {
            "object_name": "NoSuchObject",
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")

    def test_object_modifier_visible_in_detail_summary(self) -> None:
        """Modifier added to Cube appears in get_object_detail_summary."""
        self._test_tool("object_modifier_add", {
            "object_name": "Cube",
            "modifier_type": "SUBSURF",
            "name": "DetailCheck",
        })
        detail = self._test_tool("get_object_detail_summary", {"name": "Cube"})
        mod_names = [m["name"] for m in detail.get("modifiers", [])]
        self.assertIn("DetailCheck", mod_names)

    # -----------------------------------------------------------------
    # Camera animation tools (REQ-10).

    def test_camera_position_keyframe(self) -> None:
        """Camera position keyframe via object_keyframe_insert."""
        data = self._test_tool("object_keyframe_insert", {
            "object_name": "Camera",
            "frame": 1,
            "location": [0.0, -8.0, 5.0],
            "interpolation": "LINEAR",
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object_name"], "Camera")
        self.assertIn("location", data["inserted"])

    def test_camera_target_track_basic(self) -> None:
        """Set up Track-To constraint using scene camera."""
        data = self._test_tool("camera_target_track", {
            "target_location": [0.0, 0.0, 0.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["camera_name"], "Camera")
        self.assertIsInstance(data["target_name"], str)
        self.assertTrue(data["target_name"])
        self.assertIsInstance(data["constraint_name"], str)
        self.assertEqual(data["frame"], -1)

    def test_camera_target_track_explicit_camera(self) -> None:
        """Explicit camera_name resolves correctly."""
        data = self._test_tool("camera_target_track", {
            "camera_name": "Camera",
            "target_name": "FocusPoint",
            "target_location": [1.0, 0.0, 0.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["camera_name"], "Camera")
        self.assertEqual(data["target_name"], "FocusPoint")

    def test_camera_target_track_with_keyframe(self) -> None:
        """Insert keyframe on target and verify via object_fcurve_list."""
        self._test_tool("camera_target_track", {
            "target_name": "CamTarget",
            "target_location": [0.0, 0.0, 0.0],
            "frame": 1,
            "interpolation": "LINEAR",
        })
        self._test_tool("camera_target_track", {
            "target_name": "CamTarget",
            "target_location": [5.0, 0.0, 0.0],
            "frame": 30,
            "interpolation": "LINEAR",
        })
        fcurve = self._test_tool("object_fcurve_list", {
            "object_name": "CamTarget",
            "data_path": "location",
        })
        self.assertEqual(fcurve["status"], "ok")
        self.assertEqual(len(fcurve["curves"]), 3)
        x_curve = next(c for c in fcurve["curves"] if c["array_index"] == 0)
        self.assertEqual(len(x_curve["keyframes"]), 2)
        self.assertEqual(x_curve["keyframes"][0]["frame"], 1)
        self.assertAlmostEqual(x_curve["keyframes"][0]["value"], 0.0, places=4)
        self.assertEqual(x_curve["keyframes"][1]["frame"], 30)
        self.assertAlmostEqual(x_curve["keyframes"][1]["value"], 5.0, places=4)
        self.assertEqual(x_curve["keyframes"][0]["interpolation"], "LINEAR")

    def test_camera_target_track_idempotent(self) -> None:
        """Calling twice with the same target does not duplicate the constraint."""
        self._test_tool("camera_target_track", {
            "target_name": "StableTarget",
            "target_location": [0.0, 0.0, 0.0],
        })
        d2 = self._test_tool("camera_target_track", {
            "target_name": "StableTarget",
            "target_location": [1.0, 0.0, 0.0],
        })
        self.assertEqual(d2["status"], "ok")
        # Verify only one Track-To constraint exists via execute_blender_code.
        check = self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "cam = bpy.data.objects['Camera']\n"
                "target = bpy.data.objects.get('StableTarget')\n"
                "count = sum(\n"
                "    1 for c in cam.constraints\n"
                "    if c.type == 'TRACK_TO' and c.target == target\n"
                ")\n"
                "result = {'constraint_count': count}\n"
            ),
        })
        self.assertEqual(check["constraint_count"], 1)

    def test_camera_target_track_auto_target_name(self) -> None:
        """When target_name is omitted, it defaults to '{camera}_Target'."""
        data = self._test_tool("camera_target_track", {
            "camera_name": "Camera",
            "target_location": [0.0, 0.0, 0.0],
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["target_name"], "Camera_Target")

    def test_camera_target_track_error_not_camera(self) -> None:
        data = self._test_tool("camera_target_track", {
            "camera_name": "Cube",
            "target_location": [0.0, 0.0, 0.0],
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "INVALID_OBJECT_TYPE")
        self.assertIsInstance(data["current_state"]["available_cameras"], list)

    def test_camera_target_track_error_object_not_found(self) -> None:
        data = self._test_tool("camera_target_track", {
            "camera_name": "NoSuchCamera",
            "target_location": [0.0, 0.0, 0.0],
        })
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")

    # -----------------------------------------------------------------
    # Render tools.

    def _assert_valid_png(self, filepath: str) -> None:
        """
        Ask Blender to verify that *filepath* is a valid PNG file.
        """
        data = self._test_tool("execute_blender_code", {
            "code": (
                "import os\n"
                "with open({!r}, 'rb') as fh:\n"
                "    header = fh.read(8)\n"
                "result = {{\n"
                "    'size': os.path.getsize({!r}),\n"
                "    'png_magic': header == b'\\x89PNG\\r\\n\\x1a\\n',\n"
                "}}\n"
            ).format(filepath, filepath),
        })
        self.assertGreater(data["size"], 0)
        self.assertTrue(data["png_magic"])

    def _set_cycles_cpu(self) -> None:
        """Switch to Cycles CPU so rendering works in headless environments."""
        def code() -> None:
            import bpy  # type: ignore[import-not-found]
            bpy.context.scene.render.engine = 'CYCLES'
            bpy.context.scene.cycles.device = 'CPU'
            result = {'engine': 'CYCLES'}  # noqa: F841
        self._test_tool("execute_blender_code", {
            "code": _python_fn_body_as_string(code),
        })

    def test_render_thumbnail_to_path(self) -> None:
        self._set_cycles_cpu()
        data = self._test_tool("render_thumbnail_to_path", {
            "output_path": "thumb.png",
        })
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["filepath"].endswith("thumb.png"))
        self._assert_valid_png(data["filepath"])

    def test_render_viewport_to_path(self) -> None:
        self._set_cycles_cpu()
        data = self._test_tool("render_viewport_to_path", {
            "output_path": "render.png",
        })
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["filepath"].endswith("render.png"))
        self._assert_valid_png(data["filepath"])

    def test_render_frame_basic(self) -> None:
        self._set_cycles_cpu()
        data = self._test_tool("render_frame", {
            "output_path": "frame.png",
            "width": 64,
            "height": 64,
        })
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["filepath"].endswith("frame.png"))
        self.assertEqual(data["width"], 64)
        self.assertEqual(data["height"], 64)
        self._assert_valid_png(data["filepath"])

    def test_render_frame_with_frame_override(self) -> None:
        self._set_cycles_cpu()
        data = self._test_tool("render_frame", {
            "output_path": "frame10.png",
            "frame": 10,
            "width": 64,
            "height": 64,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["frame"], 10)
        self._assert_valid_png(data["filepath"])

    def test_render_animation_basic(self) -> None:
        self._set_cycles_cpu()

        def _setup_short_anim() -> None:
            import bpy  # type: ignore[import-not-found]
            bpy.context.scene.frame_start = 1
            bpy.context.scene.frame_end = 2
            result = {"frame_start": bpy.context.scene.frame_start}  # noqa: F841

        self._test_tool("execute_blender_code", {
            "code": _python_fn_body_as_string(_setup_short_anim),
        })

        output = os.path.join(tempfile.gettempdir(), "blender_mcp_test_anim.mp4")
        data = self._test_tool("render_animation", {
            "output_path": output,
            "frame_start": 1,
            "frame_end": 2,
            "width": 64,
            "height": 64,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["frame_start"], 1)
        self.assertEqual(data["frame_end"], 2)
        self.assertEqual(data["width"], 64)
        self.assertEqual(data["height"], 64)
        # Verify output file exists and has content.
        filepath = data["filepath"]
        self.assertTrue(os.path.exists(filepath), f"Video file missing: {filepath}")
        self.assertGreater(os.path.getsize(filepath), 0)

    # -----------------------------------------------------------------
    # Deferred tool response.

    def test_deferred_tool_response(self) -> None:
        """Synthetic test for the deferred response mechanism, not a real tool."""
        if not self._interactive:
            # Deferred responses only apply to interactive (timer-based) mode.
            # Background mode rejects them explicitly.
            return

        # Send code that sets check_is_finished. The deferred response
        # mechanism polls it until it returns a non-None result.
        def deferred_code() -> None:
            import time
            deadline = time.monotonic() + 0.3

            def check_is_finished():  # noqa: F841 (read by the exec namespace)
                if time.monotonic() < deadline:
                    return None
                return {'deferred': True, 'value': 42}
            result = {}  # noqa: F841
        data = self._test_tool("execute_blender_code", {
            "code": _python_fn_body_as_string(deferred_code),
        })
        self.assertTrue(data["deferred"])
        self.assertEqual(data["value"], 42)

    def test_deferred_tool_response_blocking_mode_error(self) -> None:
        """Synthetic test: blocking server modes reject deferred responses clearly."""
        if self._interactive:
            return

        def deferred_code() -> None:
            def check_is_finished():  # noqa: F841 (read by the exec namespace)
                return {'deferred': True, 'value': 42}
            result = {}  # noqa: F841
        data = self._test_tool("execute_blender_code", {
            "code": _python_fn_body_as_string(deferred_code),
        })
        self.assertEqual(data["status"], "error")
        self.assertIn(
            "Deferred responses via `check_is_finished` are only supported by the interactive addon server",
            data["message"],
        )

    def test_deferred_tool_render(self) -> None:
        """Test the deferred path with a real render of a non-trivial scene."""
        if not self._interactive:
            return

        def _setup_render_scene() -> None:
            import bpy  # type: ignore[import-not-found]
            bpy.ops.wm.read_homefile(use_empty=True)
            scene = bpy.context.scene
            # Use Cycles CPU so the render works in headless environments
            # where EEVEE may not have a usable GPU context.
            scene.render.engine = 'CYCLES'
            scene.cycles.device = 'CPU'
            scene.cycles.samples = 16
            scene.render.resolution_x = 960
            scene.render.resolution_y = 540
            # Camera.
            bpy.ops.object.camera_add(location=(7, -7, 5))
            cam = bpy.context.active_object
            cam.rotation_euler = (1.1, 0, 0.8)
            scene.camera = cam
            # Light.
            bpy.ops.object.light_add(type='SUN', location=(5, -3, 8))
            # Grid of spheres with different materials.
            for i in range(6):
                for j in range(6):
                    bpy.ops.mesh.primitive_uv_sphere_add(
                        segments=32, ring_count=16,
                        radius=0.4, location=(i, j, 0),
                    )
                    ob = bpy.context.active_object
                    mat = bpy.data.materials.new('M_{:d}_{:d}'.format(i, j))
                    mat.use_nodes = True
                    bsdf = mat.node_tree.nodes['Principled BSDF']
                    bsdf.inputs['Base Color'].default_value = (
                        i / 5.0, j / 5.0, 0.5, 1.0,
                    )
                    bsdf.inputs['Roughness'].default_value = i / 5.0
                    bsdf.inputs['Metallic'].default_value = j / 5.0
                    ob.data.materials.append(mat)
            # Ground plane.
            bpy.ops.mesh.primitive_plane_add(size=20, location=(2.5, 2.5, -0.5))
            result = {'objects': len(bpy.data.objects)}  # noqa: F841

        self._test_tool("execute_blender_code", {
            "code": _python_fn_body_as_string(_setup_render_scene),
        })

        data = self._test_tool("render_viewport_to_path", {
            "output_path": "deferred_render.png",
        })
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["filepath"].endswith("deferred_render.png"))
        self._assert_valid_png(data["filepath"])

    def test_deferred_tool_response_error(self) -> None:
        """Synthetic test: verify that an exception in check_is_finished is reported."""
        if not self._interactive:
            return

        def deferred_error_code() -> None:
            def check_is_finished():  # noqa: F841
                raise RuntimeError('checker failed')
            result = {}  # noqa: F841
        data = self._test_tool("execute_blender_code", {
            "code": _python_fn_body_as_string(deferred_error_code),
        })
        self.assertEqual(data["status"], "error")
        self.assertIn("checker failed", data["message"])

    # -----------------------------------------------------------------
    # Error handling.

    def test_execute_blender_code_error(self) -> None:
        data = self._test_tool("execute_blender_code", {
            "code": "raise ValueError('test error')",
        })
        self.assertEqual(data["status"], "error")
        self.assertIn("ValueError", data["message"])

    def test_execute_blender_code_blocked_operator(self) -> None:
        """Verify that the sandbox blocks actions which may exit Blender or lose our connection."""
        data = self._test_tool("execute_blender_code", {
            "code": "import bpy; bpy.ops.wm.read_factory_settings()",
        })
        self.assertEqual(data["status"], "error")
        self.assertIn(
            "RuntimeError: Operator 'bpy.ops.wm.read_factory_settings()' is not allowed "
            "in LLM-generated code: Resets all user preferences and startup file, "
            "use bpy.ops.wm.read_homefile() or "
            "bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True) instead",
            data["message"],
        )

    def test_execute_blender_code_blocked_sys_exit(self) -> None:
        """Verify that the sandbox blocks sys.exit()."""
        data = self._test_tool("execute_blender_code", {
            "code": "import sys; sys.exit(1)",
        })
        self.assertEqual(data["status"], "error")
        self.assertIn(
            "RuntimeError: sys.exit() is not allowed in LLM-generated code",
            data["message"],
        )

    def test_jump_to_tab_by_name_error(self) -> None:
        if not self._interactive:
            return
        data = self._test_tool("jump_to_tab_by_name", {"name": "NonExistent"})
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "WORKSPACE_NOT_FOUND")
        self.assertIsInstance(
            data["current_state"]["available_workspaces"], list
        )
        self.assertIsInstance(data["hint"], str)
        self.assertTrue(data["hint"])

    def test_execute_blender_code_for_cli_error(self) -> None:
        self._call_tool_expect_error("execute_blender_code_for_cli", {
            "blend_file": self._blend_path,
            "code": "raise ValueError('cli test error')",
        })

    def test_jump_to_view3d_object_by_name_error(self) -> None:
        if not self._interactive:
            return
        data = self._test_tool("jump_to_view3d_object_by_name", {"name": "NonExistent"})
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "OBJECT_NOT_FOUND")
        self.assertIn("'NonExistent'", data["message"])
        self.assertIn("Cube", data["current_state"]["available_objects"])
        self.assertIsInstance(data["hint"], str)
        self.assertTrue(data["hint"])

    def test_jump_to_view3d_object_data_by_name_error(self) -> None:
        if not self._interactive:
            return
        data = self._test_tool("jump_to_view3d_object_data_by_name", {"name": "NonExistent"})
        self.assertEqual(data["status"], "error")
        self.assertEqual(data["error_code"], "DATA_NOT_FOUND")
        self.assertIn("'NonExistent'", data["message"])
        self.assertIsInstance(data["current_state"]["available_data_names"], list)
        self.assertIsInstance(data["hint"], str)
        self.assertTrue(data["hint"])

    # -----------------------------------------------------------------
    # State verification.

    def test_jump_to_view3d_object_by_name_allow_edits(self) -> None:
        """
        Verify that ``allow_edits`` un-hides a hidden object.
        """
        if not self._interactive:
            return
        # Hide the default Cube.
        self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "bpy.data.objects['Cube'].hide_viewport = True\n"
                "result = {'hidden': True}\n"
            ),
        })
        # Jump to it with allow_edits enabled.
        data = self._test_tool("jump_to_view3d_object_by_name", {
            "name": "Cube", "allow_edits": True,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["object"], "Cube")
        # Verify the object is no longer hidden.
        check = self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "result = {'hide_viewport': bpy.data.objects['Cube'].hide_viewport}\n"
            ),
        })
        self.assertFalse(check["hide_viewport"])

    def test_jump_to_view3d_object_data_by_name_allow_edits(self) -> None:
        """
        Verify that ``allow_edits`` un-hides an object found by data name.
        """
        if not self._interactive:
            return
        # Hide the default Cube.
        self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "bpy.data.objects['Cube'].hide_viewport = True\n"
                "result = {'hidden': True}\n"
            ),
        })
        # Jump to it via data name with allow_edits enabled.
        data = self._test_tool("jump_to_view3d_object_data_by_name", {
            "name": "Cube", "allow_edits": True,
        })
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["data_name"], "Cube")
        # Verify the object is no longer hidden.
        check = self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "result = {'hide_viewport': bpy.data.objects['Cube'].hide_viewport}\n"
            ),
        })
        self.assertFalse(check["hide_viewport"])

    def test_execute_blender_code_stateful(self) -> None:
        """
        Verify that the Blender session is stateful across tool calls.
        """
        # Create an object.
        self._test_tool("execute_blender_code", {
            "code": (
                "import bpy\n"
                "bpy.ops.mesh.primitive_ico_sphere_add()\n"
                "bpy.context.active_object.name = 'TestSphere'\n"
                "result = {'created': True}\n"
            ),
        })
        # Verify it exists in a separate call.
        data = self._test_tool("execute_blender_code", {
            "code": "import bpy\nresult = {'found': 'TestSphere' in bpy.data.objects}\n",
        })
        self.assertTrue(data["found"])


# -----------------------------------------------------------------------------
# Concrete test classes.

class TestBackgroundServer(_TestServerMixin, unittest.TestCase):
    """
    Run all tests against Blender in ``--background`` mode.
    """

    _background = True
    _port = _PORT_BACKGROUND


class TestForegroundServer(_TestServerMixin, unittest.TestCase):
    """
    Run all tests against Blender without ``--background`` (full GUI).
    """

    _background = False
    _port = _PORT_FOREGROUND


class TestInteractiveServer(_TestServerMixin, unittest.TestCase):
    """
    Run all tests against Blender in interactive mode (timer-based polling).
    """

    _background = False
    _interactive = True
    _port = _PORT_INTERACTIVE


class TestReuseServer(_TestServerMixin, unittest.TestCase):
    """
    Run tests against an **already-running** Blender with the MCP addon enabled.

    Set ``BLENDER_MCP_REUSE=1`` and run only this class::

        $env:BLENDER_MCP_REUSE = "1"
        python -m pytest tests/test_blender_mcp_with_blender.py -k TestReuseServer -v

    The socket port is taken from ``BLENDER_MCP_PORT`` (default 9876, the
    addon's default).  Blender must already be open and the MCP server started
    inside it before running these tests.

    All tests that apply to an interactive (GUI) Blender are included.
    Tests that require ``--background`` mode are skipped automatically.
    """

    _reuse_mode = True
    _background = False
    _interactive = True
    _port = int(os.environ.get("BLENDER_MCP_PORT", str(_PORT_BACKGROUND)))


BLENDER_VERSION_MIN = (5, 1)


def test_binaries_available() -> bool:
    """
    Check required binaries are available, print errors for any that are missing.
    """
    blender_bin = os.environ.get("BLENDER_BIN", "blender")
    blender_mcp = os.environ.get("BLENDER_MCP", "blender-mcp")
    ok = True
    if not shutil.which(blender_bin):
        print("ERROR: '{:s}' not found in PATH (set BLENDER_BIN)".format(blender_bin))
        ok = False
    if not shutil.which(blender_mcp):
        print("ERROR: '{:s}' not found in PATH (set BLENDER_MCP)".format(blender_mcp))
        ok = False
    return ok


def test_blender_version() -> bool:
    """
    Check the Blender version is at least ``BLENDER_VERSION_MIN``.
    """
    import re
    blender_bin = os.environ.get("BLENDER_BIN", "blender")
    result = subprocess.run(
        [blender_bin, "--version"],
        capture_output=True,
    )
    output = result.stdout.decode("utf-8", errors="replace")
    match = re.search(r"Blender\s+(\d+)\.(\d+)", output)
    if not match:
        print("ERROR: could not parse Blender version from: {:s}".format(output.strip()))
        return False
    version = (int(match.group(1)), int(match.group(2)))
    if version < BLENDER_VERSION_MIN:
        print("ERROR: Blender {:d}.{:d} found, {:d}.{:d} or newer required".format(
            *version, *BLENDER_VERSION_MIN,
        ))
        return False
    return True


if __name__ == "__main__":
    if not test_binaries_available():
        sys.exit(1)
    if not test_blender_version():
        sys.exit(1)
    unittest.main()
