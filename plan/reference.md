# Blender Animation MCP — 开发参考手册

> 给 Blender 新手看的关键概念、常见陷阱、调试方法。

---

## 一、Addon 安装与开发

### 开发阶段用 symlink，不要每次打 zip

```powershell
# Windows（管理员 PowerShell）
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Blender Foundation\Blender\4.x\scripts\addons\blender_mcp_addon" `
  -Target "D:\data\projects\blander-mcp\src\addon\blender_mcp_addon"
```

修改代码后在 Blender 中重新启用 Addon 即可生效，无需重装。

### Blender Python Console 快速测试

在 Blender → Scripting 标签页 → 底部 Console 中直接运行 bpy 代码：

```python
[o.name for o in bpy.data.objects]                       # 场景对象列表
[l.name for l in bpy.data.objects["MyGP"].data.layers]  # GP 图层列表
```

### Addon 日志查看

从命令行启动 Blender，`print()` 输出到该终端：

```bash
# Windows
"C:\Program Files\Blender Foundation\Blender 4.x\blender.exe"
```

---

## 二、进程通信关键知识

### 为什么必须用 bpy.app.timers？

bpy API 不是线程安全的。在 TCP 子线程里直接调用 bpy 会 crash。正确模式：

```
TCP 子线程
    │ 收到指令
    ▼
_command_queue.put(command)   ← 线程安全的 Queue

bpy.app.timers（主线程，每 50ms 触发）
    │ 轮询队列 → 执行 bpy 操作
    ▼
将结果放回响应队列

TCP 子线程
    │ 读取响应
    ▼
发送给 MCP Server
```

### TCP 通信数据格式

Addon 使用 null byte（`\x00`）作为消息分隔符：

```python
# 发送
payload = json.dumps({"code": "..."}).encode() + b"\x00"
socket.sendall(payload)

# 接收（读取直到 null byte）
data = b""
while True:
    chunk = socket.recv(4096)
    data += chunk
    if b"\x00" in data:
        break
result = json.loads(data.rstrip(b"\x00"))
```

### 超时处理

每次 MCP Server 调用 Blender 设 30 秒超时：

```python
socket.settimeout(30)
```

---

## 三、Grease Pencil API 速查

### 数据层级

```python
gp_obj  = bpy.data.objects["gp_canvas"]   # Object
gp_data = gp_obj.data                      # bpy.types.GreasePencil

# 图层
layer = gp_data.layers.new("outline")      # 创建
layer = gp_data.layers["outline"]          # 获取
layer.opacity = 0.5                        # 不透明度
layer.hide = True                          # 隐藏

# 帧
frame = layer.frames.new(1)                # 在第 1 帧创建
frame = layer.frames.get(1)               # 获取（不存在返回 None）

# 笔触
stroke = frame.strokes.new()
stroke.display_mode = '3DSPACE'            # 必须设置！
stroke.material_index = 0
stroke.line_width = 10

# 点
stroke.points.add(count=3)
stroke.points[0].co = (0.0, 0.0, 0.0)    # float tuple
stroke.points[0].pressure = 1.0
```

### GP 材质

```python
mat = bpy.data.materials.new("my_mat")
bpy.data.materials.create_gpencil_data(mat)
mat.grease_pencil.color      = (0.0, 0.0, 0.0, 1.0)   # 描边色
mat.grease_pencil.fill_color = (1.0, 0.0, 0.0, 1.0)   # 填充色
mat.grease_pencil.show_fill  = True

gp_obj.data.materials.append(mat)
```

### 坐标系

Blender 右手坐标系：X 右、Y 前（屏幕内）、Z 上。
Grease Pencil 2D 动画通常在 XZ 平面作画（Y=0），摄像机从 -Y 方向看。

### 关键帧动画

```python
layer.opacity = 1.0
layer.keyframe_insert(data_path="opacity", frame=1)

layer.opacity = 0.0
layer.keyframe_insert(data_path="opacity", frame=60)
```

---

## 四、MCP Server 开发注意事项

### Tool 描述很重要

AI 完全依赖 `@mcp.tool()` 的 docstring 决定如何调用。

```python
# 好
async def create_gp_layer(object_name: str, layer_name: str = "Layer") -> str:
    """
    在指定的 Grease Pencil 对象上创建新图层。

    Returns the actual layer name created (may differ if name already exists).
    """

# 差
async def create_gp_layer(object_name: str, layer_name: str) -> str:
    """创建图层"""
