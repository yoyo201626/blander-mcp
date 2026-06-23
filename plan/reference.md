# Blender Animation MCP — 开发参考手册

> 给 Blender 新手看的关键概念、常见陷阱、调试方法

---

## 一、Blender Addon 开发必读

### Addon 安装方式（开发阶段）

开发阶段不要每次都打 zip。用 symlink：

```bash
# macOS / Linux
ln -s /absolute/path/to/blender-animation-mcp/blender_addon \
  ~/Library/Application\ Support/Blender/4.1/scripts/addons/animation_mcp

# Windows（管理员 PowerShell）
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Blender Foundation\Blender\4.1\scripts\addons\animation_mcp" `
  -Target "C:\absolute\path\to\blender_addon"
```

这样修改代码后，在 Blender 中重新启用 Addon（禁用再启用）即可生效，无需重新安装。

### Blender Python Console 快速测试

在 Blender 顶部菜单 → Scripting 标签页 → 底部 Console 中可以直接运行 bpy 代码：

```python
# 查看场景所有对象
[o.name for o in bpy.data.objects]

# 查看当前 GP 对象的图层
gp = bpy.data.objects["gp_canvas"]
[l.name for l in gp.data.layers]

# 查看某图层的帧
layer = gp.data.layers["outline"]
[(f.frame_number, len(f.strokes)) for f in layer.frames]
```

### Addon 日志查看

Blender 的 print 输出在哪里看取决于启动方式：

```bash
# 从命令行启动 Blender，print 输出到终端
/Applications/Blender.app/Contents/MacOS/Blender

# Windows
"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe"
```

强烈建议开发时从终端启动 Blender，这样能看到 Addon 的所有 print 输出。

---

## 二、进程通信关键知识

### 为什么必须用 bpy.app.timers？

Blender 的 bpy API 不是线程安全的。如果在 TCP 子线程里直接调用 bpy，会出现：

```
# 常见错误：
RuntimeError: Calling operator "bpy.ops.object.gpencil_add" ... outside the main thread
# 或者 Blender 直接 crash
```

正确模式：

```
TCP 子线程
    │ 收到指令
    ▼
_command_queue.put(command)   ← 线程安全的 Queue

bpy.app.timers（主线程，每 50ms 触发）
    │ 轮询队列
    ▼
执行 bpy 操作
    │
    ▼
_response_queue.put(result)   ← 线程安全的 Queue

TCP 子线程
    │ 读取响应
    ▼
发送给 MCP Server
```

### TCP 通信数据格式

发送和接收均以 `\n` 作为消息结束符：

```python
# 发送（MCP Server 侧）
payload = json.dumps({"tool": "ping", "params": {}}) + "\n"
socket.sendall(payload.encode())

# 接收（需要循环读取直到 \n）
data = b""
while True:
    chunk = socket.recv(4096)
    data += chunk
    if data.endswith(b"\n"):
        break
result = json.loads(data.decode())
```

### 超时处理

每次 MCP Server 调用 Blender 都应该设超时：

```python
socket.settimeout(15)  # 15 秒超时
```

如果 Blender 侧 crash 或主线程卡死，MCP Server 会在 15 秒后抛出 `socket.timeout`，而不是永远等待。

---

## 三、Grease Pencil API 速查

### 数据层级

```python
import bpy

gp_obj = bpy.data.objects["gp_canvas"]    # GPencilObject
gp_data = gp_obj.data                      # bpy.types.GreasePencil

# 图层操作
layer = gp_data.layers.new("outline")      # 创建图层
layer = gp_data.layers["outline"]          # 获取图层
gp_data.layers.remove(layer)               # 删除图层
layer.hide = True                          # 隐藏图层
layer.opacity = 0.5                        # 不透明度

# 帧操作
frame = layer.frames.new(1)                # 在第 1 帧创建
frame = layer.frames.get(1)               # 获取（不存在返回 None）
layer.frames.remove(frame)                 # 删除帧

# 笔触操作
stroke = frame.strokes.new()               # 新建笔触
stroke.display_mode = '3DSPACE'            # 必须设置！否则看不到
stroke.material_index = 0                  # 材质索引
stroke.line_width = 10                     # 线宽（整数）

# 点操作
stroke.points.add(count=3)                 # 添加 3 个点
stroke.points[0].co = (0.0, 0.0, 0.0)    # 设置坐标（必须是 float tuple）
stroke.points[0].pressure = 1.0           # 压力（0~1）
stroke.points[0].strength = 1.0           # 强度/透明度（0~1）
```

### 材质设置

```python
# 创建 GP 专用材质
mat = bpy.data.materials.new("my_mat")
mat.use_nodes = False  # GP 材质不用节点

