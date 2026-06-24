# 可测试性与封装规范

参考来源：Google Python Style Guide、pytest 官方文档、attrs/Pydantic 社区指南。

---

## 1. 纯函数与副作用隔离

业务逻辑必须是纯函数（输出只依赖输入，无隐式 I/O）；副作用隔离在边界层。

```python
# 正确：业务逻辑纯函数，I/O 在调用方
def build_scene_state(raw_objects: list[dict]) -> list[SceneObject]:
    return [SceneObject.model_validate(o) for o in raw_objects]

# 禁止：业务逻辑内部直接发起网络请求
async def get_objects() -> list[SceneObject]:
    client = BlenderClient()          # 副作用藏在业务里
    response = await client.send(...) # 无法在不连接 Blender 的情况下测试
```

---

## 2. 依赖注入（Dependency Injection）

依赖通过参数传入，不在函数内部实例化。  
来源：Google Style Guide §2.5；pytest fixture 核心设计原则。

```python
# 正确：依赖作为参数，测试时可传入 mock
async def create(
    client: BlenderClient,
    name: str = "Scene",
    fps: int = 24,
) -> SceneCreateResult:
    ...

# 禁止：内部实例化，测试无法替换
async def create(name: str = "Scene", fps: int = 24) -> SceneCreateResult:
    client = BlenderClient()  # 测试必须有真实 Blender 连接
    ...
```

---

## 3. 组合大于继承

用协议（`Protocol`）描述接口，用组合拼装行为；不用多层继承。  
来源：Google Style Guide；attrs/Pydantic 社区。

```python
# 正确：Protocol 描述接口，组合实现
from typing import Protocol

class BlenderTransport(Protocol):
    async def send(self, command: BlenderCommand) -> BlenderResponse: ...

class BlenderClient:
    def __init__(self, transport: BlenderTransport) -> None:
        self._transport = transport

# 禁止：继承链传递行为
class MockClient(BlenderClient):  # 继承具体类，测试与实现耦合
    ...
```

---

## 4. 模块级函数优于嵌套函数

嵌套函数无法被单元测试直接调用。提取为带 `_` 前缀的模块级函数。  
来源：Google Style Guide §2.6。

```python
# 正确：可测试
def _build_delta(deleted: list[str]) -> SceneStateDelta:
    return SceneStateDelta(removed=deleted)

async def clear(client: BlenderClient) -> SceneClearResult:
    response = await client.send(...)
    return SceneClearResult(
        success=True,
        scene_state_delta=_build_delta(response.deleted_objects),
    )

# 禁止：逻辑藏在嵌套函数里
async def clear(client: BlenderClient) -> SceneClearResult:
    def build_delta(deleted):   # 无法单独测试
        return SceneStateDelta(removed=deleted)
    ...
```

---

## 5. 全局状态

不可避免的全局单例必须：使用 `_` 前缀、提供 `reset()` 函数、不在模块顶层执行副作用。  
来源：Google Style Guide §2.5、§3.17。

```python
# 正确：可重置的单例
_state = SceneState()

def get_state() -> SceneState:
    return _state

def reset() -> None:       # 测试用，每个 test 前调用
    global _state
    _state = SceneState()

# 禁止：导入时执行副作用
client = BlenderClient()   # 模块导入就建立连接，测试无法控制
client.connect()
```

---

## 6. 导入时无副作用

模块顶层只允许：常量定义、类型定义、函数/类声明。  
来源：Google Style Guide §3.17。

```python
# 禁止
_server = TCPServer()     # 导入即启动
_server.start()

# 正确：延迟到显式调用
def start() -> None:
    _server = TCPServer()
    _server.start()
```

---

## 7. pytest 测试结构

- 每个 fixture 只做一件事，用 `yield` 配对清理
- 默认 `function` 作用域，不跨测试共享状态
- 需要多实例时用 factory fixture

```python
import pytest

@pytest.fixture
def scene_state():
    reset()         # 确保干净起点
    yield get_state()
    reset()         # 测试后清理

@pytest.fixture
def mock_client():
    class FakeClient:
        async def send(self, cmd: BlenderCommand) -> BlenderResponse:
            return BlenderResponse(success=True, result={"name": "Scene", "fps": 24})
    return FakeClient()

async def test_create_scene(mock_client):
    result = await create(client=mock_client, name="TestScene", fps=30)
    assert result.success
    assert result.name == "TestScene"
```
