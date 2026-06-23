# 详细开发步骤

> 覆盖范围：学习期 + Phase 0 + Phase 1 + Phase 2（Grease Pencil MVP）
> 后续 Phase 在 MVP 跑通后再细化。

---

## 学习期：Blender Python 实验（1-2 周）

### 目标

在动手写任何代码之前，先在 Blender 的 Python Console 里把核心 API 摸清楚。

### 环境准备

1. 安装 Blender 4.0+（官网下载）
2. 打开 Blender → 顶部菜单切换工作区为 **Scripting**
3. 可以看到 Python Console 和 Text Editor 两个面板

### 实验 1：理解 bpy 基础对象模型

在 Python Console 里逐行运行：

```python
import bpy

# 查看当前场景所有对象
bpy.context.scene.objects.keys()

# 查看活跃对象
bpy.context.active_object

# 创建一个普通 Cube（用 ops，后续 Addon 里会改成 data API）
bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))

# 获取刚创建的 Cube
cube = bpy.context.active_object
cube.name        # 'Cube'
cube.location    # Vector((0.0, 0.0, 0.0))

# 移动它
cube.location.x = 3.0
```

### 实验 2：Grease Pencil 基础

```python
import bpy

# 创建 Grease Pencil 对象（data API 方式，比 ops 更可靠）
gp_data = bpy.data.grease_pencils.new("MyGP")
gp_obj  = bpy.data.objects.new("MyGP", gp_data)
bpy.context.collection.objects.link(gp_obj)

# 创建图层
layer = gp_data.layers.new("outline", set_active=True)

# 在第 1 帧创建帧
frame = layer.frames.new(1)

# 在帧上画一条笔触
stroke = frame.strokes.new()
stroke.display_mode = '3DSPACE'
stroke.points.add(count=3)
stroke.points[0].co = (0, 0, 0)
stroke.points[1].co = (1, 0, 0)
stroke.points[2].co = (1, 1, 0)

# 刷新视图
bpy.context.view_layer.update()
```

运行后应该能在视口看到一条折线。

### 实验 3：Grease Pencil 材质（颜色）

```python
import bpy

# 假设 gp_obj 已经创建（接上面）
gp_obj = bpy.data.objects["MyGP"]
gp_data = gp_obj.data

# 创建材质
mat = bpy.data.materials.new("RedStroke")
bpy.data.materials.create_gpencil_data(mat)
mat.grease_pencil.color = (1, 0, 0, 1)          # 红色描边
mat.grease_pencil.fill_color = (1, 0.5, 0, 0.8)  # 橙色填充

# 绑定到 GP 对象
gp_data.materials.append(mat)

# 笔触使用该材质
stroke = gp_data.layers[0].frames[0].strokes[0]
stroke.material_index = 0
```

### 实验 4：关键帧动画（透明度）

```python
import bpy

gp_obj = bpy.data.objects["MyGP"]
layer  = gp_obj.data.layers[0]

# 第 1 帧：不透明
bpy.context.scene.frame_set(1)
layer.opacity = 1.0
layer.keyframe_insert(data_path="opacity", frame=1)

# 第 60 帧：完全透明
layer.opacity = 0.0
layer.keyframe_insert(data_path="opacity", frame=60)

# 播放动画查看效果
bpy.ops.screen.animation_play()
```

### 实验 5：画圆（预制形状原理）

```python
import bpy, math

def draw_circle(frame, cx, cy, radius, point_count=32):
    gp_obj  = bpy.data.objects["MyGP"]
    gp_data = gp_obj.data
    layer   = gp_data.layers.active

    f = layer.frames.new(frame)
    stroke = f.strokes.new()
    stroke.display_mode = '3DSPACE'
    stroke.points.add(count=point_count + 1)

    for i in range(point_count + 1):
        angle = 2 * math.pi * i / point_count
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        stroke.points[i].co = (x, y, 0)

draw_circle(frame=1, cx=0, cy=0, radius=1.5)
bpy.context.view_layer.update()
```

### 学习期检查清单

在进入 Phase 0 前，确认你能独立完成：

- [ ] 用 data API 创建 GP 对象（不用 ops）
- [ ] 创建图层 → 创建帧 → 画笔触
- [ ] 给笔触设置颜色材质
- [ ] 给图层透明度插入关键帧
- [ ] 画一个闭合圆形笔触