# 设置颜色（RGBA，值域 0~1）
mat.grease_pencil.color = (0.0, 0.0, 0.0, 1.0)        # 笔触颜色（黑色）
mat.grease_pencil.fill_color = (1.0, 0.0, 0.0, 1.0)   # 填充颜色（红色）
mat.grease_pencil.show_fill = True                      # 启用填充

# 将材质添加到 GP 对象
gp_obj.data.materials.append(mat)
```

### 坐标系说明

Blender 使用右手坐标系：

```
X → 右
Y → 前（屏幕内）
Z ↑ 上
```

对于 Grease Pencil 2D 动画，通常在 XZ 平面作画（Y=0），摄像机从 Y 轴负方向往 +Y 看。

如果要做真正的 2D 动画（正视图），建议设置：

```python
# 将 GP 对象限制在 XZ 平面
gp_obj.data.zdepth_offset = 0.0
```

### 图层关键帧动画（不透明度）

```python
# 在第 1 帧设置不透明度为 0（隐藏）
bpy.context.scene.frame_set(1)
layer.opacity = 0.0
layer.keyframe_insert(data_path="opacity", frame=1)

# 在第 24 帧设置不透明度为 1（显示）
layer.opacity = 1.0
layer.keyframe_insert(data_path="opacity", frame=24)
```

---

## 四、MCP Server 开发注意事项

### Tool 描述很重要

AI 完全依赖 Tool 的 `description` 和 `inputSchema` 来决定如何调用。写得越清楚，AI 调用越准确。

好的描述：
```python
description="在 Grease Pencil 指定图层的指定帧上绘制一条笔触。points 是坐标列表 [[x,y,z],...]，至少需要 2 个点。frame 从 1 开始计数。"
```

差的描述：
```python
description="画笔触"
```

### 错误信息必须对 AI 友好

AI 收到错误后会尝试自我纠正，所以错误信息要告诉 AI：
1. 出了什么问题
2. 当前可用的状态是什么
3. 下一步应该怎么做

```python
# 好的错误
{
    "success": False,
    "error": {
        "code": "LAYER_NOT_FOUND",
        "message": "Layer 'outline' not found in object 'gp_canvas'.",
        "hint": "Use vector.init_canvas with layers=['outline'] to create it, or check available layers.",
        "available_layers": ["default", "bg"]
    }
}

# 差的错误
{
    "success": False,
    "error": "KeyError: 'outline'"
}
```

### 异步 vs 同步

MCP Server 是 async 的，但调用 Blender 的 TCP 连接是同步阻塞的。包装方式：

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=4)

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    # 在线程池中执行同步的 TCP 调用，避免阻塞 asyncio 事件循环
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_executor, call_blender, name, arguments)
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
```

---

## 五、Scene State Manager

### 数据结构

```python
# mcp_server/state/scene_state.py

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class GPObject:
    name: str
    layers: list[str] = field(default_factory=list)
    materials: list[str] = field(default_factory=list)

@dataclass
class SceneState:
    gp_objects: dict[str, GPObject] = field(default_factory=dict)
    frame_range: tuple[int, int] = (1, 250)
    fps: int = 24

    def add_gp_object(self, name: str, layers: list[str]):
        self.gp_objects[name] = GPObject(name=name, layers=layers)

    def get_gp_object(self, name: str) -> Optional[GPObject]:
        return self.gp_objects.get(name)

    def to_summary(self) -> dict:
        return {
            "gp_objects": {
                name: {"layers": obj.layers, "materials": obj.materials}
                for name, obj in self.gp_objects.items()
            },
            "frame_range": self.frame_range,
            "fps": self.fps
        }

# 全局单例
_state = SceneState()

def get_state() -> SceneState:
    return _state
```

### 在 Tool 中更新 State

```python
# mcp_server/main.py 中

from mcp_server.state.scene_state import get_state

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    state = get_state()
    result = await loop.run_in_executor(_executor, call_blender, name, arguments)

    # 根据返回结果更新 state
    if result.get("success"):
        delta = result.get("scene_state_delta", {})
        for obj_name in delta.get("added", []):
            if name == "vector.init_canvas":
                state.add_gp_object(obj_name, arguments.get("layers", ["default"]))

    # 将当前 state 摘要附加到返回值（让 AI 了解场景现状）
    result["current_scene"] = state.to_summary()
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
```

---

## 六、常见问题与调试

### 问题：Blender 收到指令但没有反应

可能原因：
1. `bpy.app.timers` 没有注册 → 检查 `register()` 是否被调用
2. 指令在队列里但 timer 没触发 → 尝试在 Blender 中移动鼠标（触发事件循环）
3. handler 抛出了异常但被吞掉了 → 在 executor 的 `except` 里加 `print(traceback.format_exc())`

