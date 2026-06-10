# Javis-DB-Agent 版本功能清单

> 项目路径：`~/SWproject/Javis-DB-Agent/`
> 整理时间：2026-04-02
> 整理人：真显（测试者）

---

## 版本标签
```
V2.7.1, v2.7, v2.6.1, v2.6, v2.5, v2.4, v2.3, v2.3.1, v2.2, v2.1,
v1.5.1, v1.5, v1.4, v1.3.1, v1.3, v1.2.1, v1.2, v1.1, v1.0, v1.0-Beta
```

---

## V2.7.1 — 2026-04-02（最新）
**Commit:** `7e7aaf3`

### 新增/修复
- **P0: Webhook无认证漏洞修复** — Webhook端点添加认证，防止绕过审批
- **P1: RLock死锁修复** — Hook Registry并发安全
- **Hook Registry增强** — Registry并发安全加固

### 安全修复
| 级别 | 问题 | 状态 |
|------|------|------|
| P0 | Webhook无认证漏洞 | ✅ 已修复 |

---

## V2.7 — 2026-04-01
**Commits:** `ac85dc3, 7c843a0, f571a53, 3bb3e41`

### 新增功能
- **Webhook/Callback审批通知** — 替代2秒轮询的Event-based等待机制
  - `POST /api/v1/approvals/webhook` 回调接口
  - HMAC-SHA256签名验证（防篡改）
  - IP白名单限制来源
  - Replay攻击防护（Timestamp + Nonce）
- **inspect.iscoroutinefunction** — 替代已弃用的asyncio.iscoroutinefunction

### 修复
- **审批模块问题** — 多项审批相关Bug修复
- **P0安全漏洞** — Webhook无认证漏洞

---

## V2.6.1 — 2026-04-01
**Commits:** `a01a93a, c3e4833`

### 新增功能
- **Token TTL机制** — ApprovalToken增加`params_hash` + `expires_at`
  - 参数漂移检测（参数变化强制重新审批）
  - 过期时间控制（TTL双重校验）
- **Hook MODIFY动作** — 5种操作：REPLACE/REDACT/ADD/REMOVE/CLAMP
  - 嵌套字段路径支持（如`data.nested.field`）
  - SQL注入防护增强
- **后台自动清理** — 后台线程每5分钟自动清理过期会话

---

## V2.6 — 2026-04-01
**Commits:** `165aa6d, 4f0ea01, 1c5b09e, 7654b23`

### 四大核心特性（F1-F4）

| 编号 | 功能 | 源码位置 |
|------|------|----------|
| **F1** | Hook事件驱动系统 | `src/gateway/hooks/` |
| **F2** | 并行Agent执行引擎 | `src/agents/executor/` |
| **F3** | SafetyGuardRail | `src/security/guard_rail.py` |
| **F4** | 可观测性框架 | `src/observability/` |

### F1 Hook事件驱动系统
- 14种HookEvent枚举
- async/sync双模式支持
- 规则引擎：`src/gateway/hooks/rule_engine.py`

### F2 并行Agent执行引擎
- `ParallelAgentExecutor` — 6种Intent并行策略
- 置信度加权聚合

### F3 SafetyGuardRail
- 不可绕过审批门卫
- L4/L5高风险操作强制审批

### F4 可观测性框架
- Tracer — OpenTelemetry集成
- Metrics — Prometheus格式指标
- Logger — JSON Lines结构化日志

### 安全修复
- **P1-1 ReDoS风险** — 正则编译缓存
- **P1-2 线程安全** — 全局单例threading.Lock保护

---

## V2.5 — 2026-04-01（分阶段开发）

### R1: 数据库发现与扫描
**Commits:** `8c8c9dc, 1966cb9`
- **数据库发现模块** — 自动发现并注册数据库实例
- **PostgreSQL发现** — 数据库扫描器支持PostgreSQL
- **MySQL发现** — aiomysql支持MySQL发现