---

## Phase 0：项目脚手架（3 天）

### Day 1：项目初始化

```bash
# 创建项目
mkdir blender-animation-mcp && cd blender-animation-mcp
uv init
uv add mcp pydantic

# 目录结构
mkdir -p mcp_server/{tools,state,bridge,schemas}
mkdir -p blender_addon/handlers
mkdir -p dsl/examples
touch mcp_server/__init__.py
touch mcp_server/main.py
touch mcp_server/bridge/blender_client.py
touch mcp_server/state/scene_state.py
touch blender_addon/__init__.py
touch blender_addon/server.py
touch blender_addon/executor.py
```

### Day 2：MCP Server 骨架

`mcp_server/main.py`：

```python
from mcp.server import Server
from mcp.server.stdio import stdio_server
import asyncio

app = Server("blender-animation-mcp")

@app.tool()
async def system_ping() -> dict:
    """Ping Blender to check connection."""
    from mcp_server.bridge.blender_client import BlenderClient
    client = BlenderClient()
    result = await client.send({"tool": "system.ping", "params": {}})
    return result

async def main():
    async with stdio_server() as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
```

`mcp_server/bridge/blender_client.py`：

```python
import asyncio, json

BLENDER_HOST = "127.0.0.1"
BLENDER_PORT = 7890

class BlenderClient:
    async def send(self, command: dict) -> dict:
        try:
            reader, writer = await asyncio.open_connection(BLENDER_HOST, BLENDER_PORT)
            payload = json.dumps(command).encode() + b"\n"
            writer.write(payload)
            await writer.drain()
            data = await reader.readline()
            writer.close()
            await writer.wait_closed()
            return json.loads(data.decode())
        except ConnectionRefusedError:
            return {
                "success": False,
                "error": {
                    "code": "BLENDER_NOT_CONNECTED",
                    "message": "无法连接到 Blender Addon，请确认 Blender 已打开且 Addon 已启用。"
                }
            }
```

### Day 3：Blender Addon 骨架

`blender_addon/__init__.py`：

```python
bl_info = {
    "name": "Animation MCP Runtime",
    "author": "yourname",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "category": "Animation",
}

import bpy
from . import server

def register():
    server.start()

def unregister():
    server.stop()
```

`blender_addon/server.py`：

```python
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
```

`blender_addon/executor.py`：

```python
def execute(command: dict) -> dict:
    tool   = command.get("tool")
    params = command.get("params", {})

    handlers = {
        "system.ping": _ping,
    }

    handler = handlers.get(tool)
    if not handler:
        return {
            "success": False,
            "error": {
                "code": "UNKNOWN_TOOL",
                "message": f"未知工具: {tool}",
                "available_tools": list(handlers.keys())
            }
        }
    return handler(params)

def _ping(params):
    import bpy
    return {
        "success": True,
        "result": {
            "status": "pong",
            "blender_version": ".".join(str(v) for v in bpy.app.version)
        }
    }
```

**验收**：在 Claude Desktop 里说 "ping blender"，看到 pong 响应即 Phase 0 完成。

---

## Phase 1：通信层完善（1 周）

### Day 1-2：Scene State Manager

`mcp_server/state/scene_state.py`：

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class SceneObject:
    name: str
    type: str          # GPENCIL / MESH / CAMERA / LIGHT
    location: list     # [x, y, z]

@dataclass
class SceneState:
    objects: dict[str, SceneObject] = field(default_factory=dict)
    frame_start: int = 1
    frame_end: int   = 250
    frame_current: int = 1

    def add_object(self, obj: SceneObject):
        self.objects[obj.name] = obj

    def remove_object(self, name: str):
        self.objects.pop(name, None)

    def to_dict(self) -> dict:
        return {
            "objects": [
                {"name": o.name, "type": o.type, "location": o.location}
                for o in self.objects.values()
            ],
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "frame_current": self.frame_current,
        }

# 全局单例
_state = SceneState()

def get_state() -> SceneState:
    return _state

def reset():
    global _state
    _state = SceneState()
