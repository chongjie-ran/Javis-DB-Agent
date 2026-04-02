# Round30 测试报告：Javis-DB-Agent V2.6.1

**版本**: V2.6.1
**测试日期**: 2026-04-01 22:20 GMT+8
**测试者**: 真显（测试者）
**状态**: 测试用例设计完成，等待悟通修复 `approval.py` 语法错误

---

## ⚠️ 阻断问题

```
src/gateway/approval.py:517: SyntaxError: 'await' outside async function
```

悟通在开发 V2.6.1 过程中，`approval.py` 存在语法错误，导致所有测试无法导入。
修复此错误后，测试方可正常运行。

---

## 一、测试范围

| 功能 | 测试文件 | 测试用例数 |
|------|----------|-----------|
| F1: Token TTL 机制 | `test_token_ttl.py` | 30 |
| F2: Hook MODIFY 动作 | `test_hook_modify.py` | 26 |
| **总计** | | **56** |

---

## 二、F1: Token TTL 机制

### 2.1 TTL 过期检查（TTL-01 ~ TTL-10）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| TTL-01 | 会话在 TTL 后过期 | 3.5秒后 `get_session` 返回 `None` |
| TTL-02 | 会话在 TTL 内可访问 | 0.5秒后 `get_session` 正常返回 |
| TTL-03 | 缓存中的会话在 TTL 后过期 | 缓存自动清理 |
| TTL-04 | 数据库中的会话在 TTL 后过期（冷启动） | DB 查询后返回 `None` |
| TTL-05 | `_cleanup_expired` 清理缓存 | 缓存记录被删除 |
| TTL-06 | 多会话过期行为 | 过期后都不可访问 |
| TTL-07 | TTL 配置值正确 | 60秒 TTL 正常工作 |
| TTL-08 | `save_session` 更新 `updated_at` 延迟过期 | TTL 窗口顺延 |
| TTL-09 | 并发访问临界过期会话 | 线程安全，一致性保证 |
| TTL-10 | `list_user_sessions` 排除过期会话 | 只返回有效会话 |

### 2.2 params_hash 参数漂移检测（PHD-01 ~ PHD-07）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| PHD-01 | 新建会话 `metadata` 非空 | `session.metadata` 是 `dict` |
| PHD-02 | `set_context_value` 可设置并持久化 params_hash | 持久化到 DB 并正确恢复 |
| PHD-03 | 参数变化时 params_hash 不同 | 不同 SQL/instance 产生不同 hash |
| PHD-04 | params_hash 存储在 session context | 重启后仍可读取 |
| PHD-05 | params_hash 漂移时 `add_message` 仍正常 | 不因 hash 不同而失败 |
| PHD-06 | SHA256 hash 的一致性验证 | 相同输入→相同输出 |
| PHD-07 | `sort_keys=True` 确保字典顺序无关 | `{"a":1, "b":2}` 与 `{"b":2, "a":1}` 同 hash |

### 2.3 双重校验逻辑（DV-01 ~ DV-10）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| DV-01 | Cache Hit 时直接返回 | 命中缓存，直接返回 |
| DV-02 | Cache Miss 时查 DB，DB 有则回填 cache | DB 加载并回填 |
| DV-03 | Cache 和 DB 都 miss 返回 None | 正确处理不存在 |
| DV-04 | Cache 过期但 DB 有效时返回 None | TTL 过期机制 |
| DV-05 | DB 中会话过期时同步清理 cache | 一致性保证 |
| DV-06 | `save_session` 同时更新 DB 和 cache | 双写一致 |
| DV-07 | 并发读取双重校验一致性 | 5 线程并发安全 |
| DV-08 | `delete_session` 后 cache 和 DB 都清理 | 完整删除 |
| DV-09 | `_user_sessions` 索引与实际 sessions 一致 | 索引同步 |
| DV-10 | 超过 `max_sessions` 时 LRU 淘汰 | 最早会话被淘汰 |

---

## 三、F2: Hook MODIFY 动作

### 3.1 REPLACE 操作（REP-01 ~ REP-05）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| REP-01 | 替换简单字符串字段 | DDL SQL 替换为占位符 |
| REP-02 | 替换嵌套字段 | `params.risk_level` L5→L3 |
| REP-03 | 无匹配条件时不替换 | 不改变 payload |
| REP-04 | 多条 MODIFY 规则链式执行 | 按优先级顺序执行 |
| REP-05 | REPLACE 不影响其他字段 | 只改目标字段 |