### R2: Inspector真实DB连接器
**Commits:** `0cc5178, 1761f98, 8c8c9dc`
- **Inspector真实DB连接器** — InspectorAgent识别并使用`context.pg_connector`直连数据库
- **DirectPostgresConnector** — asyncpg直连PostgreSQL，支持连接池管理
- **添加真实数据库连接器到chat上下文**

### R3: LLM优化
**Commits:** `a8b49bc, cf17a31, 0849cc7`
- **Orchestrator LLM Fallback优化** — 主LLM失败时智能降级到备用响应
- **Ollama qwen3.5:35b集成** — 支持本地部署LLM模型
- **qwen3.5:35b兼容性** — thinking字段输出兼容处理

### Bug修复
- 连接器识别问题
- fallback触发逻辑
- scanner: `proc.net_connections` 替代已废弃的 `proc.connections`

### 测试
- **91用例集成测试**全通过（round23）
- **41测试用例**覆盖v2.5新功能（round26）

---

## V2.4 — 2026-03-31
**Commits:** `8c8c9dc, 28c6c69, 40e7bc9`

- **数据库发现模块** — 自动发现并注册数据库实例
- **PostgreSQL发现** — 数据库扫描器支持PostgreSQL
- **MySQL发现** — aiomysql支持MySQL发现
- **scanner修复** — `proc.net_connections` 替代已废弃的 `proc.connections`

---

## V2.3 — 2026-03-31
**Commits:** `c4321b9, 6c4d00e`

- **ApprovalGate迁移** — adapter + policy_engine架构
- **分布式修复** — ApprovalGate分布式场景修复
- **ApprovalGate回归修复** — singleton accessor和record.id修复
- **V2.3产品手册** — 完整功能使用说明书
- **部署指南** — 详细部署文档

---

## V2.2 — 2026-03-31
**Commits:** `e8fb510`

- **API prefix统一** — 所有API路由使用`/api/v1/`前缀
- **ApprovalGate清理** — 移除冗余代码，修复pending审批列表
- **docs/sop-yaml-format.md** — YAML SOP格式规范文档
- **docs/approval-api.md** — ApprovalGate API文档

---

## V2.1 — 2026-03-31
**Commits:** `d102863`

### 新增功能
- **YAML SOP Loader** — `src/security/execution/yaml_sop_loader.py`
- **Action→Tool Mapper** — 22个action映射（`src/security/execution/action_tool_mapper.py`）
- **DirectPostgresConnector** — asyncpg直连PG（`src/db/direct_postgres_connector.py`）
- **ApprovalGate** — 完整审批流（L4单签/L5双人）（`src/gateway/approval.py`）
- **Approval Routes** — REST审批API（`src/api/approval_routes.py`）
- **PGKillSessionTool** — L4高风险会话终止工具
- **3个SOP迁移** — slow_sql_diagnosis, lock_wait_diagnosis, session_cleanup

### 安全修复
- **UNION注入Bug** — 删除死代码，改用count检测
- **is_read_only()** — 支持EXPLAIN/VACUUM/ANALYZE
- **白名单正则** — 支持schema.table和带引号标识符
- **pg_explain正则** — FORMAT子句可选
- **BUG-001** — sop_id/step_id字段映射
- **API注册** — approval_router未注册到main.py

---

## V2.0 — 2026-03-30/31
**Commits:** `6519939, 1363bdb, 7623e3e, bfa7691, 4c31c25, 6679401, ce27420`

- **P0-1 SQL AST护栏** — SQL语法树级安全防护
- **SOP执行器** — retry和error handling完善
- **测试修复** — Round4集成测试13个失败修复、Round5单元测试45个失败修复

---

## V1.5 — 2026-03-30
**Commits:** `7bf06a3, 6538869, d522a40, 1674de7, d230837, 8950647, 90bf693, 4b0a41e, 8b98b89`