```

### Day 3-4：统一错误格式 + 基础场景工具

在 `mcp_server/tools/scene.py` 里实现 `scene.create` / `scene.clear` / `scene.get_state`。

每个工具调用后必须更新 Scene State，并在返回结果里带上 `scene_state_delta`：

```python
# 成功返回格式
{
    "success": True,
    "result": { ... },
    "scene_state_delta": {
        "added":    ["object_name"],
        "modified": [],
        "removed":  []
    }
}

# 失败返回格式
{
    "success": False,
    "error": {
        "code":    "OBJECT_NOT_FOUND",
        "message": "对象 'panda' 不存在",
        "hint":    "当前场景对象：['cube', 'camera']"
    }
}
```

### Day 5：Addon 侧对应 Handler

`blender_addon/handlers/scene.py`：

```python
import bpy

def scene_clear(params) -> dict:
    # 删除所有非系统对象
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    return {"success": True, "result": {"cleared": True}}

def scene_get_state(params) -> dict:
    objects = []
    for obj in bpy.context.scene.objects:
        objects.append({
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location)
        })
    return {
        "success": True,
        "result": {
            "objects": objects,
            "frame_current": bpy.context.scene.frame_current,
            "frame_end": bpy.context.scene.frame_end,
        }
    }
```

在 `executor.py` 里注册这些 handler：

```python
from .handlers import scene as scene_handler

handlers = {
    "system.ping":     _ping,
    "scene.clear":     scene_handler.scene_clear,
    "scene.get_state": scene_handler.scene_get_state,
}
```

---

## Phase 2：Grease Pencil MVP（2 周）

### Week 1：核心 GP 操作

#### Day 1-2：vector.create_object + vector.create_layer

`blender_addon/handlers/grease_pencil.py`：

```python
import bpy

def create_object(params) -> dict:
    name = params.get("name", "GPObject")

    # 用 data API，不用 ops（更可靠、不依赖 context）
    gp_data = bpy.data.grease_pencils.new(name)
    gp_obj  = bpy.data.objects.new(name, gp_data)
    bpy.context.collection.objects.link(gp_obj)

    return {
        "success": True,
        "result": {"name": name, "type": "GPENCIL"}
    }

def create_layer(params) -> dict:
    obj_name   = params["object"]
    layer_name = params.get("layer", "Layer")

    obj = bpy.data.objects.get(obj_name)
    if not obj or obj.type != 'GPENCIL':
        return _obj_not_found(obj_name)

    layer = obj.data.layers.new(layer_name, set_active=True)
    return {
        "success": True,
        "result": {"layer": layer_name}
    }

def _obj_not_found(name):
    available = [o.name for o in bpy.data.objects if o.type == 'GPENCIL']
    return {
        "success": False,
        "error": {
            "code": "OBJECT_NOT_FOUND",
            "message": f"GP 对象 '{name}' 不存在",
            "hint": f"当前 GP 对象：{available}"
        }
    }
```

#### Day 3-4：vector.draw_stroke + vector.draw_shape

```python
def draw_stroke(params) -> dict:
    obj_name   = params["object"]
    layer_name = params.get("layer", "Layer")
    frame_num  = params.get("frame", 1)
    points     = params["points"]   # [[x,y,z], ...]

    obj = bpy.data.objects.get(obj_name)
    if not obj: return _obj_not_found(obj_name)

    layer = obj.data.layers.get(layer_name)
    if not layer:
        return {"success": False, "error": {"code": "LAYER_NOT_FOUND", "message": f"图层 '{layer_name}' 不存在"}}

    # 获取或创建帧
    frame = layer.frames.get(frame_num)
    if not frame:
        frame = layer.frames.new(frame_num)

    stroke = frame.strokes.new()
    stroke.display_mode = '3DSPACE'
    stroke.points.add(count=len(points))
    for i, pt in enumerate(points):
        stroke.points[i].co = tuple(pt)

    bpy.context.view_layer.update()
    return {"success": True, "result": {"stroke_index": len(frame.strokes) - 1}}


import math

