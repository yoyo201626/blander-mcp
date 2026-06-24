# AI 动画工厂 — 需求文档

> 依据：对官方参考实现 `references/blender_mcp` 的分析，结合本项目「AI 动画工厂」目标推导而来。

---

## 一、项目目标

用自然语言驱动 Blender，**批量、程序化、自动化**地生产节点动画与帧动画内容。美术资源可购买导入，AI 负责组织、驱动和渲染。

核心区分点：本项目是**生产流水线**，不是交互式辅助工具。

---

## 二、参考实现评估（官方 blmcp）

### 2.1 官方实现提供了什么

| 能力 | 工具 | 评价 |
|------|------|------|
| 在 Blender 中执行任意 Python 代码 | `execute_blender_code` | 万能逃生舱，但不稳定 |
| 后台模式执行（无 GUI） | `execute_blender_code_for_cli` | 批处理基础 |
| 场景对象摘要 | `get_objects_summary` `get_object_detail_summary` | 有限的场景感知 |
| .blend 文件信息 | `get_blendfile_summary_*` | 文件级检查 |
| 渲染输出 | `render_viewport_to_path` `render_thumbnail_to_path` | 仅视口渲染 |
| 视觉反馈 | `get_screenshot_of_window/area` | 调试用，非生产用 |
| 文档搜索 | `search_api_docs` `search_manual_docs` | LLM 自我查文档 |
| UI 导航 | `jump_to_*` | 交互式辅助 |

### 2.2 官方实现的本质局限

官方 blmcp 的设计假设是：**LLM 自己写 bpy 代码，通过 `execute_blender_code` 执行**。

这在交互式、探索性场景下够用，但对生产流水线有以下根本性问题：

1. **LLM 生成 bpy 代码的成功率不稳定**：节点 socket 连接依赖精确名称，关键帧 API 有多种调用模式，错一个参数静默失败
2. **无结构化状态**：每次 execute 是孤立的，LLM 无法感知上次操作产生的副作用（名称冲突 `.001`、材质残留等）
3. **无节点领域抽象**：Geometry Nodes 图的创建代码冗长且易错，没有封装
4. **无资产管道**：没有导入 FBX/GLTF/Blend Library 的专用工具
5. **无批量渲染管线**：没有帧范围、输出路径、渲染设置的结构化控制
6. **单连接，无并发**：一次只能连一个 Blender 实例

---

## 三、需求列表

以下需求均来自官方实现的缺口，并与 `master.md` 里程碑对应。

---

### REQ-01：结构化节点图工具

**来源**：官方无节点专用工具，全靠 LLM 手写 bpy 节点代码  
**对应里程碑**：M3（程序动画）

**需求描述**

MCP Server 必须提供以下节点图操作工具，而非让 AI 生成原始 bpy 代码：

| 工具 | 说明 |
|------|------|
| `node.graph_get` | 返回指定对象的节点树结构（节点名、类型、参数、连接关系） |
| `node.graph_apply_preset` | 按预制名称（如 `wave_deform`、`noise_displacement`）一键应用预制节点图 |
| `node.set_value` | 修改节点树中指定节点的指定输入值 |
| `node.animate_value` | 给节点输入值插入关键帧，实现节点参数动画 |

**节点预制库（内置）**

| 预制名 | 效果 |
|--------|------|
| `wave_deform` | 正弦波形变形，参数：振幅、频率 |
| `noise_displacement` | 噪声置换，参数：强度、尺度 |
| `instance_on_points` | 在点上实例化，参数：目标对象 |

**验收标准**：AI 调用 `node.graph_apply_preset` 后，Blender 内出现正确的节点图，不需要 AI 生成任何 bpy 代码。

---

### REQ-02：结构化动画数据工具

**来源**：官方无关键帧/F-Curve/驱动器的专用工具  
**对应里程碑**：M2（关键帧动画）、M3（程序动画）

**需求描述**

| 工具 | 说明 |
|------|------|
| `animation.keyframe_set` | 在指定帧为指定属性（位置/旋转/缩放）设置关键帧 |
| `animation.fcurve_get` | 读取对象的 F-Curve 数据，返回插值类型和所有关键帧 |
| `animation.driver_set` | 为属性绑定 Driver 表达式（如 `sin(frame * 0.1)`） |
| `animation.action_apply` | 将预制 Action 应用到对象（M4 角色动画） |

**返回格式要求**

`animation.keyframe_set` 必须返回实际写入的帧号和属性路径，供 AI 验证：

```json
{
  "success": true,
  "result": {
    "object": "Cube",
    "data_path": "location",
    "frames_written": [1, 30, 60]
  }
}
```

**验收标准**：AI 能通过 `animation.fcurve_get` 读取刚设置的关键帧，确认写入正确。

---

### REQ-03：资产导入管道

**来源**：官方无资产导入工具；本项目美术资源需购买导入  
**对应里程碑**：M4（角色动画）

**需求描述**

| 工具 | 说明 |
|------|------|
| `asset.import_file` | 导入外部文件（支持 `.fbx` / `.gltf` / `.glb` / `.obj`），返回导入的对象名列表 |
| `asset.link_blend` | 从另一个 `.blend` 文件 Library Link 资产（角色、材质、Action） |
| `asset.assign_material` | 将材质赋给对象的指定面 |

**导入后状态同步**

导入成功后，MCP Server 侧的 Scene State 必须立即同步导入的对象，包括：
- 对象名称（处理 Blender 自动追加的 `.001` 后缀）
- 对象类型（MESH / ARMATURE）
- 绑定的材质槽