### 新增功能
- **BackupAgent** — 备份恢复专家（check_backup_status/list_backup_history/trigger_backup/estimate_restore_time）
- **PerformanceAgent** — 性能分析专家（extract_top_sql/explain_sql_plan/suggest_parameters）
- **DFX深度测试框架** — 160用例（47✅/19❌/1⏭️）
- **Intent样本库扩展** — 16个Intent × 6-13个同义表达
- **语义路由增强** — 余弦相似度匹配（阈值0.75）
- **样本自演化闭环** — IntentExampleCollector自动收集用户反馈
- **上下文融合** — 融入最近3轮对话

---

## V1.4 — 2026-03-30
**Commits:** `90bf693, 4b0a41e, 8b98b89, 4b002cf`

- **BackupAgent** — Round 1备份恢复专家
- **PerformanceAgent** — Round 1性能分析专家
- **Orchestrator集成** — BackupAgent/PerformanceAgent注册到编排器
- **OAuth2 refresh_token** — RFC6749规范完善
- **跨平台安装脚本** — install.sh支持Ubuntu/CentOS/RHEL/macOS

---

## V1.3.1 — 2026-03-30
**Commits:** `4b002cf, 8b98b89`

- **跨平台安装脚本增强** — 动态Python版本检测
- **Docker支持** — Dockerfile + docker-compose.yml
- **systemd服务** — javis-agent.service开机自启
- **GitHub Actions** — 自动构建+测试+发布
- **Python包构建** — pyproject.toml + Makefile
- **跨平台兼容性测试** — tests/round15/test_platform_compat.py
- **asyncio兼容性** — asyncio.run()替换废弃的get_event_loop()

---

## V1.3 — 2026-03-30
**Commits:** `7bf06a3`（与V1.5共享部分提交）

- **语义工具选择增强** — `_select_agents()`基于语义的动态工具选择
- **端到端泛化测试** — 31个测试用例（tests/round15/test_e2e_generalization.py）
- **LLM Fallback完善** — Prompt优化，新增识别规则示例

---

## V1.2.1 / V1.2 / V1.1 — 早期版本
- D01测试隔离、D03刷新令牌、D08并发、R07绝对路径修复
- 重命名为Javis-DB-Agent
- OAuth2 refresh_token补全
- API限速（IP/用户维度滑动窗口）
- Pydantic V3迁移
- 敏感数据脱敏
- JWT刷新、Token类型区分、Replay攻击防护
- TLS/SSL配置

---

## 源码目录结构
```
src/
├── agents/          # Agent实现（Orchestrator, Inspector, Reporter, Backup, Performance, SQLAnalyzer）
├── api/             # API路由（routes, schemas, auth, approval, chat_stream, monitoring）
├── channels/        # 消息通道（wecom, feishu, email）
├── db/              # 数据库连接器（Adapter Layer: base, mysql_adapter, postgres_adapter）
├── discovery/       # 数据库发现模块
├── gateway/         # 网关（approval, hooks, session, tool_registry）
├── knowledge/       # 知识库
├── llm/             # LLM客户端（Ollama）
├── models/          # 数据模型
├── observability/   # 可观测性（Tracer, Metrics, Logger）
├── real_api/        # 真实API客户端
├── security/        # 安全（rate_limit, guard_rail, execution）
└── tools/           # 工具定义
```

---

## 端点超时行为（统一配置）
| 端点 | 超时 | 超时行为 |
|------|------|----------|
| POST /api/v1/chat | 30s | → HTTP 504 |
| POST /api/v1/diagnose | 30s | → HTTP 504 |
| POST /api/v1/analyze/sql | 30s | → HTTP 504 |
| POST /api/v1/inspect | 30s | → HTTP 504（修复后，与其他端点一致） |
| POST /api/v1/report | 30s | → HTTP 504 |

> **注意**：`/inspect`端点在V2.7.1之前存在超时行为不一致Bug（超时时追加结果继续执行），现已修复为与其他端点一致的超时抛出504行为。

---

*最后更新：2026-04-02*