### 问题：GP 对象创建了但看不见

原因：`stroke.display_mode` 没有设置为 `'3DSPACE'`

```python
stroke.display_mode = '3DSPACE'  # 必须！
```

### 问题：Blender crash 而不是报错

原因：在非主线程调用了 bpy。检查所有 bpy 调用是否都在 timer 回调里。

### 问题：MCP Server 超时

可能原因：
1. Blender Addon 没有启动 TCP Server → 检查 Blender 终端是否有 "TCP Server listening" 输出
2. 防火墙阻断了 localhost:7890 → 关闭防火墙或检查端口
3. Blender 主线程卡住 → 查看 Blender 是否在执行长时间操作（如渲染）

### 问题：颜色显示不对

Blender 内部使用线性颜色空间，而我们输入的通常是 sRGB。对于简单情况（纯色）影响不大，但如果颜色明显偏亮，需要：

```python
import bpy
# 开启颜色管理时，GP 颜色是 linear 的
# 纯黑 (0,0,0) 和纯白 (1,1,1) 不受影响
# 中间灰度值会有差异
```

---

## 七、开发工作流建议

### 每天开发流程

```
1. 从终端启动 Blender（能看 print 日志）
2. 启用 Animation MCP Runtime Addon
3. 确认终端显示 "TCP Server listening on localhost:7890"
4. 运行 MCP Server：uv run python -m mcp_server.main
5. 在 Claude Desktop 中测试新 Tool
6. 如需修改 Addon：
   a. 修改代码
   b. 在 Blender 中禁用 Addon → 重新启用（不需要重启 Blender）
7. 如需修改 MCP Server：
   a. 修改代码
   b. 重启 Claude Desktop（MCP Server 随之重启）
```

### 单个 handler 的测试方法

不必每次都通过 Claude 测试，可以直接在 Blender Console 里测试 handler：

```python
# 在 Blender Scripting 标签页里
import sys
sys.path.insert(0, "/absolute/path/to/blender-animation-mcp")

from blender_addon.handlers.grease_pencil import init_canvas, draw_stroke

# 直接调用
result = init_canvas({"name": "test_canvas", "layers": ["outline"]})
print(result)

result = draw_stroke({
    "object_name": "test_canvas",
    "layer": "outline",
    "frame": 1,
    "points": [[0,0,0],[1,0,0],[2,1,0]]
})
print(result)
```

---

## 八、DSL 示例文件格式

`dsl/examples/` 目录下存放完整的调用示例，便于测试和文档：

### dsl/examples/simple_line_animation.json

```json
{
  "description": "一条从短到长的线条动画，24帧",
  "steps": [
    {
      "tool": "vector.init_canvas",
      "params": { "name": "canvas", "layers": ["outline"] }
    },
    {
      "tool": "vector.set_material",
      "params": {
        "object_name": "canvas",
        "material_name": "black_stroke",
        "stroke_color": [0, 0, 0, 1]
      }
    },
    {
      "tool": "vector.animate_stroke",
      "params": {
        "object_name": "canvas",
        "layer": "outline",
        "material_index": 0,
        "line_width": 15,
        "keyframes": [
          { "frame": 1,  "points": [[0,0,0],[0.5,0,0]] },
          { "frame": 8,  "points": [[0,0,0],[1.0,0,0]] },
          { "frame": 16, "points": [[0,0,0],[1.5,0,0]] },
          { "frame": 24, "points": [[0,0,0],[2.0,0,0]] }
        ]
      }
    },
    {
      "tool": "render.video",
      "params": {
        "output": "/tmp/line_grow.mp4",
        "start": 1,
        "end": 24,
        "fps": 24,
        "resolution": [1280, 720]
      }
    }
  ]
}
```

---

## 九、pyproject.toml 参考

```toml
[project]
name = "blender-animation-mcp"
version = "0.1.0"
description = "MCP-driven animation runtime for Blender"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
]

[project.scripts]
anim-mcp = "mcp_server.main:run"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

---

## 十、版本兼容性记录

| 组件 | 版本 | 备注 |
|------|------|------|
| Blender | 4.1.x | Grease Pencil 3 API 在此版本稳定 |
| Python（Blender 内置） | 3.11 | 无法更改，Addon 用此版本 |
| Python（MCP Server） | 3.11+ | 与 Blender 内置版本一致 |
| mcp SDK | 1.x | Anthropic 官方 |
| uv | 最新 | 包管理器 |

> ⚠️ Blender 4.2+ 对 Grease Pencil 有较大改动（GPv3），如果升级 Blender 版本，需要检查 `grease_pencil.py` 中的所有 API 调用。