def draw_shape(params) -> dict:
    shape  = params["shape"]    # "circle" / "rect" / "line"
    obj_name   = params["object"]
    layer_name = params.get("layer", "Layer")
    frame_num  = params.get("frame", 1)

    if shape == "circle":
        cx, cy = params.get("center", [0, 0])
        r      = params.get("radius", 1.0)
        n      = params.get("segments", 32)
        pts    = [[cx + r*math.cos(2*math.pi*i/n),
                   cy + r*math.sin(2*math.pi*i/n), 0]
                  for i in range(n+1)]
    elif shape == "rect":
        x, y = params.get("origin", [0, 0])
        w, h = params.get("size", [1, 1])
        pts  = [[x,y,0],[x+w,y,0],[x+w,y+h,0],[x,y+h,0],[x,y,0]]
    elif shape == "line":
        pts = [params["start"] + [0], params["end"] + [0]]
    else:
        return {"success": False, "error": {"code": "UNKNOWN_SHAPE", "message": f"未知形状: {shape}"}}

    return draw_stroke({"object": obj_name, "layer": layer_name, "frame": frame_num, "points": pts})
```

#### Day 5：vector.set_material

```python
def set_material(params) -> dict:
    obj_name     = params["object"]
    stroke_color = params.get("stroke_color", [0, 0, 0, 1])   # RGBA
    fill_color   = params.get("fill_color",   [1, 1, 1, 0])   # RGBA, alpha=0 默认不填充
    mat_name     = params.get("material_name", f"{obj_name}_mat")

    obj = bpy.data.objects.get(obj_name)
    if not obj: return _obj_not_found(obj_name)

    mat = bpy.data.materials.new(mat_name)
    bpy.data.materials.create_gpencil_data(mat)
    mat.grease_pencil.color      = tuple(stroke_color)
    mat.grease_pencil.fill_color = tuple(fill_color)
    mat.grease_pencil.show_fill  = fill_color[3] > 0

    obj.data.materials.append(mat)
    mat_index = len(obj.data.materials) - 1

    return {"success": True, "result": {"material_index": mat_index}}
```

### Week 2：动画化 + MCP 工具注册 + 端到端测试

#### Day 1-2：vector.animate_opacity

```python
def animate_opacity(params) -> dict:
    obj_name   = params["object"]
    layer_name = params.get("layer", "Layer")
    keyframes  = params["keyframes"]  # [{"frame": 1, "value": 1.0}, ...]

    obj = bpy.data.objects.get(obj_name)
    if not obj: return _obj_not_found(obj_name)

    layer = obj.data.layers.get(layer_name)
    if not layer:
        return {"success": False, "error": {"code": "LAYER_NOT_FOUND", "message": f"图层 '{layer_name}' 不存在"}}

    for kf in keyframes:
        layer.opacity = kf["value"]
        layer.keyframe_insert(data_path="opacity", frame=kf["frame"])

    return {"success": True, "result": {"keyframe_count": len(keyframes)}}
```

#### Day 3：在 MCP Server 注册所有 vector.* 工具

`mcp_server/tools/vector.py`：

```python
from mcp.server import Server
from mcp_server.bridge.blender_client import BlenderClient
from mcp_server.state.scene_state import get_state, SceneObject

# 由 main.py 调用 register(app) 注册
def register(app: Server):
    client = BlenderClient()

    @app.tool()
    async def vector_create_object(name: str) -> dict:
        """创建 Grease Pencil 矢量对象"""
        result = await client.send({"tool": "vector.create_object", "params": {"name": name}})
        if result.get("success"):
            get_state().add_object(SceneObject(name=name, type="GPENCIL", location=[0,0,0]))
        return result

    @app.tool()
    async def vector_draw_shape(object: str, shape: str, layer: str = "Layer",
                                 frame: int = 1, **kwargs) -> dict:
        """画预制形状：circle / rect / line"""
        params = {"object": object, "shape": shape, "layer": layer, "frame": frame, **kwargs}
        return await client.send({"tool": "vector.draw_shape", "params": params})

    @app.tool()
    async def vector_animate_opacity(object: str, layer: str, keyframes: list) -> dict:
        """给图层透明度插入关键帧，keyframes 格式: [{"frame": 1, "value": 1.0}]"""
        params = {"object": object, "layer": layer, "keyframes": keyframes}
        return await client.send({"tool": "vector.animate_opacity", "params": params})
