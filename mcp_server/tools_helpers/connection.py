"""
Socket client for communicating with the Blender add-on.
"""

__all__ = (
    "get_connection_params",
    "send_code",
)

import json
import os
import socket

_DEFAULT_HOST = "localhost"
_DEFAULT_PORT = 9876
_TIMEOUT = 300.0
_RECV_BUFFER_SIZE = 65536


def get_connection_params() -> tuple[str, int]:
    host = os.environ.get("BLANDER_MCP_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("BLANDER_MCP_PORT", str(_DEFAULT_PORT)))
    return host, port


def send_code(code: str, strict_json: bool) -> dict[str, object]:
    """
    Send Python code to the Blender add-on for execution.

    Returns the response dict with ``status``, ``result`` or ``message``,
    and optionally ``stdout``/``stderr``.
    Raises ``ConnectionError`` when Blender is unreachable.
    """
    host, port = get_connection_params()
    request = json.dumps({
        "type": "execute",
        "code": code,
        "strict_json": strict_json,
    }) + "\0"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(_TIMEOUT)
            sock.connect((host, port))
            sock.sendall(request.encode("utf-8"))

            buf = bytearray()
            while True:
                chunk = sock.recv(_RECV_BUFFER_SIZE)
                if not chunk:
                    break
                buf.extend(chunk)
                if b"\0" in buf:
                    break
    except ConnectionRefusedError as ex:
        raise ConnectionError(
            "Cannot connect to Blender at {:s}:{:d}. "
            "Ensure Blender is running with the MCP addon enabled.".format(
                host, port
            )
        ) from ex
    except socket.timeout as ex:
        raise ConnectionError(
            "Blender connection timed out at {:s}:{:d}".format(host, port)
        ) from ex
    except OSError as ex:
        raise ConnectionError(
            "Socket error communicating with Blender at {:s}:{:d}: {:s}".format(
                host, port, str(ex)
            )
        ) from ex

    if not buf:
        raise ConnectionError("Empty response from Blender")

    line, _sep, _rest = buf.partition(b"\0")
    try:
        response: dict[str, object] = json.loads(line.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as ex:
        raise ConnectionError(
            "Invalid response from Blender: {:s}".format(str(ex))
        ) from ex
    return response