**验收标准**：调用 `asset.import_file` 后，AI 能通过 Scene State 感知到新对象，不需要额外查询。

---

### REQ-04：批量渲染管线

**来源**：官方仅有视口渲染工具，无批量/参数化渲染支持  
**对应里程碑**：M1（MVP 渲染）～M5（AI Pipeline）

**需求描述**

| 工具 | 说明 |
|------|------|
| `render.setup` | 设置渲染参数：引擎（EEVEE/Cycles）、分辨率、帧率、输出路径、帧范围 |
| `render.frame` | 渲染单帧并返回输出文件路径 |
| `render.video` | 渲染帧序列并调用 ffmpeg 合成为 mp4 |
| `render.status` | 查询当前渲染任务的进度（已完成帧数/总帧数） |

**帧率和分辨率预设**

内置常用预设，减少 AI 参数错误：

| 预设名 | 分辨率 | 帧率 |
|--------|--------|------|
| `hd_24` | 1920×1080 | 24 |
| `hd_30` | 1920×1080 | 30 |
| `square_24` | 1080×1080 | 24 |

**验收标准**：AI 调用 `render.video` 后，输出目录有完整的 mp4 文件，无需人工介入。

---

### REQ-05：可靠的场景状态管理

**来源**：官方每次 execute 孤立，无跨调用状态  
**对应里程碑**：M0（基础建设）起贯穿全程

**需求描述**

MCP Server 侧维护 `SceneState`，追踪：

```
SceneState
├── objects: dict[name → SceneObject]
│   ├── name: str           # Blender 实际名称（含 .001 后缀）
│   ├── type: str           # MESH / GPENCIL / ARMATURE / CAMERA
│   ├── location: [x,y,z]
│   └── materials: list[str]
├── node_graphs: dict[name → NodeGraphSummary]
├── actions: dict[name → ActionSummary]
├── frame_start: int
├── frame_end: int
└── fps: int
```

**同步规则**

- 每次工具调用成功后，立即更新 SceneState
- 每次工具调用的返回值必须包含 `scene_state_delta`（增删改摘要）
- 提供 `scene.sync` 工具：从 Blender 实际状态重建 SceneState（用于恢复意外不一致）

**错误信息必须携带当前状态**

AI 调用不存在的对象时，错误信息必须附上当前可用对象列表：

```json
{
  "success": false,
  "error": {
    "code": "OBJECT_NOT_FOUND",
    "message": "对象 'robot' 不存在",
    "hint": "调用 asset.import_file 先导入，或从现有对象中选择",
    "available_objects": ["Camera", "Light", "Cube"]
  }
}
```

**验收标准**：AI 在一个多步任务中，可以通过 Scene State 感知到前几步操作的结果，无需每次重新查询 Blender。

---

### REQ-06：execute_blender_code 保留但受约束

**来源**：官方的 `execute_blender_code` 作为万能逃生舱  
**对应里程碑**：全程

**需求描述**

保留 `execute_blender_code` 工具，但在 MCP Server 层加以约束：

1. **仅作为兜底**：System Prompt 中明确该工具是最后手段，优先使用领域工具
2. **执行后强制同步**：执行后自动触发 `scene.sync`，防止状态漂移
3. **返回结构化错误**：捕获 bpy 异常，返回标准错误格式而非裸 Python traceback

**验收标准**：AI 不在有对应领域工具的情况下主动调用 `execute_blender_code`。

---

## 四、非功能需求

### NFR-01：工具调用成功率

同一个任务（如"创建波浪变形动画"），在 10 次 AI 调用中至少 9 次成功（不依赖人工重试）。

评估方式：用 DSL 示例文件 `dsl/examples/` 中的场景定期回归测试。

### NFR-02：错误自愈

AI 调用工具失败时，错误信息中的 `hint` 字段足够引导 AI 在下一次调用中自我纠正，不需要人工介入。

### NFR-03：单 Blender 实例（当前范围）

当前只支持连接一个本地 Blender 实例（`localhost:7890`）。多实例并发属于 M5 之后的扩展，不在当前需求范围内。

---

## 五、需求与里程碑映射

| 需求 | M0 | M1 | M2 | M3 | M4 | M5 |
|------|----|----|----|----|----|----|
| REQ-01 节点图工具 | | | | ✓ | | |
| REQ-02 动画数据工具 | | | ✓ | ✓ | ✓ | |
| REQ-03 资产导入管道 | | | | | ✓ | |
| REQ-04 批量渲染管线 | | ✓ | ✓ | ✓ | ✓ | ✓ |
| REQ-05 场景状态管理 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| REQ-06 execute 兜底 | ✓ | | | | | |

---

## 六、官方实现可直接复用的部分

以下内容可从 `references/blender_mcp` 直接参考或复用，无需重新设计：

| 部分 | 复用方式 |
|------|------|
| TCP socket 通信协议（null byte 分隔） | 参考 `tools_helpers/connection.py`，我们用 `\n` 分隔，原理相同 |
| `bpy.app.timers` 主线程调度模式 | 完全一致，见 `reference.md` 和 `dev-step.md` |
| FastMCP 工具自动注册模式 | 参考 `__init__.py` 的 `pkgutil.iter_modules` 扫描方式 |
| RST 文档内嵌搜索 | 如需 LLM 自查文档，可直接复用 `tools_helpers/rst_doc_search.py` |
| 错误格式设计理念 | 参考 `data/prompts.yml` 中的 System Prompt 约定 |
