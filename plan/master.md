# Blender Animation MCP — 大计划

> 面向：全部手动开发 / Blender 新手 / MVP 目标：Grease Pencil 矢量动画

---

## 一、整体路线图

```
M0（基础建设）
  └─ 环境搭建、进程通信打通、Hello World 验证
        ↓
M1（MVP：矢量动画）         ← 首要目标
  └─ Grease Pencil 工具链完整跑通
     能用自然语言画线、上色、做帧动画
        ↓
M2（扩展：关键帧动画）
  └─ 3D 对象移动 / 旋转 / 缩放
     Scene State 完整化
        ↓
M3（扩展：程序动画）
  └─ Driver / Modifier 驱动
     bounce / wave / noise
        ↓
M4（扩展：角色动画）
  └─ 预制角色 + Armature + 预制 Action
        ↓
M5（AI Pipeline）
  └─ 自然语言 → 多步工具链 → 自动渲染
```

---

## 二、各里程碑目标与交付物

### M0 — 基础建设（预计 1~2 周）

**目标**：进程通信跑通，Claude 能发一条指令让 Blender 做出响应

| 交付物 | 说明 |
|--------|------|
| Blender Addon 骨架 | 能安装、能启用、TCP Server 启动 |
| MCP Server 骨架 | 注册一个 `ping` 工具，Claude 可调用 |
| 通信验证脚本 | 证明 MCP → Blender 指令链路通 |
| 错误反馈机制 | 每次调用返回结构化成功/失败信息 |

**验收标准**：
```
在 Claude 中输入 → MCP Tool 调用 → Blender 收到指令 → Blender 返回 OK
```

---

### M1 — MVP：Grease Pencil 矢量动画（预计 3~4 周）

**目标**：用自然语言创建和动画化 2D 矢量图形

| 功能 | Tool | 说明 |
|------|------|------|
| 创建画布 | `vector.init_canvas` | 创建 Grease Pencil 对象 + 图层 |
| 画笔触 | `vector.draw_stroke` | 在指定帧画一条笔触 |
| 设置颜色 | `vector.set_material` | 笔触颜色 / 填充色 |
| 删除笔触 | `vector.clear_frame` | 清空某帧内容 |
| 逐帧动画 | `vector.animate_stroke` | 多帧笔触变化 |
| 图层不透明度 | `vector.set_layer_opacity` | 淡入淡出 |
| 渲染 | `render.image` / `render.video` | 输出结果 |

**验收标准**：
```
输入"画一个从小变大的圆圈，持续 2 秒" → 生成动画视频
```

---

### M2 — 关键帧动画（预计 2~3 周）

**目标**：3D 对象的完整关键帧控制

新增 Tool：
- `animation.move` `animation.rotate` `animation.scale`
- `scene.create_object`（立方体、球体、平面）
- `camera.animate`

Scene State 在此阶段完整化，追踪所有场景对象。

---

### M3 — 程序动画（预计 2~3 周）

**目标**：用数学公式驱动动画（无需手动设关键帧）

新增 Tool：
- `motion.bounce`（Driver：Z = height × |sin(t)|）
- `motion.wave`（Geometry Nodes wave 预制图）
- `motion.noise`（随机抖动）
- `motion.follow_path`（沿曲线运动）

---

### M4 — 角色动画（预计 3~4 周）

**目标**：预制人形角色 + 骨骼动画

- 内置几个预制角色（`.blend` 文件）
- 预制 Action 库（walk / idle / jump）
- IK 目标关键帧控制

---

### M5 — AI Pipeline（持续迭代）

**目标**：自然语言端到端

- LLM 规划多步工具链
- 错误自动重试
- 一句话 → 完整渲染视频

---

## 三、系统分层职责