```

#### Day 4-5：端到端测试 + DSL 示例

测试脚本（`dsl/examples/red_circle_fadeout.json`）：

```json
[
  {
    "tool": "scene.clear",
    "params": {}
  },
  {
    "tool": "vector.create_object",
    "params": { "name": "circle_anim" }
  },
  {
    "tool": "vector.create_layer",
    "params": { "object": "circle_anim", "layer": "main" }
  },
  {
    "tool": "vector.draw_shape",
    "params": {
      "object": "circle_anim",
      "layer": "main",
      "frame": 1,
      "shape": "circle",
      "center": [0, 0],
      "radius": 1.5
    }
  },
  {
    "tool": "vector.set_material",
    "params": {
      "object": "circle_anim",
      "stroke_color": [1, 0, 0, 1],
      "fill_color": [1, 0, 0, 0.3]
    }
  },
  {
    "tool": "vector.animate_opacity",
    "params": {
      "object": "circle_anim",
      "layer": "main",
      "keyframes": [
        { "frame": 1,  "value": 1.0 },
        { "frame": 60, "value": 0.0 }
      ]
    }
  }
]
```

在 Claude Desktop 里用自然语言触发上述序列，确认 Blender 里出现红色圆圈并动画淡出，**Phase 2 MVP 完成**。

---

## 启动教程

> 每次开发前按此顺序操作，确保三个进程都正常运行。

### 前置条件

| 依赖 | 最低版本 | 检查命令 |
|------|----------|----------|
| Blender | 4.0 | `blender --version` |
| Python | 3.11 | `python --version` |
| uv | 任意 | `uv --version` |

首次使用时安装依赖：

```bash
cd blender-animation-mcp
uv sync
```

---

### 第一步：安装 Blender Addon（首次 / 更新时）

1. 打开 Blender
2. 顶部菜单：**Edit → Preferences → Add-ons → Install…**
3. 选择项目根目录下的 `blender_addon/` 文件夹（或先打包：`zip -r blender_addon.zip blender_addon/`，再安装 zip）
4. 在 Add-ons 列表里搜索 **Animation MCP Runtime**，勾选启用

启用后 Blender System Console 应显示：

```
[MCP Addon] TCP Server started on port 7890
[MCP Addon] Timer registered
```

> **Addon 更新后**：重新 Install 覆盖，或在 Scripting 面板执行热重载（见调试教程）。

---

### 第二步：启动 MCP Server

```bash
# 项目根目录
uv run python -m mcp_server.main
```

Server 以 stdio 模式运行，启动后无终端输出属于正常（Claude Desktop 接管 stdin/stdout）。

如需调试输出，用 stderr：

```bash
uv run python -m mcp_server.main 2>mcp_debug.log
```

---

### 第三步：配置 Claude Desktop（首次）

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`（macOS）：

```json
{
  "mcpServers": {
    "blender-animation": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/Admin/projects/blander-mcp",
        "python",
        "-m",
        "mcp_server.main"
      ]
    }
  },
}
```

保存后重启 Claude Desktop，工具栏会出现 blender-animation 工具集。

---

### 第四步：验证整条链路

在 Claude Desktop 里说：

```
ping blender
```

预期 Claude 调用 `system_ping` 工具，返回：

```json
{
  "success": true,
  "result": {
    "status": "pong",
    "blender_version": "4.1.0"
  }
}
```

看到 pong 即代表 Claude → MCP Server → Blender Addon 三段通信全部打通。

---

### 启动顺序总结

```
① 打开 Blender（确认 Addon 已启用，TCP Server 在 7890 端口监听）
         ↓
② 启动 Claude Desktop（自动拉起 MCP Server 子进程）
         ↓
③ 在 Claude 里发指令，验证 ping 响应
```

> **顺序不能反**：MCP Server 启动时会尝试读 stdio，必须由 Claude Desktop 拉起；Blender Addon 要先于 MCP Server 就绪，否则 ping 会返回 BLENDER_NOT_CONNECTED。

---

## 调试教程

### 1. 日志在哪里看

#### Blender System Console（Addon 日志）

- **macOS / Linux**：从终端启动 Blender，所有 `print()` 和异常栈输出到该终端

  ```bash
  /Applications/Blender.app/Contents/MacOS/Blender
  ```