```

### 错误信息必须对 AI 友好

```python
# 好
{
    "status": "error",
    "message": "GP object 'canvas' not found.",
    "hint": "Call create_gp_object first, or use one of: ['gp_obj1']"
}

# 差
{"error": "KeyError: 'canvas'"}
```

---

## 五、常见问题

### GP 对象创建了但看不见

`stroke.display_mode` 没有设置为 `'3DSPACE'`。

### Blender crash 而不是报错

在非主线程调用了 bpy。所有 bpy 调用必须在 `bpy.app.timers` 回调里。

### MCP Server 调用超时

1. 检查 Blender Addon 是否已启用（TCP Server 是否在监听）
2. 用手动 TCP 脚本绕过 Claude 直接测试 Addon
3. 检查 Blender 主线程是否卡在长时间操作（如渲染）

### GP 颜色显示偏差

Blender 内部使用线性颜色空间，输入值会被当作 linear 处理。
纯黑 `(0,0,0,1)` 和纯白 `(1,1,1,1)` 不受影响，中间色会有偏差。

---

## 六、上游代码结构与更新方法

`src/mcp/blmcp/` 的内容来自**三个独立来源**，更新时需要分别处理。

### 来源说明

```
src/mcp/blmcp/
├── __init__.py        ┐
├── tools/             ├─ 来源①：blender-mcp 仓库自身代码
├── tools_helpers/     ┘
└── data/
    ├── api/           ── 来源②：Blender Python API 文档构建产物（RST）
    └── manual/        ── 来源③：Blender 用户手册仓库（RST）
```

`data/` 下的文件不是 blender-mcp 仓库的代码，是用仓库里的辅助脚本从外部同步进来的。

### 更新来源①：核心代码

```bash
git clone https://projects.blender.org/blender/blender-mcp.git upstream

# 覆盖核心代码（保留 src/mcp/blmcp/data/ 不动）
cp -r upstream/mcp/blmcp/__init__.py      src/mcp/blmcp/
cp -r upstream/mcp/blmcp/tools/           src/mcp/blmcp/
cp -r upstream/mcp/blmcp/tools_helpers/   src/mcp/blmcp/

# 修复 import 路径（upstream 按自己结构写，迁移后会错位）
# 将所有 `src.mcp.blmcp` 替换为 `blmcp`
```

### 更新来源②：API 文档

需要本地 Blender 源码并构建 Python API 文档：

```bash
# 在 Blender 源码目录构建 API 文档
make docs_py
# 构建产物默认在 doc/python_api/

# 用同步脚本复制到项目
python src/_misc/update_reference_api.py /path/to/blender/doc/python_api/
```

### 更新来源③：用户手册

```bash
git clone https://projects.blender.org/blender/blender-manual.git

python src/_misc/update_reference_manual.py /path/to/blender-manual/
```

### 恢复同步脚本

如果 `src/_misc/` 下的脚本丢失，可从 git 历史找回：

```bash
git show 6294711:references/blender_mcp/_misc/update_reference_api.py \
  > src/_misc/update_reference_api.py

git show 6294711:references/blender_mcp/_misc/update_reference_manual.py \
  > src/_misc/update_reference_manual.py
```

---

## 七、版本兼容性

| 组件 | 版本 | 备注 |
|------|------|------|
| Blender | 4.0+ | 当前基准版本 |
| Python（Blender 内置） | 3.11 | Addon 用此版本，无法更改 |
| Python（MCP Server） | 3.10+ | blmcp 要求 |
| blmcp | 1.0.0 | 官方参考实现 |
| uv | 最新 | 包管理器 |

> ⚠️ Blender 4.2+ 起 Grease Pencil 升级为 GPv3，API 有较大改动。
> 升级 Blender 版本时，来源①②③均需同步更新，仅更新核心代码不够。

---

## 八、参考链接

| 资源 | 地址 |
|------|------|
| Blender Python API 文档 | https://docs.blender.org/api/current/ |
| bpy PyPI 包 | https://pypi.org/project/bpy/ |
| Blender MCP Server 页面 | https://www.blender.org/lab/mcp-server/ |
| blender-mcp 源码仓库 | https://projects.blender.org/blender/blender-mcp |
| Blender 用户手册仓库 | https://projects.blender.org/blender/blender-manual |
| Blender 源码仓库 | https://projects.blender.org/blender/blender |