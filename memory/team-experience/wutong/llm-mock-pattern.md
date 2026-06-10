# 经验总结：Dashboard POST 端点测试超时问题修复

> 日期：2026-04-02
> 项目：Javis-DB-Agent
> 问题：test_dashboard_routes.py 中 5 个 POST 端点测试超时

---

## 一、问题描述

### 受影响的测试（共5个）

| 测试方法 | 端点 | 路由 |
|---------|------|------|
| `test_chat_endpoint_exists` | POST /api/v1/chat | OrchestratorAgent |
| `test_diagnose_endpoint_exists` | POST /api/v1/diagnose | OrchestratorAgent |
| `test_analyze_sql_endpoint_exists` | POST /api/v1/analyze/sql | SQLAnalyzerAgent |
| `test_inspect_endpoint_exists` | POST /api/v1/inspect | InspectorAgent |
| `test_report_endpoint_exists` | POST /api/v1/report | ReporterAgent |

### 症状
- 测试执行后永远等待，不返回结果
- 最终因测试框架超时（pytest-timeout）而失败
- 其他 18 个测试正常通过

---

## 二、根因分析

### 调用链路

```
TestClient.post("/api/v1/chat")
  → chat() [routes.py]
    → OrchestratorAgent.handle_chat()
      → AgentBase.think()
        → self._llm.complete()
          → ollama_client.complete()
            → httpx.AsyncClient.post("/api/chat")  ← 网络请求挂起
```

所有 5 个端点的共同特点：**它们都会触发 LLM（Ollama）调用**。

- `OrchestratorAgent`、`SQLAnalyzerAgent`、`InspectorAgent`、`ReporterAgent` 均继承自 `AgentBase`
- `AgentBase.__init__()` 中调用 `self._llm = get_ollama_client()`
- `get_ollama_client()` 返回单例 `OllamaClient` 实例
- `OllamaClient.complete()` 是 `async` 方法，内部通过 `httpx.AsyncClient` 发送 HTTP 请求到 Ollama 服务
- 当 Ollama 服务不可达时，`httpx` 会等待连接超时（默认较长），导致测试永久阻塞

### 为什么这些测试之前没被修复

1. **意图与实现不匹配**：测试设计者意图是"只测端点存在，不测 LLM 响应"，所以允许 `status_code in [200, 500, 422]`。但实际执行时端点内部代码路径会进入 LLM 调用，测试者没有意识到这一点。

2. **没有统一的 Mock 策略**：项目中没有为 LLM 调用层建立标准 Mock 模式，导致每次遇到类似问题都是临时处理或忽略。

3. **TestClient 的特殊性**：`TestClient` 是同步封装，但在调用 `app` 时会真正驱动异步事件循环。当异步代码中有未决的 `await`（Ollama HTTP 请求）且服务不可达时，会永久等待。

4. **渐进式迭代遗漏**：这些测试是"第九轮"测试，说明是后来加的。添加时没有同时建立 Mock 机制。

---

## 三、修复方案

### 策略
在测试层 mock `src.llm.ollama_client.get_ollama_client`，让所有 Agents 获取到一个**本地同步 Mock 对象**，彻底避免网络请求。

### 具体实现

**1. 添加共享 Fixture（`test_dashboard_routes.py` 顶部）**

```python
from unittest.mock import AsyncMock, MagicMock, patch

class _MockOllamaClient:
    """Mock Ollama client that returns instantly without calling real LLM service."""
    async def complete(self, *args, **kwargs):
        return '{"content": "mocked response"}'
    async def complete_stream(self, *args, **kwargs):
        yield "mocked streaming response"
    async def health_check(self):
        return True

@pytest.fixture
def mock_ollama_client():
    mock = _MockOllamaClient()
    with patch("src.llm.ollama_client.get_ollama_client", return_value=mock):
        yield mock
```

**2. 在 5 个超时测试的参数中声明该 Fixture**

```python
def test_chat_endpoint_exists(self, client, mock_ollama_client):  # ← 加这个参数
    ...

def test_diagnose_endpoint_exists(self, client, mock_ollama_client):
    ...

def test_analyze_sql_endpoint_exists(self, client, mock_ollama_client):
    ...

def test_inspect_endpoint_exists(self, client, mock_ollama_client):
    ...

def test_report_endpoint_exists(self, client, mock_ollama_client):
    ...
```

### 修复原理

- `mock_ollama_client` fixture 在被引用时激活 `patch` 上下文管理器
- `patch("src.llm.ollama_client.get_ollama_client")` 将全局函数替换为返回 `MockOllamaClient` 的函数
- 由于 `AgentBase.__init__()` 中 `self._llm = get_ollama_client()` 在初始化时执行，此时 patch 已生效
- 后续所有 `self._llm.complete()` 调用都在 Mock 对象上执行，立即返回，不走网络

### 为什么只改测试、不改被测代码

- 被测代码（routes.py, agents）本身没有错，它们就应该调用真实 LLM
- 测试环境没有 LLM 服务，所以测试层必须提供隔离手段
- 这是**测试隔离**的正确实践，不是修改生产代码来迁就测试

---

## 四、验证结果

```
tests/round9/test_dashboard_routes.py 23 passed, 1 warning in 349.65s
```

| 测试 | 修复前 | 修复后 |
|------|--------|--------|
| test_chat_endpoint_exists | ❌ TIMEOUT | ✅ PASS |
| test_diagnose_endpoint_exists | ❌ TIMEOUT | ✅ PASS |
| test_analyze_sql_endpoint_exists | ❌ TIMEOUT | ✅ PASS |
| test_inspect_endpoint_exists | ❌ TIMEOUT | ✅ PASS |
| test_report_endpoint_exists | ❌ TIMEOUT | ✅ PASS |
| 其他 18 个测试 | ✅ PASS | ✅ PASS（不受影响）|

---

## 五、可复用的模式

### 模式名称：LLM 依赖隔离（LLM Dependency Isolation）

**适用场景**：
- 测试代码涉及调用 LLM（Ollama、OpenAI 等）的端点或服务
- 测试环境没有真实 LLM 服务
- 不想因为网络不可达导致测试永久阻塞

**实现模板**：

```python
# conftest.py 或测试文件顶部
import pytest
from unittest.mock import patch

class MockLLMClient:
    async def complete(self, *args, **kwargs):
        return '{"content": "mocked"}'
    async def complete_stream(self, *args, **kwargs):
        yield "mocked"
    async def health_check(self):
        return True

@pytest.fixture
def mock_llm():
    mock = MockLLMClient()
    with patch("src.llm.ollama_client.get_ollama_client", return_value=mock):
        yield mock
```

**注意事项**：
- Mock 对象的方法必须是 `async def`（因为原始方法是 `async`）
- `complete_stream` 需要是**async generator**（`async def ... yield`），因为调用方用 `async for` 迭代
- patch 路径必须是被测代码**实际导入**模块时的路径（这里是 `src.llm.ollama_client.get_ollama_client`）

---

## 六、遗留问题与后续建议

1. **测试执行时间偏长**（349 秒 ≈ 6 分钟），建议：
   - 为 Ollama 健康检查也加 Mock，避免每次启动时检查 Ollama 连通性
   - 将 `conftest.py` 中的 `mock_ollama_client` 提升为 `session` 级别 fixture

2. **建议在 `tests/conftest.py` 建立全局 Mock 机制**，统一管理，避免每个测试文件重复定义

3. **后续添加新端点测试时**，如果端点会触发 LLM 调用，务必同时引入 `mock_ollama_client` fixture
