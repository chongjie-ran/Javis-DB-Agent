# V2.6.1 + V2.7 真实DB测试报告

**测试时间**: 2026-04-01  
**测试环境**: PostgreSQL 16.13 (localhost:5432), zcloud_agent_test DB  
**测试目录**: tests/round30/, tests/round31/  
**结果**: ✅ 94/94 通过

---

## 测试结果汇总

| 测试文件 | 用例数 | 通过 | 失败 | 耗时 |
|----------|--------|------|------|------|
| test_hook_modify.py | 26 | 26 | 0 | 0.14s |
| test_token_ttl.py | 30 | 30 | 0 | 32.45s |
| test_webhook_callback.py | 10 | 10 | 0 | - |
| test_webhook_integration.py | 15 | 15 | 0 | - |
| test_webhook_security.py | 13 | 13 | 0 | - |
| **总计** | **94** | **94** | **0** | **36.54s** |

---

## 发现并修复的问题

### Bug 1: 死锁 — `PersistentSessionManager` 使用非重入锁

**文件**: `src/gateway/persistent_session.py`  
**问题**: 类级别 `_lock` 使用 `threading.Lock()`（非重入），`create_session()` 持有锁时调用 `delete_session()` 导致死锁  
**影响**: `test_max_sessions_lru_eviction` (DV-10) 超时失败  
**修复**: 将 `threading.Lock()` 改为 `threading.RLock()`  
```python
# Before
_lock = threading.Lock()  # 类级别的锁
# After
_lock = threading.RLock()  # 类级别的可重入锁（支持同一线程重复获取）
```

### Bug 2: 测试断言顺序错误 — DV-04

**文件**: `tests/round30/test_token_ttl.py`  
**问题**: `test_cache_expired_db_valid_returns_none` 在 `get_session()` 之前检查 cache 内容，TTL 过期检查仅在 `get_session()` 中触发  
**影响**: 误报失败  
**修复**: 调整断言顺序，先调用 `get_session()` 再检查 cache  

---

## 测试覆盖详情

### V2.6.1 Token TTL (30 tests)
- **TTL过期检查** (10 tests): TTL-01~TTL-10 — 验证会话在 TTL 后正确过期
- **params_hash 参数漂移检测** (7 tests): PHD-01~PHD-07 — 验证参数变化检测的正确性
- **双重校验逻辑** (10 tests): DV-01~DV-10 — Cache+DB 双重校验，含 LRU 淘汰
- **全局单例** (3 tests): SM-01~SM-03 — SessionManager 单例行为

### V2.6.1 Hook MODIFY (26 tests)
- **REPLACE 操作** (5 tests): REP-01~REP-05 — 字段替换、嵌套字段替换、链式执行
- **REDACT 操作** (5 tests): RED-01~RED-05 — 密码/邮箱/信用卡脱敏、SQL注释移除
- **ADD/REMOVE/CLAMP** (7 tests): ARC-01~ARC-07 — 字段增删、值限制
- **混合动作** (4 tests): MIX-01~MIX-04 — MODIFY+BLOCK/WARN/LOG 组合
- **真实SQL场景** (4 tests): RLS-01~RLS-04 — SQL注入防护、DDL白名单、超时限制

### V2.7 Webhook (38 tests)
- **Callback注册** (10 tests): register/unregister/trigger/async 回调机制
- **Event等待机制** (5 tests): Event-based 等待替代轮询，< 0.1s 响应
- **API Schema** (3 tests): WebhookPayload/WebhookResponse 数据模型
- **Event设置** (3 tests): approve/reject/timeout 时 Event 被正确设置
- **HMAC签名** (4 tests): 有效/无效/未配置密钥/空签名场景
- **IP白名单** (4 tests): 单IP/CIDR/多网络/未配置场景
- **Reject幂等性** (2 tests): 同审批人重复reject被忽略
- **ClientIP提取** (3 tests): X-Forwarded-For/X-Real-IP/直接连接

---

## 商用标准评估

| 维度 | 状态 | 说明 |
|------|------|------|
| Token TTL | ✅ | 双重校验（Cache+DB）正确，LRU 淘汰工作正常 |
| Hook MODIFY | ✅ | REPLACE/REDACT/ADD/REMOVE/CLAMP 全部正常工作 |
| Webhook | ✅ | HMAC签名、IP白名单、回调机制全部通过 |
| 并发安全 | ✅ (修复后) | RLock 修复了死锁问题 |
| 幂等性 | ✅ | Reject 重复调用不改变状态 |
