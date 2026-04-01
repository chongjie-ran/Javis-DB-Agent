# Javis-DB-Agent V2.6.1 & V2.7 Release Notes

## 发布日期
2026-04-01

---

## V2.7 主要更新

### Webhook/Callback 审批通知

- **Event-based 等待机制** — 替代 2 秒轮询，实时响应审批结果
- **POST /api/v1/approvals/webhook** — 回调接口，审批完成后即时通知
- **HMAC-SHA256 签名验证** — 请求体完整性校验，防篡改
- **IP 白名单** — 仅允许白名单 IP 发起的回调请求
- **Replay 攻击防护** — `X-Webhook-Timestamp` + `X-Webhook-Nonce` 头防重放

### 安全改进

| 级别 | 问题 | 状态 |
|------|------|------|
| P0 | Webhook 无认证漏洞 | ✅ 已修复 |
| - | HMAC 签名防止篡改 | ✅ 已实现 |
| - | IP 白名单限制来源 | ✅ 已实现 |

---

## V2.6.1 主要更新

### Token TTL 机制

- **params_hash 参数漂移检测** — 参数变化时强制重新审批
- **expires_at 过期时间控制** — ApprovalToken 带过期时间戳
- **双重校验** — TTL 过期 + 参数一致性，双重保障

### Hook MODIFY 动作

- **5 种修改操作**：REPLACE / REDACT / ADD / REMOVE / CLAMP
- **嵌套字段路径支持** — 如 `data.nested.field`
- **SQL 注入防护增强** — MODIFY 操作多重校验

### 后台自动清理

- **后台线程每 5 分钟自动清理** — 过期会话自动回收
- **与 ApprovalToken TTL 机制分离** — 独立运行，互不干扰

---

## V2.6 主要更新（历史版本）

### F1: Hook 事件驱动系统
- 14 种 HookEvent 枚举
- async/sync 双模式支持

### F2: 并行 Agent 执行引擎
- 6 种 Intent 并行策略
- 置信度加权聚合

### F3: SafetyGuardRail
- 不可绕过审批门卫
- L4/L5 强制审批

### F4: 可观测性框架
- Tracer (OpenTelemetry)
- Metrics (Prometheus)
- Logger (JSON Lines)

---

## 测试结果

| 模块 | 通过 | 总计 | 状态 |
|------|------|------|------|
| Token TTL | 30 | 30 | ✅ |
| Hook MODIFY | 26 | 26 | ✅ |
| Webhook | 38 | 38 | ✅ |
| Guard Rail | 23 | 23 | ✅ |
| **总计** | **173** | **173** | **✅ 全部通过** |

---

## 已知问题

- `test_scanner.py` — 需要真实 PostgreSQL/MySQL 进程
- `test_unified_client.py` — 依赖本地 `.env` 配置

---

## 升级指南

详见 [UPGRADE.md](./UPGRADE.md)（如有）

---

## 版本历史

| 版本 | 日期 | 重要变更 |
|------|------|----------|
| V2.7 | 2026-04-01 | Webhook 审批通知、HMAC 签名、IP 白名单 |
| V2.6.1 | 2026-04-01 | Token TTL、Hook MODIFY、后台自动清理 |
| V2.6 | 2026-04-01 | Hook 事件驱动、并行引擎、SafetyGuardRail、可观测性 |
| V2.5 | 2026-04-01 | Inspector 真实 DB 连接器、Ollama qwen3.5:35b |
| V2.4 | 2026-03-31 | 数据库发现模块、PostgreSQL/MySQL 发现 |
| V2.3 | 2026-03-31 | ApprovalGate 迁移、分布式修复 |
| V2.2 | 2026-03-31 | API prefix 统一、ApprovalGate 整理 |
| V2.1 | 2026-03-31 | YAML SOP Loader、Action→Tool 映射、ApprovalGate |
| V2.0 | 2026-03-31 | SQL AST 护栏、ApprovalGate 基础架构 |
