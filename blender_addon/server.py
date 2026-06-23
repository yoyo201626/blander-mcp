import bpy, threading, socket, json, queue

_command_queue = queue.Queue()
_server_thread = None
_server_socket  = None

# ── TCP Server（子线程，只接收数据，不碰 bpy）────────────────

def _tcp_server():
    global _server_socket
    _server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_socket.bind(("127.0.0.1", 7890))
    _server_socket.listen(5)
    print("[MCP Addon] TCP Server started on port 7890")

    while True:
        try:
            conn, _ = _server_socket.accept()
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk: break
                data += chunk
                if b"\n" in data: break
            if data:
                command = json.loads(data.strip())
                _command_queue.put((command, conn))
        except OSError:
            break

# ── Timer（主线程，安全执行 bpy）─────────────────────────────

def _process_queue():
    while not _command_queue.empty():
        command, conn = _command_queue.get()
        try:
            from . import executor
            result = executor.execute(command)
        except Exception as e:
            result = {"success": False, "error": {"code": "EXECUTOR_ERROR", "message": str(e)}}
        try:
            conn.sendall(json.dumps(result).encode() + b"\n")
            conn.close()
        except Exception:
            pass
    return 0.05  # 每 50ms 检查一次队列

def start():
    global _server_thread
    _server_thread = threading.Thread(target=_tcp_server, daemon=True)
    _server_thread.start()
    bpy.app.timers.register(_process_queue, persistent=True)
    print("[MCP Addon] Timer registered")

def stop():
    global _server_socket
    if _server_socket:
        _server_socket.close()
    if bpy.app.timers.is_registered(_process_queue):
        bpy.app.timers.unregister(_process_queue)