### 3.2 REDACT 操作（RED-01 ~ RED-05）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| RED-01 | 密码字段脱敏 | `secret123` → `********` |
| RED-02 | 邮箱部分脱敏 | `john.doe@company.com` → `jo***@company.com` |
| RED-03 | 信用卡号脱敏 | `4111...1111` → `****-****-****-1111` |
| RED-04 | SQL 语句移除注释 | `-- comment` → `[COMMENT REDACTED]` |
| RED-05 | 无敏感数据时不脱敏 | 正常 SQL 不变 |

### 3.3 ADD / REMOVE / CLAMP 操作（ARC-01 ~ ARC-07）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| ARC-01 | ADD 添加新字段到 payload | `added_by_hook` 字段注入 |
| ARC-02 | ADD 增加数值字段 | `retry_count` +1 |
| ARC-03 | REMOVE 从 payload 删除字段 | `debug_flag` 字段被删除 |
| ARC-04 | REMOVE 只删除匹配条件的字段 | 其他字段保留 |
| ARC-05a | CLAMP 将超出上限的值限制在范围内 | `max_connections` 500→100 |
| ARC-05b | CLAMP 将低于下限的值限制在范围内 | `max_connections` 0→1 |
| ARC-06 | 值在范围内时 CLAMP 不修改 | 范围内值保持不变 |
| ARC-07 | CLAMP 限制超时值合理范围 | `timeout_ms` 600000→300000 |

### 3.4 MODIFY 与其他动作混合（MIX-01 ~ MIX-04）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| MIX-01 | MODIFY 规则优先级高于 BLOCK | 先修改后阻止 |
| MIX-02 | MODIFY 后跟 WARN | 修改完成→添加警告 |
| MIX-03 | MODIFY 和 LOG 组合 | 修改后记录日志 |
| MIX-04 | 同一 payload 多个 MODIFY 操作 | 链式执行，结果累积 |

### 3.5 Hook MODIFY 真实 SQL 场景（RLS-01 ~ RLS-04）

| 用例ID | 描述 | 预期行为 |
|--------|------|---------|
| RLS-01 | SQL 注入防护（REPLACE 清理危险字符） | `/* ... */` 和 `--` 注释被移除 |
| RLS-02 | DDL 白名单（REPLACE 高风险 DDL） | DROP→`[DDL REPLACED]` |
| RLS-03 | 只允许 SELECT（其他全部 REDACT） | DELETE→`[NON-SELECT REDACTED]` |
| RLS-04 | 超时限制真实场景 | 120s→60s，不误改 SQL |

---

## 四、运行方式

```bash
cd ~/SWproject/Javis-DB-Agent

# 1. 先确保 approval.py 语法错误已修复

# 运行全部 Round30 测试
python3 -m pytest tests/round30/ -v --tb=short

# 仅运行 TTL 测试
python3 -m pytest tests/round30/test_token_ttl.py -v --tb=short

# 仅运行 Hook MODIFY 测试
python3 -m pytest tests/round30/test_hook_modify.py -v --tb=short
```

---

## 五、已知环境问题

| 问题 | 影响 | 解决方案 |
|------|------|---------|
| `approval.py:517` 语法错误 | 所有测试无法导入 | 悟通修复该文件 |
| TTL 计时依赖 `time.sleep` | 在慢环境可能不稳定 | 依赖 `time.time()` 机制，实际应可靠 |
| `params_hash` 存于 `context` 而非 `metadata` | PHD-04 测试设计需对齐 | 确认 V2.6.1 设计意图 |

---

## 六、测试用例设计说明

本测试套件基于现有代码库分析设计：
- **F1**: 基于 `persistent_session.py` 中现有的 TTL 机制（`ttl_seconds` 参数、`_cleanup_expired`、`get_session` TTL 检查）
- **F2**: 基于 `hook_engine.py` 中现有的 `HookAction.MODIFY` 和 `HookContext` API，测试 REPLACE/REDACT/ADD/REMOVE/CLAMP 5 种操作模式

部分测试依赖 `time.sleep` 进行 TTL 过期验证，在高负载环境下可能需调整等待时间。

---

*报告生成: 2026-04-01 22:20 GMT+8*
*真显（测试者）*
