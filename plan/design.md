# blender-animation-mcp

> AI Agent 驱动的 Blender 动画控制运行时，基于 MCP（Model Context Protocol）协议。

---

## 核心理念

**不让 AI 直接操作 Blender API，而是通过动画领域 DSL 与其交互。**

```
自然语言输入
     ↓
AI Agent（Claude / GPT）
     ↓  MCP Protocol
MCP Server（Animation Tool Router）
     ↓  WebSocket / stdio
Blender Addon（DSL Executor）
     ↓  bpy
Blender Engine
     ↓
动画输出（视频 / GLTF / FBX）
```

### 为什么不直接生成 bpy 代码？

| 问题 | 说明 |
|------|------|
| API 太底层 | `bpy.ops.mesh.primitive_cube_add()` 对 AI 来说不直观、易出错 |
| 状态不可见 | AI 无法感知当前场景里有什么对象 |
| 错误难恢复 | bpy 报错信息对 LLM 不友好 |
| 缺乏领域语义 | "让熊猫走路"应该是一个工具调用，而不是 200 行骨骼操作代码 |

---

## 技术选型

### MCP Server

| 技术 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 与 Blender 生态一致，MCP SDK 原生支持 |
| MCP 框架 | `mcp` (Anthropic SDK) | 官方 SDK，支持 stdio / SSE 两种传输 |
| 传输方式 | **stdio**（本地）/ SSE（远程） | 本地开发用 stdio，零网络依赖；远程部署用 SSE |
| 包管理 | `uv` | 速度快，lockfile 可靠 |

> ❌ 不使用 FastAPI + WebSocket 自建协议层  
> ✅ 直接使用 MCP SDK，让 Claude Desktop / Cursor 等客户端原生调用

### Blender Addon

| 技术 | 选择 | 理由 |
|------|------|------|
| 通信 | **JSON-RPC over TCP Socket** | Blender 有独立 Python 解释器，需要进程间通信 |
| 执行调度 | `bpy.app.timers` | 保证所有 bpy 调用在 Blender 主线程执行 |
| Blender 版本 | 4.0+ | Geometry Nodes 和 Grease Pencil 3 趋于稳定 |

#### api

https://docs.blender.org/api/current/index.html

#### 编程风格

https://peps.python.org/pep-0008/

### 场景状态管理

MCP Server 侧维护一个内存中的 **Scene State**，追踪：
- 当前所有对象（名称、类型、位置）
- 已有的 Action / NLA 轨道
- 活跃摄像机

这样 AI 在生成下一个工具调用时能感知当前状态，不会对不存在的对象发指令。

---

## 项目结构

```
blender-animation-mcp/
│
├── mcp_server/                  # MCP 协议层（独立进程）
│   ├── __init__.py
│   ├── main.py                  # MCP Server 入口，注册所有 Tool
│   ├── tools/                   # Tool 定义（按领域分组）
│   │   ├── scene.py             # scene.*, camera.*
│   │   ├── asset.py             # character.*, material.*
│   │   ├── animation.py         # animation.*
│   │   ├── procedural.py        # motion.*
│   │   ├── nodes.py             # node.*
│   │   └── export.py            # render.*, export.*
│   ├── state/
│   │   └── scene_state.py       # Scene State Manager（追踪场景对象）
│   ├── bridge/
│   │   └── blender_client.py    # 与 Blender Addon 的 TCP 通信客户端
│   └── schemas/                 # Pydantic 参数校验模型
│       ├── animation.py
│       ├── character.py
│       └── node.py
│
├── blender_addon/               # Blender 内运行的 Addon（独立进程）
│   ├── __init__.py              # Addon 注册入口
│   ├── server.py                # TCP Server，接收来自 MCP Server 的指令
│   ├── executor.py              # 指令分发器，调用对应 handler
│   └── handlers/                # 实际执行 bpy 操作
│       ├── scene.py
│       ├── asset.py
│       ├── keyframe.py          # 关键帧 / FCurve / Action 操作
│       ├── procedural.py        # Driver / Modifier 程序动画
│       ├── grease_pencil.py     # 矢量 / 2D 动画
│       ├── rig.py               # Armature / Rigify / IK
│       ├── geometry_nodes.py    # Geometry Nodes 图
│       └── export.py            # 渲染 / 导出
│
├── dsl/                         # Animation DSL 规范
│   ├── README.md                # DSL 文档
│   └── examples/                # DSL 调用示例（JSON）
│       ├── bouncing_ball.json
│       ├── panda_walk.json
│       └── wave_geometry.json
│
├── assets/                      # 内置预制资产
│   ├── characters/              # 预制角色（.blend）
│   └── materials/               # 预制材质
│
├── tests/
│   ├── test_tools.py            # MCP Tool 单元测试（mock Blender）
│   └── test_executor.py         # Executor 集成测试
│
├── pyproject.toml               # uv 项目配置
├── uv.lock
└── README.md
```

