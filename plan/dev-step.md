# 详细开发步骤

> M0 已完成（blmcp 官方实现已集成）。本文从 M1 开始。

---

## 学习期：Blender Python 实验（进入 M1 前必做）

在动手写工具之前，先在 Blender 的 Python Console 里把核心 API 摸清楚。

### 环境准备

1. 安装 Blender 4.0+
2. 打开 Blender → 顶部菜单切换为 **Scripting** 工作区

### 实验 1：bpy 基础对象模型

```python
import bpy

bpy.context.scene.objects.keys()        # 查看当前场景所有对象
bpy.context.active_object              # 查看活跃对象

bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
cube = bpy.context.active_object
cube.location.x = 3.0
```

### 实验 2：Grease Pencil 基础

```python
import bpy

# data API 方式（比 ops 可靠）
gp_data = bpy.data.grease_pencils.new("MyGP")
gp_obj  = bpy.data.objects.new("MyGP", gp_data)
bpy.context.collection.objects.link(gp_obj)

layer = gp_data.layers.new("outline", set_active=True)
frame = layer.frames.new(1)

stroke = frame.strokes.new()
stroke.display_mode = '3DSPACE'   # 必须设置
stroke.points.add(count=3)
stroke.points[0].co = (0, 0, 0)
stroke.points[1].co = (1, 0, 0)
stroke.points[2].co = (1, 1, 0)

bpy.context.view_layer.update()
```

### 实验 3：GP 材质

```python
mat = bpy.data.materials.new("RedStroke")
bpy.data.materials.create_gpencil_data(mat)
mat.grease_pencil.color = (1, 0, 0, 1)
mat.grease_pencil.fill_color = (1, 0.5, 0, 0.8)
gp_obj.data.materials.append(mat)
```

### 实验 4：关键帧动画（透明度）

```python
gp_obj = bpy.data.objects["MyGP"]
layer  = gp_obj.data.layers[0]

layer.opacity = 1.0
layer.keyframe_insert(data_path="opacity", frame=1)

layer.opacity = 0.0
layer.keyframe_insert(data_path="opacity", frame=60)
```

### 实验 5：画圆

```python
import bpy, math

def draw_circle(frame, cx, cy, radius, n=32):
    gp_obj  = bpy.data.objects["MyGP"]
    layer   = gp_obj.data.layers.active
    f       = layer.frames.new(frame)
    stroke  = f.strokes.new()
    stroke.display_mode = '3DSPACE'
    stroke.points.add(count=n + 1)
    for i in range(n + 1):
        angle = 2 * math.pi * i / n
        stroke.points[i].co = (cx + radius * math.cos(angle),
                               cy + radius * math.sin(angle), 0)

draw_circle(frame=1, cx=0, cy=0, radius=1.5)
bpy.context.view_layer.update()
```

### 学习期检查清单

- [ ] 用 data API 创建 GP 对象（不用 ops）
- [ ] 创建图层 → 创建帧 → 画笔触
- [ ] 给笔触设置颜色材质
- [ ] 给图层透明度插入关键帧
- [ ] 画一个闭合圆形笔触

---

## M0 现状（已完成）

官方 blmcp 实现已集成到 `src/mcp/blmcp/`，Addon 在 `src/addon/`。
可用工具（20 个）：

- 执行任意代码：`execute_blender_code`
- 场景查询：`get_objects_summary`、`get_object_detail_summary`
- 文件信息：`get_blendfile_summary_*`
- 渲染：`render_viewport_to_path`、`render_thumbnail_to_path`
- 截图：`get_screenshot_of_*`
- 文档搜索：`search_api_docs`、`search_manual_docs`
- UI 导航：`jump_to_*`

**验收**：`uv run blender-mcp --help` 正常，20 个工具全部识别。

---

## M1 开发任务：Grease Pencil 矢量动画

在 `src/mcp/blmcp/tools/` 下按需补充专用工具。每个能力对应一对文件：
`capability.py` + `capability_toolcode.py`。

### 待实现能力（按 requirements.md REQ-03 ~ REQ-07）

#### REQ-03：GP 对象与图层管理

- [ ] 创建 GP 对象（返回实际名称，处理 `.001` 后缀）
- [ ] 创建/删除图层
- [ ] 查询对象图层列表

#### REQ-04：笔触绘制

- [ ] 在指定帧/图层绘制坐标序列笔触
- [ ] 按帧替换/追加笔触
- [ ] 预制形状（圆、矩形、直线）

#### REQ-05：GP 材质颜色

- [ ] 创建 GP 材质，设置描边色和填充色
- [ ] 将材质分配给对象

#### REQ-06：图层动画

- [ ] 对图层透明度设置关键帧
- [ ] 读取已有关键帧数据

#### REQ-07：渲染输出

- [ ] 渲染帧序列（补充官方仅有视口渲染的缺口）
- [ ] 设置输出路径、分辨率、帧率

### M1 验收标准

AI 能完成以下任务且不需要调用 `execute_blender_code`：
- 创建 GP 对象并画出指定形状
- 为笔触设置颜色
- 插入透明度关键帧
- 渲染为视频文件

---

## M2 开发任务：关键帧动画

待实现能力（对应 REQ-08 ~ REQ-10）：

- [ ] 创建基础 3D 几何体（立方体、球体等）
- [ ] 对任意属性设置关键帧（位置/旋转/缩放）
- [ ] 读取 F-Curve 数据（供验证）
- [ ] 摄像机关键帧

---

## M3 开发任务：程序动画

待实现能力（对应 REQ-11 ~ REQ-15）：

- [ ] 修改器读取与添加
- [ ] Driver 绑定
- [ ] Geometry Nodes 节点图查询、预制图应用、参数调整
- [ ] 材质摘要查询

---

## M4 开发任务：角色动画

待实现能力（对应 REQ-16 ~ REQ-17）：

- [ ] 外部资产导入（FBX / GLTF）
- [ ] .blend Library Link
- [ ] 预制 Action 应用
- [ ] IK 目标关键帧

---

## 开发工具链

### 调试方法

```bash
# 从终端启动 Blender（能看 Addon print 输出）
"C:\Program Files\Blender Foundation\Blender 4.x\blender.exe"

# 启动 MCP Server
uv run blender-mcp

# 手动测试 TCP 通信（绕过 Claude）
python -c "
import socket, json
s = socket.socket()
s.connect(('127.0.0.1', 6789))
s.sendall(json.dumps({'code': 'result = [o.name for o in bpy.data.objects]'}).encode() + b'\\x00')
print(json.loads(s.recv(65536).rstrip(b'\\x00')))
"
```

### 热重载 Addon

修改 Addon 代码后，在 Blender Scripting 面板执行禁用再启用即可，无需重启 Blender。

### 工作流建议

```
改工具代码 → 重启 MCP Server（重启 Claude Desktop）
                ↓
先用 execute_blender_code 在 Blender Console 验证 bpy 代码正确
                ↓
再封装为专用工具（toolcode.py）
                ↓
端到端测试（Claude → 工具 → Blender → 结果）
```