- **Windows**：Blender 菜单 → **Window → Toggle System Console**

Addon 正常启动时会打印：

```
[MCP Addon] TCP Server started on port 7890
[MCP Addon] Timer registered
```

Handler 抛出异常时，`server.py` 会捕获并返回 `EXECUTOR_ERROR`，完整堆栈打印到 System Console。

#### MCP Server 日志

MCP Server 的 stdout 被 Claude Desktop 占用（协议传输），调试日志必须写 stderr：

```python
import sys
print("[MCP] 调试信息", file=sys.stderr)
```

或启动时重定向：

```bash
uv run python -m mcp_server.main 2>>mcp_debug.log
tail -f mcp_debug.log
```

---

### 2. 手动测试 TCP 通信（绕过 Claude）

不启动 Claude，直接用 Python 脚本向 Addon 发命令，快速验证 handler 是否正常：

```python
# scripts/tcp_test.py
import socket, json

def send(command):
    s = socket.socket()
    s.connect(("127.0.0.1", 7890))
    s.sendall(json.dumps(command).encode() + b"\n")
    data = s.recv(4096)
    s.close()
    return json.loads(data)

# 测试连通性
print(send({"tool": "system.ping", "params": {}}))

# 测试场景状态
print(send({"tool": "scene.get_state", "params": {}}))

# 测试未知工具（验证错误格式）
print(send({"tool": "not.exist", "params": {}}))
```

运行：

```bash
python scripts/tcp_test.py
```

---

### 3. 热重载 Addon（不重启 Blender）

修改 Python handler 后，在 Blender **Scripting** 面板的 Text Editor 里执行：

```python
import importlib
import blender_addon
import blender_addon.executor
import blender_addon.server

# 先停止再重新加载
blender_addon.server.stop()
importlib.reload(blender_addon.executor)
importlib.reload(blender_addon.server)
importlib.reload(blender_addon)
blender_addon.server.start()
print("Addon 重载完成")
```

或安装 **Addon Reload** 插件后按 **F8** 一键重载。

> 注意：热重载不会影响已在运行的 Timer，`stop()` + `start()` 确保 Timer 和 TCP Server 都重置。

---

### 4. 常见错误及处理

#### `BLENDER_NOT_CONNECTED`

```json
{"success": false, "error": {"code": "BLENDER_NOT_CONNECTED"}}
```

**原因**：MCP Server 连不上 7890 端口。  
**检查**：
1. Blender 是否已打开？
2. Addon 是否已启用（System Console 有无 "TCP Server started"）？
3. 端口是否被占用：`lsof -i :7890`

---

#### `EXECUTOR_ERROR`

```json
{"success": false, "error": {"code": "EXECUTOR_ERROR", "message": "..."}}
```

**原因**：handler 内部抛出异常。  
**处理**：看 Blender System Console 里的完整 Python traceback，定位到具体 handler 文件和行号。

---

#### `UNKNOWN_TOOL`

```json
{
  "success": false,
  "error": {
    "code": "UNKNOWN_TOOL",
    "message": "未知工具: vector.draw_stroke",
    "available_tools": ["system.ping"]
  }
}
```

**原因**：`executor.py` 的 `handlers` 字典里没有注册该工具。  
**处理**：在 `blender_addon/executor.py` 里添加对应的 handler 映射，并热重载 Addon。

---

#### MCP Server 工具调用超时

Claude Desktop 里工具一直 spinning 无响应。  
**原因**：`BlenderClient.send()` 等待 readline，但 Blender 没有发回响应。  
**检查**：
1. Blender System Console 有无报错？
2. 用 `tcp_test.py` 手动发同一条命令，看 Blender 是否处理。
3. 检查 `_process_queue` timer 是否还在运行（Blender 菜单 → Info 区无报错即正常）。

---

### 5. 调试工作流建议

```
改 handler 代码
    → Blender 热重载 Addon（F8 或 Scripting 面板脚本）
    → 用 tcp_test.py 直接发命令验证返回值
    → 确认无误后再在 Claude 里端到端测试
```

不要每次都走 Claude → 这会引入 LLM 不确定性，让你不知道是 AI 理解错了还是 handler 有 bug。先用 `tcp_test.py` 把 handler 验证正确，再接入 AI。