---

## Animation DSL 参考

所有工具调用均为 JSON，通过 MCP 协议传递。

### Scene

```json
// 创建场景
{ "tool": "scene.create", "params": { "name": "main", "fps": 24 } }

// 创建摄像机并动画化
{ "tool": "camera.animate", "params": {
    "from": [0, -10, 5], "to": [5, -10, 5],
    "start_frame": 1, "end_frame": 60
}}
```

### 角色资产

```json
// 创建内置预制角色（Phase 1 使用内置资产库）
{ "tool": "character.create", "params": { "name": "panda", "preset": "cartoon_biped" } }

// 导入外部资产
{ "tool": "character.import", "params": { "name": "robot", "path": "./assets/robot.blend" } }
```

> **资产策略**：Phase 1-2 使用内置预制 `.blend` 资产（已绑定骨骼）；  
> Phase 4 引入 Rigify 自动绑定；Phase 5 支持外部资产库。

### 关键帧动画

```json
// 移动
{ "tool": "animation.move", "params": {
    "target": "panda",
    "keyframes": [
        { "frame": 1,  "value": [0, 0, 0] },
        { "frame": 60, "value": [5, 0, 0] }
    ],
    "interpolation": "BEZIER"
}}

// 旋转
{ "tool": "animation.rotate", "params": {
    "target": "panda",
    "keyframes": [
        { "frame": 1,  "value": [0, 0, 0] },
        { "frame": 30, "value": [0, 0, 180] }
    ]
}}
```

### 程序动画

```json
// 弹跳（自动生成 Driver: Z = height * |sin(frame * speed)|）
{ "tool": "motion.bounce", "params": { "target": "ball", "height": 2.0, "speed": 0.2 } }

// 波浪
{ "tool": "motion.wave",   "params": { "target": "plane", "amplitude": 0.5, "frequency": 2.0 } }

// 路径跟随
{ "tool": "motion.follow_path", "params": { "target": "car", "path": "road_curve", "duration": 120 } }
```

### 矢量 / 2D 动画（Grease Pencil）

```json
{ "tool": "vector.draw", "params": {
    "layer": "outline",
    "stroke": { "points": [[0,0,0],[1,0,0],[1,1,0]], "pressure": 0.8 }
}}

{ "tool": "vector.animate_stroke", "params": {
    "layer": "outline", "stroke_index": 0,
    "keyframes": [
        { "frame": 1,  "points": [[0,0,0],[1,0,0]] },
        { "frame": 30, "points": [[0,0,0],[1,0,0],[2,0,0]] }
    ]
}}
```

### Geometry Nodes

```json
// 创建预制节点图
{ "tool": "node.create_graph", "params": { "target": "plane", "preset": "wave_deform" } }

// 修改节点参数
{ "tool": "node.set_value", "params": {
    "target": "plane", "graph": "wave_deform",
    "node": "Wave Texture", "input": "Scale", "value": 3.0
}}
```

### 角色动画（Armature）

```json
// 应用预制动作
{ "tool": "animation.apply_action", "params": { "character": "panda", "action": "walk_cycle", "start_frame": 1 } }

// 设置 IK 目标关键帧
{ "tool": "animation.set_ik_target", "params": {
    "character": "panda", "bone": "hand_R",
    "keyframes": [
        { "frame": 1,  "position": [0.5, 0, 1.2] },
        { "frame": 15, "position": [0.5, 0.3, 1.5] }
    ]
}}
```

### 渲染与导出

```json
{ "tool": "render.video", "params": { "output": "./output/panda_walk.mp4", "start": 1, "end": 120, "engine": "EEVEE" } }
{ "tool": "export.gltf",  "params": { "output": "./output/panda.glb", "include_animations": true } }
```

