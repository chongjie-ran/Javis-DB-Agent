# zCloudNewAgentProject 第三轮架构 - 告警关联推理链

> 版本：v1.0 | 日期：2026-03-28 | 状态：规划中

---

## 1. 第三轮目标

### 1.1 P0任务
| 任务 | 描述 | 优先级 |
|------|------|--------|
| 告警关联推理链 | 实现A告警→B告警→C告警的链式诊断逻辑 | P0 |
| Mock zCloud API增强 | 模拟超时、限流、级联故障等真实场景 | P0 |
| Session持久化 | 支持重启后恢复对话上下文 | P0 |

---

## 2. 告警关联推理链设计

### 2.1 核心概念

**告警关联图（Alert Correlation Graph）**：
```
[ALT-001: CPU高] → [ALT-002: 慢SQL] → [ALT-003: 用户反馈卡顿]
      ↓                   ↓                    ↓
   可能关联            可能关联              可能关联
   
级联关系：
CPU高(因) → 慢SQL(果) → 用户卡顿(果)
```

### 2.2 关联类型

| 关联类型 | 描述 | 示例 |
|----------|------|------|
| 因果关联 | A导致B | CPU高→慢SQL |
| 时间关联 | A和B在时间上接近 | 同一分钟内多个告警 |
| 实例关联 | 同一实例的告警 | INS-001上的多个告警 |
| 症状关联 | A是B的症状 | 响应慢→CPU高 |

### 2.3 关联规则

```python
ALERT_CORRELATION_RULES = {
    # 因果关联规则
    "CPU_HIGH": {
        "causes": [],  # 什么导致这个告警
        "leads_to": ["SLOW_QUERY", "RESPONSE_SLOW", "SESSION_BLOCK"],  # 这个告警会导致什么
    },
    "SLOW_QUERY": {
        "causes": ["CPU_HIGH", "DISK_IO_HIGH", "LOCK_WAIT"],
        "leads_to": ["RESPONSE_SLOW", "USER_COMPLAIN"],
    },
    "LOCK_WAIT": {
        "causes": ["BIG_TRANSACTION", "MISSING_INDEX"],
        "leads_to": ["SESSION_BLOCK", "RESPONSE_SLOW"],
    },
    # 同一实例关联
    "same_instance": True,  # 同一实例的告警自动关联
    # 时间窗口关联（秒）
    "time_window": 300,  # 5分钟内告警关联
}
```

### 2.4 推理引擎架构

```
AlertCorrelationEngine
├── _build_correlation_graph()    # 构建告警关联图
├── _find_related_alerts()        # 查找关联告警
├── _analyze_causal_chain()       # 分析因果链
├── _score_correlation()           # 计算关联度
└── _generate_diagnostic_path()    # 生成诊断路径
```

### 2.5 输出格式

```json
{
  "primary_alert": "ALT-001",
  "correlation_chain": [
    {"alert_id": "ALT-001", "role": "root_cause", "confidence": 0.9},
    {"alert_id": "ALT-002", "role": "symptom", "confidence": 0.85},
    {"alert_id": "ALT-003", "role": "symptom", "confidence": 0.7}
  ],
  "diagnostic_path": ["ALT-001", "ALT-002", "ALT-003"],
  "root_cause": "CPU使用率过高导致查询变慢",
  "confidence": 0.88
}
```

---

## 3. Mock API增强设计

### 3.1 增强场景

| 场景 | 模拟方式 | 触发条件 |
|------|----------|----------|
| 超时 | 延迟响应 | 特定API+随机10%概率 |
| 限流 | 429状态码 | 请求频率超限 |
| 级联故障 | 多个相关API失败 | 实例故障时关联服务也失败 |
| 错误响应 | 4xx/5xx状态码 | 参数错误/服务端错误 |
| 数据不一致 | 返回矛盾数据 | 模拟数据同步延迟 |

### 3.2 错误注入机制

```python
class ErrorInjectionConfig:
    enabled: bool = True
    timeout_rate: float = 0.1      # 10% 超时概率
    rate_limit_rate: float = 0.05  # 5% 限流概率
    cascade_failure_rate: float = 0.2  # 20% 级联故障概率
    error_codes: list = [400, 401, 403, 404, 500, 502, 503]
```

### 3.3 级联故障模拟

```python
# 当实例INS-001故障时，关联服务也会受影响
CASCADE_RULES = {
    "INS-001": {
        "affects": ["INS-001-sessions", "INS-001-backup"],
        "delay_seconds": 5  # 延迟5秒后影响
    }
}
```

---

## 4. Session持久化设计

### 4.1 持久化方案

| 方案 | 优点 | 缺点 |
|------|------|------|
| SQLite | 简单、跨平台、支持SQL查询 | 需额外库 |
| JSON文件 | 简单、无依赖 | 并发差、查询弱 |
| 文件+JSON | 简单、人类可读 | 大会话性能差 |

**选择**：SQLite + JSON混合方案

### 4.2 数据模型

```sql
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    metadata TEXT,  -- JSON
    context TEXT   -- JSON
);

CREATE TABLE messages (
    message_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,  -- JSON
    timestamp REAL NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_updated ON sessions(updated_at);
```

### 4.3 持久化接口

```python
class PersistentSessionManager:
    def __init__(self, db_path: str = "data/sessions.db"):
        self.db_path = db_path
        self._ensure_db()
    
    async def create_session(self, user_id: str) -> Session
    async def get_session(self, session_id: str) -> Optional[Session]
    async def save_session(self, session: Session)
    async def delete_session(self, session_id: str) -> bool
    async def list_user_sessions(self, user_id: str) -> list[Session]
    async def add_message(self, session_id: str, message: Message)
    def _ensure_db()  # 确保数据库表存在
```

---

## 5. 目录结构调整

```
src/
├── agents/
│   ├── diagnostic.py       # [增强] 告警关联推理
│   └── orchestrator.py     # [增强] 链式诊断调用
├── gateway/
│   ├── session.py          # [重构] 持久化SessionManager
│   └── alert_correlator.py # [新增] 告警关联引擎
├── mock_api/
│   ├── zcloud_client.py    # [增强] 错误注入
│   ├── error_injector.py   # [新增] 错误注入器
│   └── cascade_simulator.py # [新增] 级联故障模拟
└── tools/
    └── query_tools.py      # [增强] 超时处理
```

---

## 6. 实施计划

| 阶段 | 任务 | 产出 |
|------|------|------|
| Phase 1 | 告警关联引擎 | alert_correlator.py |
| Phase 2 | 诊断Agent增强 | diagnostic.py (链式推理) |
| Phase 3 | Session持久化 | session.py (SQLite) |
| Phase 4 | Mock API增强 | error_injector.py + cascade_simulator.py |
| Phase 5 | 集成测试 | tests/round3/ |

---

*状态：规划中，待开始实现*
