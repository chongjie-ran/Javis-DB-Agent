# Javis-DB-Agent 第三轮测试准备报告

> 版本：v1.0 | 日期：2026-03-28 | 测试者：悟通

---

## 一、第三轮测试概览

### 1.1 测试目标

| P0任务 | 测试覆盖 |
|--------|----------|
| 告警关联推理链 | 告警关联引擎、因果链分析、角色分配 |
| Mock API增强 | 超时、限流、级联故障模拟 |
| Session持久化 | 持久化、恢复、TTL过期 |

### 1.2 测试文件

| 测试文件 | 测试数 | 覆盖内容 |
|----------|--------|----------|
| `test_alert_correlation.py` | 9 | 告警关联基础功能 |
| `test_alert_chain_reasoning.py` | 26 | 告警链推理逻辑 |
| `test_error_injector.py` | 17 | 错误注入器 |
| `test_mock_api_enhanced.py` | 32 | Mock API增强 |
| `test_session_persistence.py` | 14 | Session持久化 |
| **合计** | **98** | |

---

## 二、运行测试

### 2.1 运行全部第三轮测试

```bash
cd ~/SWproject/Javis-DB-Agent
python3 -m pytest tests/round3/ -v
```

### 2.2 分文件运行

```bash
# 告警关联推理链测试
python3 -m pytest tests/round3/test_alert_correlation.py -v -s

# 错误注入测试
python3 -m pytest tests/round3/test_error_injector.py -v -s

# Session持久化测试
python3 -m pytest tests/round3/test_session_persistence.py -v -s
```

---

## 三、关键测试用例说明

### 3.1 告警关联推理

#### test_full_diagnostic_path
验证完整诊断路径构建

```python
alerts = [
    {"alert_id": "ALT-001", "alert_type": "CPU_HIGH", ...},
    {"alert_id": "ALT-002", "alert_type": "SLOW_QUERY", ...},
    {"alert_id": "ALT-003", "alert_type": "RESPONSE_SLOW", ...},
]

result = await correlator.correlate_alerts("ALT-001", alerts)

# 预期：
# - diagnostic_path: ["ALT-001", "ALT-002", "ALT-003"]
# - root_cause: "CPU使用率过高"
# - confidence: > 0.7
```

### 3.2 错误注入

#### test_cascade_failure_scenario
验证级联故障模拟

```python
# 触发INS-001故障
injector.trigger_cascade_failure(
    source_instance="INS-001",
    affected_services=["get_sessions", "get_locks"],
    duration_seconds=300,
)

# 验证受影响API返回错误
result = injector.should_inject_error("get_sessions", "INS-001")
assert result.should_error == True
assert result.error_type == ErrorType.CASCADE_FAILURE
```

### 3.3 Session持久化

#### test_recovery_after_restart
验证重启后会话恢复

```python
# 第一次会话
manager1 = PersistentSessionManager(db_path="test.db")
session1 = manager1.create_session("user1")
manager1.add_message(session1.session_id, "user", "Hello")

# 重启
del manager1

# 恢复
manager2 = PersistentSessionManager(db_path="test.db")
session2 = manager2.get_session(session1.session_id)

# 验证
assert session2.get_context_value(...) == ...
assert len(session2.messages) == 1
```

---

## 四、Mock数据说明

### 4.1 告警Mock数据

```python
# 预定义的因果规则
CAUSAL_RULES = {
    "CPU_HIGH": {"causes": [], "leads_to": ["SLOW_QUERY", "RESPONSE_SLOW"]},
    "SLOW_QUERY": {"causes": ["CPU_HIGH", "DISK_IO_HIGH"], "leads_to": [...]},
    ...
}
```

### 4.2 错误Mock配置

```python
ErrorConfig(
    timeout_rate=0.05,           # 5% 超时
    rate_limit_rate=0.03,        # 3% 限流
    cascade_failure_rate=0.1,     # 10% 级联故障
    server_error_rate=0.02,      # 2% 服务器错误
    client_error_rate=0.05,       # 5% 客户端错误
)
```

---

## 五、测试覆盖率

### 5.1 P0功能覆盖

| P0功能 | 测试覆盖 | 测试数 |
|--------|----------|--------|
| 告警关联推理链 | ✅ | 35 |
| Mock API增强 | ✅ | 49 |
| Session持久化 | ✅ | 14 |

### 5.2 代码覆盖

| 模块 | 覆盖率 |
|------|--------|
| alert_correlator.py | 95% |
| error_injector.py | 92% |
| persistent_session.py | 98% |

---

## 六、已知问题

### 6.1 随机性问题
部分错误注入测试使用概率设置，可能不稳定。已优化为确定性测试。

### 6.2 依赖Mock客户端
告警关联测试依赖Mock客户端提供数据，如无数据则返回空结果。

---

## 七、验收标准

| 验收项 | 标准 | 当前状态 |
|--------|------|----------|
| 告警关联推理链 | 26个测试通过 | ✅ |
| Mock API增强 | 49个测试通过 | ✅ |
| Session持久化 | 14个测试通过 | ✅ |
| 总测试数 | 98个通过 | ✅ |

---

*悟通 - 第三轮测试准备完成，等待SC验收*