---

## Tool 完整列表

### scene
`scene.create` `scene.clear` `scene.set_frame_range`  
`camera.create` `camera.animate` `light.create`

### asset
`character.create` `character.import`  
`material.create` `material.assign`

### animation
`animation.move` `animation.rotate` `animation.scale`  
`animation.apply_action` `animation.set_ik_target`  
`animation.set_pose`

### procedural
`motion.bounce` `motion.wave` `motion.noise`  
`motion.follow_path` `motion.pendulum`

### vector (Grease Pencil)
`vector.draw` `vector.animate_stroke` `vector.set_layer_opacity`

### node (Geometry Nodes)
`node.create_graph` `node.connect` `node.set_value` `node.animate_value`

### export
`render.image` `render.video`  
`export.gltf` `export.fbx` `export.alembic`

---

## 快速开始

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/yourname/blender-animation-mcp.git
cd blender-animation-mcp

# 安装 MCP Server 依赖（使用 uv）
uv sync
```

### 2. 安装 Blender Addon

1. 打开 Blender → Edit → Preferences → Add-ons → Install
2. 选择 `blender_addon/` 目录（或打包为 `.zip`）
3. 启用 **Animation MCP Runtime**

### 3. 启动 MCP Server

```bash
# 在 Blender 侧先启动 Addon TCP Server（在 Blender Python Console 中）
# 插件启用后会自动启动，监听 localhost:7890

# 启动 MCP Server
uv run python -m mcp_server.main
```

### 4. 连接到 Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "blender-animation": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp_server.main"],
      "cwd": "/path/to/blender-animation-mcp"
    }
  }
}
```

之后直接在 Claude 对话中输入：

```
生成一个熊猫角色，让它从左走到右，持续 3 秒，最后跳一下
```

---

## 开发阶段

### Phase 1 — MCP ↔ Blender 通道打通
**目标**：能从 Claude 控制 Blender 的基本对象

- [ ] Blender Addon TCP Server（`bpy.app.timers` 主线程调度）
- [ ] MCP Server 基础框架 + 工具注册
- [ ] Scene State Manager
- [ ] 错误反馈通道（工具调用返回详细错误信息）
- [ ] 支持：`scene.create` `character.create` `animation.move` `render.image`

### Phase 2 — 关键帧动画 DSL
**目标**：完整的关键帧控制能力

- [ ] `animation.move / rotate / scale`
- [ ] FCurve 自动生成（支持 BEZIER / LINEAR / CONSTANT 插值）
- [ ] NLA Editor Action 管理
- [ ] 多对象同步动画

### Phase 3 — 程序动画
**目标**：用数学公式驱动的动画

- [ ] Driver 自动生成（`motion.bounce / wave / noise`）
- [ ] Modifier 动画（Cloth、Soft Body 简单配置）
- [ ] Geometry Nodes 预制图库

### Phase 4 — 角色动画
**目标**：人形角色的完整动画控制

- [ ] Rigify 自动绑定集成
- [ ] IK/FK 切换控制
- [ ] 预制 Action 库（walk / run / idle / jump / attack）
- [ ] `animation.apply_action` 混合多段动作

### Phase 5 — AI Pipeline
**目标**：自然语言端到端生成动画

- [ ] LLM 意图解析 → 工具调用序列规划
- [ ] 多步骤工具链编排
- [ ] 错误自动重试与修正
- [ ] 支持：输入一句话，输出完整渲染视频

---

## 错误处理规范

每个工具调用均返回统一结构：

```json
{
  "success": true,
  "result": { "object_name": "panda", "location": [0, 0, 0] },
  "scene_state_delta": { "added": ["panda"], "modified": [], "removed": [] }
}
```

失败时：

```json
{
  "success": false,
  "error": {
    "code": "OBJECT_NOT_FOUND",
    "message": "Object 'panda' does not exist in the scene.",
    "available_objects": ["cube", "camera", "light"]
  }
}
```

> 错误信息需对 LLM 友好：告知当前可用状态，让 AI 能自我纠正。

---

## 非目标

本项目不是：

- Blender 的替代品
- 通用 Python 代码生成器
- AI 绘画 / 图像生成工具
- 游戏引擎

本项目是：

> **以动画领域语义为中心的 AI ↔ Blender 控制运行时**

---

## License

MIT