```
┌─────────────────────────────────────────────┐
│              Claude / AI Agent               │
│  理解自然语言，规划工具调用序列              │
└──────────────────┬──────────────────────────┘
                   │ MCP Protocol (stdio)
┌──────────────────▼──────────────────────────┐
│              MCP Server                      │
│  • 注册和暴露所有 Tool                       │
│  • 参数校验（Pydantic）                      │
│  • 维护 Scene State                          │
│  • 通过 TCP 与 Blender 通信                  │
└──────────────────┬──────────────────────────┘
                   │ JSON-RPC over TCP (localhost:7890)
┌──────────────────▼──────────────────────────┐
│              Blender Addon                   │
│  • TCP Server 接收指令                       │
│  • bpy.app.timers 主线程调度                 │
│  • Handler 执行实际 bpy 操作                 │
│  • 返回执行结果 + 错误信息                   │
└──────────────────┬──────────────────────────┘
                   │ bpy Python API
┌──────────────────▼──────────────────────────┐
│              Blender Engine                  │
│  渲染 / 动画 / Grease Pencil / 导出          │
└─────────────────────────────────────────────┘
```

---

## 四、关键技术决策

### 决策 1：MCP 传输方式用 stdio

不自建 HTTP Server。直接用 `mcp` SDK 的 stdio 模式：

- Claude Desktop 配置一行命令即可连接
- 无需端口管理
- 本地开发零网络依赖

### 决策 2：MCP Server ↔ Blender 用 TCP Socket

两个独立进程必须通过 IPC 通信。选 TCP 而不是文件/管道的原因：
- 双向通信（Blender 可主动推送状态）
- 超时控制简单
- 未来可支持远程 Blender

### 决策 3：Blender 侧必须用 bpy.app.timers

Blender 的 bpy API **只能在主线程调用**。TCP Server 运行在子线程，所以：

```
TCP 子线程收到指令
    → 放入命令队列（thread-safe queue）
    → bpy.app.timers 在主线程轮询队列
    → 执行 bpy 操作
    → 结果放回响应队列
    → TCP 子线程读取结果并返回
```

### 决策 4：Scene State 在 MCP Server 侧维护

不在 Blender 侧维护状态，原因：
- Blender 侧重启后状态丢失
- MCP Server 可快速查询，无需跨进程

每次工具调用成功后，MCP Server 更新本地状态，并将 `scene_state_delta` 附在返回值中给 AI 参考。

### 决策 5：M1 使用内置预制资产

Grease Pencil 对象程序化创建（无需外部资产），Phase 4 才引入 `.blend` 预制角色文件。

---

## 五、统一返回格式

所有工具调用返回：

```json
// 成功
{
  "success": true,
  "data": { ... },
  "scene_state_delta": {
    "added": ["gp_canvas"],
    "modified": [],
    "removed": []
  }
}

// 失败
{
  "success": false,
  "error": {
    "code": "OBJECT_NOT_FOUND",
    "message": "Grease Pencil object 'gp_canvas' not found.",
    "hint": "Call vector.init_canvas first.",
    "available_objects": ["Camera", "Light"]
  }
}
```

> 错误信息必须包含 `hint`，告诉 AI 下一步该怎么做。

---

## 六、MVP 以外不做的事

| 不做 | 原因 |
|------|------|
| Rigify 自动绑骨 | M4 才需要，且对 Blender 新手复杂度过高 |
| 外部资产库集成 | 超出当前范围 |
| 多 Blender 实例 | 先支持单实例 |
| 云端渲染 | 本地渲染足够 MVP 验证 |
| 实时预览推流 | 渲染输出文件即可 |

---

## 七、风险与应对

| 风险 | 可能性 | 应对 |
|------|--------|------|
| bpy 主线程限制导致死锁 | 高 | 严格用 timers + queue，M0 阶段就验证 |
| Grease Pencil API 在 4.x 有 breaking change | 中 | 锁定 Blender 4.1，文档记录 API 版本 |
| AI 调用工具序列错误 | 高 | 错误返回必须包含 hint，引导 AI 自我纠正 |
| Blender Addon 调试困难 | 中 | 所有 handler 写单元测试（mock bpy） |