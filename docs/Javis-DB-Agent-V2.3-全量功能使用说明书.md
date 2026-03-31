# Javis-DB-Agent V2.3 全量功能使用说明书

> 版本：V2.3 | 日期：2026-03-31  
> 项目路径：https://github.com/chongjie-ran/Javis-DB-Agent  
> 代码规模：~13,764行核心代码 | 测试用例：600+

---

## 目录

1. [产品概述](#一产品概述)
2. [Agent层功能](#二agent层功能)
3. [Gateway层功能](#三gateway层功能)
4. [安全层功能](#四安全层功能)
5. [知识层功能](#五知识层功能)
6. [工具层功能](#六工具层功能)
7. [API层功能](#七api层功能)
8. [数据层功能](#八数据层功能)
9. [通道层功能](#九通道层功能)
10. [LLM层功能](#十llm层功能)
11. [DevOps与部署](#十一devops与部署)
12. [版本演进历史](#十二版本演进历史)
13. [测试覆盖统计](#十三测试覆盖统计)

---

## 一、产品概述

### 1.1 产品定位

**Javis-DB-Agent** 是面向数据库运维场景的智能体系统，赋能DBA和运维人员实现：
- 🔍 **智能诊断**：AI驱动的告警诊断，自动根因分析
- 🔒 **安全护栏**：SQL AST解析，危险操作审批流
- 📚 **知识积累**：SOP执行器，知识图谱辅助决策
- ✅ **受控闭环**：从"建议输出"到"受控执行"

### 1.2 核心架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户层                                  │
│           (CLI / Web Dashboard / API / 消息通道)           │
└────────────────────────────┬────────────────────────────────┘
                              │
┌────────────────────────────▼────────────────────────────────┐
│                   Agent Gateway (核心)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ 会话管理  │ │ 工具注册  │ │ 策略引擎  │ │ 审批网关  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                    │
│  │ 审计日志  │ │ 告警关联  │ │ 分布式   │                    │
│  └──────────┘ └──────────┘ └──────────┘                    │
└────────────────────────────┬────────────────────────────────┘
                              │
┌────────────────────────────▼────────────────────────────────┐
│                     智能决策层 (11个Agent)                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ 编排Agent │ │ 诊断Agent │ │ 风险Agent │ │ SQL分析  │           │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ 巡检Agent│ │ 报告Agent│ │ 会话分析 │ │ 容量Agent│           │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘           │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐                       │
│  │ 告警Agent│ │ 备份Agent│ │ 性能Agent│                       │
│  └─────────┘ └─────────┘ └─────────┘                       │
└────────────────────────────┬────────────────────────────────┘
                              │
┌────────────────────────────▼────────────────────────────────┐
│                   安全层 + 知识层 + 工具层                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ SQL AST护栏   │ │ SOP执行器     │ │ 知识图谱     │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ ApprovalGate │ │ 案例库+RAG   │ │ 48个工具    │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
└────────────────────────────┬────────────────────────────────┘
                              │
┌────────────────────────────▼────────────────────────────────┐
│                       数据层                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ PostgreSQL   │ │   MySQL     │ │   Mock API  │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、Agent层功能

> 路径：`src/agents/`

### 2.1 核心Agent（V1.0基础框架）

| Agent | 文件 | 职责 | 核心能力 |
|-------|------|------|----------|
| **Orchestrator** | `orchestrator.py` | 编排调度 | 多Agent协作、意图路由、语义工具选择 |
| **Diagnostic** | `diagnostic.py` | 诊断专家 | 告警诊断、根因分析、A→B→C链式关联 |
| **Risk** | `risk.py` | 风险专家 | L1-L5五级风险、动态调整、细粒度权限 |
| **SQLAnalyzer** | `sql_analyzer.py` | SQL分析 | 执行计划解读、索引建议、SQL改写 |
| **Inspector** | `inspector.py` | 巡检专家 | 健康检查、资源探查、健康评分90-100 |
| **Reporter** | `reporter.py` | 报告专家 | RCA报告、巡检报告、周报月报 |

### 2.2 扩展Agent（V1.1-V1.4新增）

| Agent | 版本 | 核心工具 |
|-------|------|----------|
| **SessionAnalyzer** | V1.1 | session_list, connection_pool, deadlock_detection |
| **CapacityAgent** | V1.1 | storage_analysis, growth_prediction, capacity_alert |
| **AlertAgent** | V1.1 | alert_analysis, deduplication, root_cause, predictive_alert |
| **BackupAgent** | V1.4 | check_backup_status, trigger_backup, estimate_restore_time |
| **PerformanceAgent** | V1.4 | extract_top_sql, explain_sql_plan, suggest_parameters |

### 2.3 Agent增强能力

- **语义工具选择**：基于语义理解动态选择最合适的Agent/工具，非硬编码映射
- **16种Intent识别**：每种Intent有6-13个同义表达样本
- **语义向量匹配**：Chroma + Embedding，余弦相似度阈值0.75
- **LLM语义Fallback**：向量匹配置信度不足时降级到LLM判断
- **上下文融合**：融入最近3轮对话上下文，理解指代和省略
- **样本自演化**：IntentExampleCollector自动收集用户反馈

---

## 三、Gateway层功能

> 路径：`src/gateway/`

### 3.1 会话管理
- **PersistentSession**：`persistent_session.py` — 会话持久化（SQLite），支持重启后上下文恢复
- **Session**：`session.py` — 轻量级会话上下文封装

### 3.2 工具注册与路由
- **ToolRegistry**：`tool_registry.py` — 工具注册中心，动态注册与发现
- **DualEngineToolExecutor**：`src/tools/db_adapter.py` — 双引擎路由，自动识别db_type
- **DBRouter**：`db_router.py` — 数据库类型路由分发

### 3.3 策略引擎
- **PolicyEngine**：`policy_engine.py` — 策略执行引擎（V2.3完成迁移）
- **UserRole权限模型**：VIEWER(1) → ADMIN(5)，逐级递增
- **角色-风险级别映射**：
  - VIEWER：L1只读
  - ANALYST：L1+L2
  - ADVISOR：L1+L2+L3
  - OPERATOR：L1+L2+L3+L4
  - ADMIN：全部

### 3.4 审批网关
- **ApprovalGate**：`approval.py` — 完整审批流程（V2.1新增）
  - L4高风险：单签审批（会话终止等）
  - L5极高风险：双人审批（DROP TABLE等）
  - PENDING队列管理
- **ApprovalAdapter**：`approval_adapter.py` — 同步适配器，兼容旧系统（V2.3新增）
- **Distributed**：`distributed.py` — 分布式策略分发

### 3.5 审计
- **Audit**：`audit.py` — 全链路审计日志，哈希链防篡改
- **敏感数据脱敏**：password/token/secret/api_key等字段自动Mask

### 3.6 告警关联
- **AlertCorrelator**：`alert_correlator.py` — 告警关联分析，A→B→C链式诊断

---

## 四、安全层功能

> 路径：`src/security/`

### 4.1 SQL安全护栏（V2.0新增）

**AST Parser** (`sql_guard/ast_parser.py`)：
- ✅ sqlglot集成，支持MySQL/PostgreSQL/Oracle/OceanBase方言
- ✅ 表名提取 `get_tables()`
- ✅ 操作类型识别 `get_operations()`
- ✅ 危险函数检测

**UNION注入防护**：
- ✅ `union_count > union_all_count` 直接检测
- ✅ UNION SELECT拦截，UNION ALL放行
- ✅ CTE+UNION安全识别

**is_read_only扩展**：
- ✅ SELECT/INSERT/UPDATE/DELETE分类
- ✅ EXPLAIN/VACUUM/ANALYZE只读判断
- ✅ SET命令识别为非只读

**白名单模板** (`sql_guard/template_registry.py`)：
- ✅ 正则表达式匹配
- ✅ 支持 `schema.table` 和带引号标识符
- ✅ MySQL/PostgreSQL双模板库

### 4.2 SOP执行框架（V2.0新增）

**YAML SOP Loader** (`security/execution/yaml_sop_loader.py`)：
- ✅ 从YAML加载SOP定义
- ✅ 支持 `knowledge/sop_yaml/` 目录

**SOP Executor** (`security/execution/sop_executor.py`)：
- ✅ 状态机：PENDING → RUNNING → COMPLETED/FAILED/ABORTED
- ✅ 逐步骤执行，支持暂停/继续/中止
- ✅ 审批门控：WAITING_APPROVAL状态

**Action→Tool映射** (`security/execution/action_tool_mapper.py`)：
- ✅ 22个action映射到具体工具
- ✅ `find_idle_sessions` → `pg_session_analysis`
- ✅ `kill_session` → `pg_kill_session`

**执行回流验证** (`security/execution/execution_feedback.py`)：
- ✅ PreCheck/PostCheck Hook
- ✅ 状态对比验证：IMPROVED/UNCHANGED/DEGRADED

**内置SOP（3个）**：
| SOP | 说明 |
|-----|------|
| slow_sql_diagnosis | 慢SQL诊断 |
| lock_wait_diagnosis | 锁等待诊断 |
| session_cleanup | 会话清理 |

### 4.3 认证与鉴权

- **OAuth2 Provider**：`real_api/auth.py` — RFC6749规范，client_credentials + refresh_token
- **API Key认证**：双模式支持
- **JWT刷新机制**：Token类型区分，Replay攻击防护
- **TLS/SSL配置**：HTTPS强制

### 4.4 限流与脱敏

- **Rate Limit**：`security/rate_limit.py` — IP/用户维度滑动窗口限流
- **Sensitive Masking**：审计日志、API响应、日志敏感信息Mask

---

## 五、知识层功能

> 路径：`src/knowledge/`

### 5.1 知识库核心（V1.2结构化改造）

- **TaxonomyService**：`knowledge/services/taxonomy_service.py`
- **TaxonomyRepository**：`knowledge/repositories/taxonomy_repository.py`
- **Entity/Resource/ObservationPoint模型**：结构化知识表示

### 5.2 向量与语义

- **VectorStore**：`knowledge/vector_store.py` — Chroma向量存储
- **EmbeddingService**：文本向量化服务
- **IntentExampleCollector**：样本自演化闭环
- **样本自演化**：用户反馈 → 样本自动学习 → 意图识别增强

### 5.3 高级知识能力

- **依赖传播引擎**（Round 19）：资源依赖传播与根因分析
- **观察点元数据服务**（Round 20）：ObservationPointMetadataService
- **知识库自演化闭环**（Round 21）：LLM+可观测驱动知识库自演化

### 5.4 知识API

- **Taxonomy REST API**：`src/api/knowledge_routes/`

---

## 六、工具层功能

> 路径：`src/tools/` — **48个工具**

### 6.1 工具分类

| 类别 | 数量 | 风险级别 | 示例 |
|------|------|----------|------|
| 查询工具 | 14 | L1只读 | query_instance_status, query_session |
| 会话工具 | 4 | L1只读 | session_list, session_detail |
| 告警工具 | 4 | L1只读 | alert_analysis, alert_deduplication |
| 分析工具 | 3 | L2诊断 | analyze_impact, analyze_sql_pattern |
| 容量工具 | 4 | L1只读 | storage_analysis, growth_prediction |
| 备份工具 | 4 | L3低风险 | check_backup_status, trigger_backup |
| 性能工具 | 3 | L2诊断 | extract_top_sql, explain_sql_plan |
| PostgreSQL工具 | 6 | L2-L4 | pg_session_analysis, pg_kill_session |
| 高危工具 | 2 | L4-L5 | kill_session, execute_sql |
| 动作工具 | 4 | L3低风险 | trigger_inspection, create_work_order |

### 6.2 工具执行器

- **BaseTool**：统一接口规范
- **ToolRegistry**：动态工具注册与发现
- **DualEngineToolExecutor**：MySQL/PostgreSQL/Oracle自动路由

### 6.3 PostgreSQL专用工具

| 工具 | 说明 | 风险 |
|------|------|------|
| pg_session_analysis | 会话分析（pg_stat_activity） | L1 |
| pg_lock_analysis | 锁分析（pg_locks） | L1 |
| pg_replication_status | 复制状态（pg_stat_replication） | L1 |
| pg_bloat_analysis | 表膨胀分析 | L2 |
| pg_index_analysis | 索引分析 | L2 |
| pg_kill_session | 终止会话 | L4 |

---

## 七、API层功能

> 路径：`src/api/` + `src/real_api/` + `src/mock_api/`

### 7.1 Real API Client（V1.0）

**9个API接口**：
- instances（实例管理）
- alerts（告警）
- sessions（会话）
- locks（锁）
- sqls（SQL）
- replication（复制）
- capacity（容量）
- inspection（检查）
- workorders（工单）

### 7.2 REST路由

| 路由 | 文件 | 说明 |
|------|------|------|
| Dashboard | `dashboard.py` | Web管理界面API |
| Approval | `approval_routes.py` | 审批流REST API |
| Audit | `audit_routes.py` | 审计记录API |
| Auth | `auth_routes.py` | 认证API |
| Chat Stream | `chat_stream.py` | 流式聊天接口 |
| Knowledge | `knowledge_routes/` | 知识库管理API |
| Monitoring | `monitoring_routes.py` | 监控指标API |
| Metrics | `metrics.py` | 指标收集API |

### 7.3 API端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/approvals/pending | 获取待审批列表 |
| GET | /api/v1/approvals/{id} | 获取审批详情 |
| POST | /api/v1/approvals/{id}/approve | 审批通过 |
| POST | /api/v1/approvals/{id}/reject | 审批拒绝 |

### 7.4 Mock API

- **Mock Javis API**：`mock_javis_api/` — Mock后端（端口18080）
- **API模式切换**：`scripts/switch_api_mode.py` — mock ↔ real一键切换

---

## 八、数据层功能

> 路径：`src/db/`

### 8.1 数据库适配器

- **DB Adapter Layer**：`db/base.py` — 统一适配器接口
- **MySQL Adapter**：`db/mysql_adapter.py`
- **PostgreSQL Adapter**：`db/postgres_adapter.py`

### 8.2 直连数据库（V2.0新增）

- **DirectPostgresConnector**：`db/direct_postgres_connector.py`
  - asyncpg直连PostgreSQL
  - 支持直连模式和API适配器双模式
  - 真实数据库环境打通

---

## 九、通道层功能

> 路径：`src/channels/`

| 通道 | 说明 |
|------|------|
| **WeCom** | 企业微信消息通道 |
| **Feishu** | 飞书消息通道 |
| **Email** | 邮箱消息通道 |

---

## 十、LLM层功能

> 路径：`src/llm/`

- **Ollama Client**：`llm/ollama_client.py` — 本地LLM客户端，支持加密通信
- **语义意图识别**：Embedding向量相似度 + LLM语义Fallback双模式
- **上下文融合**：融合最近3轮对话上下文

---

## 十一、DevOps与部署

### 11.1 部署方式

| 方式 | 说明 |
|------|------|
| **Docker** | Dockerfile + docker-compose.yml（支持amd64/arm64） |
| **systemd** | javis-agent.service 开机自启 |
| **一键脚本** | install.sh（Ubuntu/CentOS/RHEL/macOS） |
| **Python包** | pyproject.toml + Makefile |

### 11.2 CI/CD

- **GitHub Actions**：自动构建+测试+发布

### 11.3 Web界面

- **Dashboard**：`templates/dashboard.html` — Web管理界面

---

## 十二、版本演进历史

| 版本 | 日期 | 核心功能 | Git Tag |
|------|------|----------|--------|
| **v1.0** | 2026-03-28 | 基础框架：6 Agent + Gateway + Mock API + OAuth2 | ✅ |
| **v1.1** | 2026-03-29 | 能力扩展：双引擎路由 + Session/Capacity/Alert Agent | ✅ |
| **v1.2** | 2026-03-29 | 知识结构化：Taxonomy API + 依赖传播 + 知识自演化 | ✅ |
| **v1.3** | 2026-03-30 | AI泛化：语义路由 + 样本自演化 + 上下文融合 | ✅ |
| **v1.3.1** | 2026-03-30 | 跨平台：Docker + systemd + GitHub Actions | ✅ |
| **v1.4** | 2026-03-30 | 新Agent：BackupAgent + PerformanceAgent | ✅ |
| **v1.5** | 2026-03-30 | DFX测试：160用例DFX深度测试框架 | ✅ |
| **v1.5.1** | 2026-03-30 | 修复：IntentExampleCollector API测试 | ✅ |
| **v2.0** | 2026-03-31 | 真实环境：YAML SOP Loader + DirectPostgresConnector | ✅ |
| **v2.1** | 2026-03-31 | SQL安全：SQL AST护栏 + UNION检测 + ApprovalGate | ✅ |
| **v2.2** | 2026-03-31 | 质量：API前缀统一 + 旧ApprovalGate废弃 + 文档 | ✅ |
| **v2.3** | 2026-03-31 | 迁移：ApprovalAdapter + policy_engine迁移 + distributed修复 | ✅ |

---

## 十三、测试覆盖统计

| 版本 | 测试套件 | 测试用例数 |
|------|----------|------------|
| **V1.3** | round15 (6个文件) | ~120+ |
| **V1.4** | round16 (3个文件) | ~60+ |
| **V1.5 DFX** | v1.5/validation | 67 |
| **V2.0 Mock** | v2.0 (4个文件) | ~150+ |
| **V2.0 RealPG** | v2.0/real_pg (3个文件) | 80 |
| **V2.1** | v2.0/approval_gate + v21_verification | ~60+ |
| **V2.2** | v2.0/integration | 集成场景覆盖 |
| **Unit** | unit/ | ~100+ |
| **总计** | | **600+** |

### 真实环境测试（V2.0）

| 测试文件 | 测试数 | 说明 |
|----------|--------|------|
| test_real_pg_security.py | 29 | SQL AST解析、危险SQL检测 |
| test_real_pg_knowledge.py | 21 | SOP执行、知识层 |
| test_real_pg_perception.py | 30 | 拓扑感知、配置感知 |
| **合计** | **80** | **全部通过** ✅ |

---

## 附录：快速参考

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| JAVIS_PG_HOST | localhost | PostgreSQL主机 |
| JAVIS_PG_PORT | 5432 | PostgreSQL端口 |
| JAVIS_PG_USER | postgres | PostgreSQL用户 |
| JAVIS_PG_PASSWORD | | PostgreSQL密码 |
| JAVIS_PG_DATABASE | postgres | 数据库名 |
| JAVIS_API_MODE | mock | mock/real模式 |

### 启动命令

```bash
# Mock模式（开发测试）
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# 真实API模式
export JAVIS_API_MODE=real
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# Dashboard
open http://localhost:8000/dashboard/
```

---

*文档版本：V2.3*
*最后更新：2026-03-31*
*整理来源：道衍（架构视角）+ 悟通（代码视角）+ 真显（测试视角）*
