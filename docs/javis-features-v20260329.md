# Javis-DB-Agent 软件功能说明

> **文档版本**: v20260329_094422
> **项目版本**: v1.0
> **生成日期**: 2026-03-29
> **状态**: 正式版

---

## 一、项目概述

### 1.1 项目简介

**Javis-DB-Agent** 是面向**数据库运维场景**的本地智能体（Agent）系统，旨在赋能DBA和运维人员实现智能诊断、自动巡检与安全闭环处置。

系统以**Ollama**（本地LLM推理引擎）为智能核心，通过多Agent协作架构，连接**zCloud数据库管理平台**的Mock/真实API，实现自然语言驱动的数据库运维智能化。

### 1.2 核心设计目标

| 目标 | 说明 |
|------|------|
| **智能诊断** | 基于LLM的告警根因分析，支持A→B→C链式告警关联推理 |
| **安全闭环** | L1-L5风险分级，高风险操作需审批，完整审计留痕 |
| **知识沉淀** | 内置告警规则库（15+规则）、SOP库（8个）、案例库（3个） |
| **双模运行** | Mock API（开发测试）与 Real API（生产环境）一键切换 |
| **会话持久化** | SQLite持久化存储，重启后上下文无缝恢复 |

### 1.3 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        用户层                                     │
│            (Web Dashboard / API / CLI)                          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Gateway                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ 会话管理  │  │ 工具注册  │  │ 策略引擎  │  │  审计日志  │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              告警关联推理引擎（AlertCorrelator）          │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      智能决策层                                   │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │ Orchestrator│  │ Diagnostic │  │   Risk    │                │
│  │  编排Agent  │  │  诊断Agent  │  │ 风险Agent  │                │
│  └────────────┘  └────────────┘  └────────────┘                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
│  │ SQLAnalyzer│  │ Inspector  │  │  Reporter  │                │
│  │ SQL分析Agent│  │  巡检Agent  │  │ 报告Agent  │                │
│  └────────────┘  └────────────┘  └────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       知识层                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ 告警规则库│  │  SOP库   │  │  案例库   │                      │
│  └──────────┘  └──────────┘  └──────────┘                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      工具执行层                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ 查询工具  │  │ 分析工具  │  │ 行动工具  │  │高风险工具│       │
│  │ (L1只读) │  │ (L2诊断) │  │ (L3低风险)│  │ (L4-L5) │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       API层                                      │
│  ┌─────────────────────┐    ┌─────────────────────┐           │
│  │   Mock Javis-DB-Agent API   │    │   Real Javis-DB-Agent API    │           │
│  │   (本地开发测试)     │ ←→ │   (生产环境)         │           │
│  └─────────────────────┘    └─────────────────────┘           │
│  - 12个REST接口              - 14个Router模块                  │
│  - QPS限流模拟               - API Key认证                     │
│  - 错误注入                  - OAuth2认证                       │
│  - 50+模拟告警              - httpx重试机制                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       LLM层                                      │
│              Ollama (本地推理, OpenAI兼容API)                     │
│  - glm4:latest (5.4GB, 默认)                                    │
│  - qwen3:30b-a3b (18.6GB, 高质量)                              │
│  - /api/chat 流式/同步接口                                       │
│  - /api/generate 非chat接口                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 项目结构

```
Javis-DB-Agent/
├── src/                          # 核心源代码
│   ├── agents/                   # Agent实现（6个Agent）
│   │   ├── base.py              # Agent基类（策略检查、工具调用、审计）
│   │   ├── orchestrator.py      # 编排Agent（意图识别、任务分解）
│   │   ├── diagnostic.py        # 诊断Agent（根因分析、告警链推理）
│   │   ├── risk.py              # 风险Agent（L1-L5分级评估）
│   │   ├── sql_analyzer.py      # SQL分析Agent（慢SQL、执行计划）
│   │   ├── inspector.py         # 巡检Agent（健康评分、风险项）
│   │   └── reporter.py          # 报告Agent（RCA/巡检报告/摘要）
│   ├── gateway/                 # Gateway核心
│   │   ├── alert_correlator.py  # 告警关联推理引擎（603行）
│   │   ├── policy_engine.py    # 策略引擎（角色权限、审批流）
│   │   ├── audit.py             # 审计日志（JSONL持久化）
│   │   ├── session.py           # 会话管理（TTL）
│   │   ├── tool_registry.py     # 工具注册中心
│   │   └── persistent_session.py # 会话持久化（SQLite, 605行）
│   ├── tools/                   # 工具集（23个工具）
│   │   ├── base.py             # 工具基类
│   │   ├── query_tools.py      # 查询工具（14个, L1只读）
│   │   ├── analysis_tools.py   # 分析工具（3个, L2诊断）
│   │   ├── action_tools.py      # 行动工具（4个, L3-L4）
│   │   ├── additional_query_tools.py  # 补充查询工具（4个）
│   │   └── high_risk_tools.py  # 高风险工具（2个, L5）
│   ├── mock_api/                # Mock API客户端
│   │   ├── javis_client.py    # MockZCloudClient
│   │   ├── error_injector.py   # 错误注入器（超时/限流/级联故障）
│   │   └── qps_limiter.py      # QPS限流器
│   ├── real_api/                # 真实API客户端
│   │   ├── client.py           # ZCloudRealClient（httpx封装）
│   │   ├── auth.py             # 认证模块（API Key + OAuth2）
│   │   ├── config.py           # 配置读取
│   │   └── routers/            # API路由（10个模块）
│   │       ├── instances.py    # 实例管理
│   │       ├── alerts.py       # 告警管理
│   │       ├── sessions.py     # 会话管理
│   │       ├── locks.py        # 锁管理
│   │       ├── sqls.py         # SQL监控
│   │       ├── replication.py  # 复制状态
│   │       ├── parameters.py   # 参数管理
│   │       ├── capacity.py     # 容量管理
│   │       ├── inspection.py   # 巡检管理
│   │       └── workorders.py   # 工单管理
│   ├── api/                     # FastAPI路由
│   │   ├── routes.py           # 核心API路由（7个端点）
│   │   ├── dashboard.py        # Dashboard路由（模式切换）
│   │   └── schemas.py          # Pydantic请求/响应模型
│   ├── knowledge/              # 知识库模块
│   ├── llm/                    # LLM交互
│   │   └── ollama_client.py    # Ollama客户端封装
│   ├── config.py              # 配置管理（Pydantic Settings）
│   └── main.py                # 应用入口（FastAPI + Lifespan）
│
├── mock_javis_api/            # Mock API Server
│   ├── server.py              # FastAPI应用 + QPS中间件
│   ├── models.py              # 数据模型
│   ├── models_enhanced.py     # 增强数据模型
│   └── routers/               # Mock路由（10个）
│
├── templates/                  # Web Dashboard
│   └── dashboard.html         # 管理界面
│
├── scripts/                    # 工具脚本
│   ├── switch_api_mode.py      # API模式切换（mock↔real）
│   ├── init_db.py             # 初始化数据库
│   ├── load_knowledge.py      # 加载知识库
│   └── verify_ollama.py       # Ollama连接验证
│
├── configs/                    # 配置文件
│   ├── config.yaml            # 主配置（API、LLM、知识库）
│   ├── tools.yaml             # 工具定义配置
│   └── prompts.yaml           # Prompt模板配置
│
├── knowledge/                  # 知识内容
│   ├── alert_rules.yaml       # 告警规则（15条）
│   ├── sop/                   # SOP库（8个）
│   │   ├── HA切换处理.md
│   │   ├── 主从延迟排查.md
│   │   ├── 主从延迟诊断.md
│   │   ├── 锁等待排查.md
│   │   ├── 慢SQL分析.md
│   │   ├── 容量不足处理.md
│   │   ├── 巡检标准流程.md
│   │   ├── 性能瓶颈排查.md
│   │   ├── 数据库高负载排查.md
│   │   └── 连接数打满处理.md
│   └── cases/                 # 案例库（3个）
│       ├── 2026-01-15-锁等待故障.md
│       ├── 2026-02-20-慢SQL风暴.md
│       └── 2026-03-10-主从延迟.md
│
├── tests/                      # 测试套件（~419个测试）
│   ├── unit/                  # 单元测试
│   ├── integration/           # 集成测试
│   ├── mock/                  # Mock API测试
│   ├── mysql/                 # MySQL特定测试
│   ├── ollama/                # Ollama推理测试
│   ├── round3/                # Round 3测试（告警关联/持久化）
│   ├── round4/                # Round 4测试（端到端/性能）
│   └── round9/                # Round 9测试（Real API/Dashboard）
│
├── docs/                       # 文档
│   ├── architecture.md        # 架构设计文档
│   ├── requirements.md        # 需求文档
│   ├── tech-spec.md           # 技术方案
│   ├── javis-db-api-research.md # Javis-DB-Agent API研究
│   ├── javis-db-auth-design.md  # 认证设计
│   ├── round3-execution-report.md
│   ├── round4-performance-report.md
│   └── round9-execution-report.md
│
├── data/                       # 运行时数据
│   ├── javis_db_agent.db        # SQLite会话持久化
│   ├── audit.db               # SQLite审计日志
│   └── audit.jsonl            # JSONL审计日志
│
├── requirements.txt            # Python依赖
├── README.md                   # 项目主文档
├── PROJECT_SUMMARY.md          # 项目整体总结
└── CHANGELOG.md               # 变更日志
```

---

## 二、功能模块详细说明

### 2.1 Agent模块（智能决策层）

#### 2.1.1 OrchestratorAgent（编排Agent）

**文件位置**: `src/agents/orchestrator.py`

**核心职责**: 作为统一入口，解析用户目标并协调专业Agent完成任务。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **意图识别** | 自动识别用户意图类型（diagnose/sql_analyze/inspect/report/risk_assess/general） |
| **Agent选择** | 根据意图自动选择合适的专业Agent组合 |
| **任务分解** | 将复杂任务分解为多个子任务，构建执行计划 |
| **结果聚合** | 汇总多Agent结果，生成统一回复 |
| **对话处理** | `handle_chat()` 处理自然语言对话 |
| **诊断处理** | `handle_diagnose()` 协调诊断+风险评估联合处理 |

**支持的子Agent**:
- `diagnostic`: 诊断Agent（告警根因分析）
- `risk`: 风险Agent（风险分级评估）
- `sql_analyzer`: SQL分析Agent（SQL性能分析）
- `inspector`: 巡检Agent（健康检查）
- `reporter`: 报告Agent（报告生成）

#### 2.1.2 DiagnosticAgent（诊断Agent）

**文件位置**: `src/agents/diagnostic.py`

**核心职责**: 接收告警/故障信息，进行根因分析和告警关联推理。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **告警诊断** | `diagnose_alert(alert_id)` 诊断指定告警，自动查找关联告警并构建诊断链 |
| **告警链诊断** | `diagnose_alert_chain(alert_ids)` 多个告警联合诊断 |
| **实例诊断** | `diagnose_instance(instance_id)` 诊断指定实例健康状态 |
| **告警关联推理** | 调用 `AlertCorrelator` 查找A→B→C告警链 |
| **证据收集** | 调用查询工具获取诊断数据（实例状态、会话、锁、SQL等） |
| **结果格式化** | `DiagnosticResultFormatter` 输出结构化诊断报告 |

**输出格式**:
- `root_cause`: 根本原因描述
- `confidence`: 置信度（0.0-1.0）
- `evidence`: 证据列表
- `next_steps`: 下一步排查步骤
- `severity`: 严重程度（critical/high/medium/low）
- `alert_chain`: 告警关联链

#### 2.1.3 RiskAgent（风险评估Agent）

**文件位置**: `src/agents/risk.py`

**核心职责**: 评估操作/故障的风险级别（L1-L5），判断是否可自动处置。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **风险分级** | L1-L5五级风险评估（只读→诊断→低风险→中风险→高风险） |
| **影响评估** | `analyze_impact()` 分析操作影响范围（session/instance/database/all） |
| **自动处置判断** | L3及以下可自动处置，L4需审批，L5需双人审批 |
| **风险关键词匹配** | 从诊断结果推断风险级别 |

**风险级别定义**:

| 级别 | 名称 | 说明 | 审批要求 |
|------|------|------|----------|
| L1 | 只读分析 | 查看数据、分析问题 | 无需审批 |
| L2 | 自动诊断 | 自动诊断、根因分析 | 无需审批 |
| L3 | 低风险执行 | 低风险操作、日志记录 | 仅记录 |
| L4 | 中风险执行 | 中等风险操作 | 单签审批 |
| L5 | 高风险执行 | 高风险、破坏性操作 | 双人审批 |

#### 2.1.4 SQLAnalyzerAgent（SQL分析Agent）

**文件位置**: `src/agents/sql_analyzer.py`

**核心职责**: 分析SQL执行情况，提供优化建议。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **SQL分析** | `analyze_sql(sql)` 分析指定SQL语句 |
| **会话SQL分析** | `analyze_session(session_id)` 分析指定会话的SQL |
| **执行计划解读** | 识别全表扫描、索引缺失等问题 |
| **锁阻塞分析** | 分析锁等待与阻塞链 |
| **优化建议** | 索引建议、SQL改写、参数调整建议 |
| **SQL指纹提取** | 归一化SQL模板，用于模式识别 |

**分析维度**:
- 执行频率与资源消耗
- 执行计划分析（全表扫描、索引缺失等）
- 锁等待与阻塞链
- 性能趋势（历史对比）
- 优化建议

#### 2.1.5 InspectorAgent（巡检Agent）

**文件位置**: `src/agents/inspector.py`

**核心职责**: 执行数据库健康检查，输出健康评分和风险项。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **实例巡检** | `inspect_instance(instance_id)` 巡检指定实例 |
| **全面巡检** | `full_inspection(instance_ids)` 批量巡检多个实例 |
| **健康评分** | 0-100分综合评分（excellent/good/fair/poor/critical） |

**巡检维度**:

| 维度 | 检查项 |
|------|--------|
| 实例状态 | CPU/内存/IO/连接数 |
| 主从复制 | 延迟、断开、HA状态 |
| 锁与会话 | 长时间锁、阻塞链 |
| 慢查询 | Top SQL统计 |
| 存储 | 表空间使用率 |
| 参数配置 | 配置合规性 |
| 安全 | 权限与审计 |

**健康评分标准**:
- 90-100: 优秀（excellent）
- 75-89: 良好（good）
- 60-74: 一般（fair）
- 40-59: 较差（poor）
- <40: 危险（critical）

#### 2.1.6 ReporterAgent（报告Agent）

**文件位置**: `src/agents/reporter.py`

**核心职责**: 生成结构化运维报告（RCA/巡检报告/摘要）。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **RCA报告** | `generate_rca(incident_id)` 生成根因分析报告（故障复盘） |
| **巡检报告** | `generate_inspection_report(instance_id)` 生成巡检报告 |
| **摘要报告** | `generate_summary(data)` 生成执行摘要（高层汇报） |

**报告结构**:
- 执行摘要（一段话概括）
- 背景/问题描述
- 分析过程
- 结论与建议
- 附录（详细数据）

---

### 2.2 Gateway模块（核心基础设施）

#### 2.2.1 AlertCorrelator（告警关联推理引擎）

**文件位置**: `src/gateway/alert_correlator.py`（603行）

**核心职责**: 实现A告警→B告警→C告警的链式诊断逻辑。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **因果规则匹配** | 15+因果规则（如CPU_HIGH→SLOW_QUERY→RESPONSE_SLOW） |
| **时间窗口关联** | 在时间窗口内查找关联告警（默认600秒） |
| **实例级联分析** | 同一实例内的告警关联 |
| **角色标注** | 标注告警在链中的角色（根因/症状/促成因素） |
| **置信度计算** | 多维度计算告警关联置信度 |
| **诊断路径生成** | 输出有序的告警诊断路径 |

**内置因果规则示例**:

| 告警类型 | 导致因素 | 引发结果 |
|----------|----------|----------|
| CPU_HIGH | - | SLOW_QUERY, RESPONSE_SLOW, SESSION_BLOCK |
| MEMORY_USAGE_HIGH | - | SLOW_QUERY, DB_HIGH_LOAD, OOM_KILL |
| DISK_USAGE_HIGH | - | WRITE_SLOW, BACKUP_FAILED |
| SLOW_QUERY | CPU_HIGH, DISK_IO_HIGH | RESPONSE_SLOW, USER_COMPLAIN |
| LOCK_WAIT | BIG_TRANSACTION | SESSION_BLOCK, RESPONSE_SLOW |
| CONNECTION_FULL | SESSION_LEAK | SERVICE_UNAVAILABLE |

**输出数据模型**:
- `AlertNode`: 告警节点（含角色标注和置信度）
- `CorrelationLink`: 关联链路（因果/时间/实例类型）
- `CorrelationResult`: 关联分析结果（诊断路径、根因、置信度）

#### 2.2.2 PolicyEngine（策略引擎）

**文件位置**: `src/gateway/policy_engine.py`

**核心职责**: 基于角色的访问控制（RBAC），执行风险级别策略检查。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **角色权限映射** | VIEWER/ANALYST/ADVISOR/OPERATOR/ADMIN五种角色 |
| **风险级别检查** | 根据角色和操作风险级别判断是否允许 |
| **审批流程控制** | L4单签审批，L5双人审批 |
| **自定义规则扩展** | 支持添加自定义策略规则 |

**角色权限矩阵**:

| 角色 | L1只读 | L2诊断 | L3低风险 | L4中风险 | L5高风险 |
|------|--------|--------|---------|---------|---------|
| VIEWER | ✅ | ❌ | ❌ | ❌ | ❌ |
| ANALYST | ✅ | ✅ | ❌ | ❌ | ❌ |
| ADVISOR | ✅ | ✅ | ✅ | ❌ | ❌ |
| OPERATOR | ✅ | ✅ | ✅ | ✅ | ❌ |
| ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ |

#### 2.2.3 AuditLogger（审计日志）

**文件位置**: `src/gateway/audit.py`

**核心职责**: 记录所有操作行为的审计日志，支持查询和导出。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **操作记录** | 记录Agent调用、工具调用、策略检查结果 |
| **持久化存储** | JSONL文件持久化（`data/audit.jsonl`） |
| **多维度查询** | 按用户/会话/工具/时间范围查询 |
| **会话审计** | `get_session_audit()` 获取会话的所有审计日志 |
| **用户审计** | `get_user_audit()` 获取用户最近N小时的审计日志 |
| **日志导出** | `export()` 导出指定时间范围的日志到文件 |

**审计动作类型**:
- `SESSION_CREATE` / `SESSION_CLOSE`
- `AGENT_INVOKE`
- `TOOL_CALL` / `TOOL_RESULT`
- `POLICY_PASS` / `POLICY_DENY`
- `APPROVAL_REQUEST` / `APPROVAL_GRANT` / `APPROVAL_REJECT`
- `ERROR`

#### 2.2.4 PersistentSessionManager（会话持久化）

**文件位置**: `src/gateway/persistent_session.py`（605行）

**核心职责**: 管理会话生命周期，支持SQLite持久化和TTL过期管理。

**能力说明**:

| 能力 | 说明 |
|------|------|
| **会话创建/获取** | `create_session()` / `get_session()` |
| **消息记录** | 记录用户消息和Agent回复 |
| **上下文存储** | 运维上下文（instance_id、alert_id等）持久化 |
| **TTL管理** | 会话过期时间自动管理 |
| **重启恢复** | 重启后从SQLite恢复会话历史 |
| **消息历史** | `get_history(limit)` 获取最近N条消息 |

**存储结构**: SQLite（`data/javis_db_agent.db`）

#### 2.2.5 ToolRegistry（工具注册中心）

**文件位置**: `src/gateway/tool_registry.py`

**核心职责**: 统一管理所有工具的注册、查询和元数据。

**能力说明**:
- 工具注册与取消注册
- 按名称/类别/风险级别查询
- 工具统计（总数、分类统计）
- 工具定义导出（definition_dict）

---

### 2.3 工具模块（工具执行层）

> 所有工具均继承自 `BaseTool`，支持参数校验、前置检查、后置检查。

#### 2.3.1 查询工具（Query Tools，风险级别 L1）

| 工具名称 | 功能 | 输入参数 | 输出数据 |
|----------|------|----------|----------|
| `query_instance_status` | 查询实例状态 | instance_id, metrics | CPU/内存/IO/连接数/运行时间 |
| `query_session` | 查询会话信息 | instance_id, limit, filter | SID/SERIAL#/用户名/状态/SQL |
| `query_lock` | 查询锁等待信息 | instance_id, include_blocker | 阻塞链/Wait SID/Blocker SID |
| `query_slow_sql` | 查询慢SQL | instance_id, limit, order_by | SQL文本/执行时间/磁盘读/行数 |
| `query_replication` | 查询主从复制状态 | instance_id | 主从角色/延迟秒数/HA状态 |
| `query_alert_detail` | 查询告警详情 | alert_id | 告警类型/级别/实例/指标值/阈值 |
| `query_sql_plan` | 查询SQL执行计划 | sql_id, instance_id | 操作/对象名/代价/基数 |
| `query_disk_usage` | 查询磁盘使用率 | instance_id | 磁盘总量/已用/使用率/表空间列表 |
| `query_parameters` | 查询数据库参数 | instance_id, filter | 参数名/当前值/默认值/是否修改 |
| `query_top_sql` | 查询Top SQL | instance_id, sort_by, limit | SQL ID/文本/排序指标值 |
| `query_ha_status` | 查询HA/主备状态 | instance_id | HA启用/角色/最后切换时间/原因 |
| `get_inspection_result` | 获取巡检结果 | task_id | 健康评分/问题列表/巡检状态 |
| `query_config_deviation` | 查询配置偏差 | instance_id | 参数/当前值/标准值/偏差类型 |
| `query_related_alerts` | **查询关联告警** | alert_id, instance_id, time_range_seconds | 关联告警列表/诊断路径/根因 |
| `query_tablespace` | 查询表空间详情 | instance_id, tablespace_name | 表空间名/状态/总容量/使用率 |
| `query_processlist` | 查询进程列表 | instance_id, limit, filter | PID/用户/主机/命令/时间/SQL |
| `query_audit_log` | 查询审计日志 | instance_id, start_time, end_time, limit, operation_type | 审计记录/操作用户/对象/状态 |
| `query_backup_status` | 查询备份状态 | instance_id, backup_type | 备份ID/类型/状态/大小/位置 |

#### 2.3.2 分析工具（Analysis Tools，风险级别 L2）

| 工具名称 | 功能 | 输入参数 | 输出数据 |
|----------|------|----------|----------|
| `analyze_impact` | 分析影响范围 | instance_id, scope | 影响会话数/连接数/用户数/业务影响 |
| `analyze_sql_pattern` | 分析SQL模式 | sql_text, pattern_type | 语句类型/表数量/JOIN检测/复杂度 |
| `diagnose_alert` | 告警自动诊断 | alert_type, severity | 根因/置信度/检查步骤/解决方案 |
| `analyze_explain_plan` | SQL执行计划分析 | sql_text, instance_id, format | 执行计划/总代价/问题列表/优化建议 |

#### 2.3.3 行动工具（Action Tools，风险级别 L3-L4）

| 工具名称 | 功能 | 风险级别 | 输入参数 | 输出数据 |
|----------|------|----------|----------|----------|
| `trigger_inspection` | 触发巡检 | L3 | instance_id, inspection_type | 任务ID/状态/开始时间 |
| `send_notification` | 发送通知 | L3 | channel, recipient, title, content | 通知ID/渠道/状态/发送时间 |
| `refresh_sampling` | 刷新采样数据 | L3 | instance_id, sampling_type | 刷新状态/时间 |
| `create_work_order` | 创建工单 | L4 | title, description, priority, instance_id | 工单ID/状态/创建时间 |
| `kill_session` | **强制终止会话** | L5 | instance_id, session_id, reason, confirm | 任务ID/会话ID/状态/影响连接数 |

#### 2.3.4 工具执行流程

```
用户请求 → Agent.think() → Agent.call_tool()
           ↓
     ToolRegistry.get_tool()
           ↓
     BaseTool.validate_params()  ← 参数校验
           ↓
     PolicyEngine.check()  ← 策略检查（L4/L5审批）
           ↓
     BaseTool.pre_execute()  ← 前置检查
           ↓
     BaseTool.execute()  ← 实际执行
           ↓
     BaseTool.post_execute()  ← 后置检查
           ↓
     AuditLogger.log()  ← 审计记录
           ↓
     返回 ToolResult
```

---

### 2.4 API模块（外部接口层）

#### 2.4.1 FastAPI路由（src/api/routes.py）

| 端点 | 方法 | 功能 | 请求模型 |
|------|------|------|----------|
| `/api/v1/chat` | POST | 对话交互 | `ChatRequest` |
| `/api/v1/diagnose` | POST | 告警诊断 | `DiagnoseRequest` |
| `/api/v1/analyze/sql` | POST | SQL分析 | `SQLAnalyzeRequest` |
| `/api/v1/inspect` | POST | 执行巡检 | `InspectRequest` |
| `/api/v1/report` | POST | 生成报告 | `ReportRequest` |
| `/api/v1/tools` | GET | 列出工具 | category参数 |
| `/api/v1/tools/{tool_name}` | GET | 获取工具详情 | - |
| `/api/v1/health` | GET | 健康检查 | - |

#### 2.4.2 Dashboard路由（src/api/dashboard.py）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/dashboard/` | GET | Dashboard主页（HTML） |
| `/dashboard/status` | GET | 获取当前API模式状态 |
| `/dashboard/switch` | POST | 切换API模式（mock↔real） |
| `/dashboard/health-check` | GET | 健康检查 |

#### 2.4.3 Mock API Server（mock_javis_api/server.py）

**端口**: 18080

| 路由前缀 | 接口数量 | 功能 |
|----------|----------|------|
| `/api/v1/instances` | 3 | 实例管理（列表/详情/指标） |
| `/api/v1/alerts` | 4 | 告警管理（列表/详情/确认/解决） |
| `/api/v1/sessions` | 3 | 会话管理 |
| `/api/v1/locks` | 2 | 锁管理 |
| `/api/v1/sqls` | 3 | SQL监控（慢SQL/执行计划/Top SQL） |
| `/api/v1/replication` | 2 | 复制状态 |
| `/api/v1/parameters` | 3 | 参数管理 |
| `/api/v1/capacity` | 5 | 容量管理（表空间/备份/审计日志等） |
| `/api/v1/inspection` | 3 | 巡检管理 |
| `/api/v1/workorders` | 3 | 工单管理 |

**增强特性**:
- QPS限流中间件（查询100QPS，写入20QPS，批量5QPS）
- 50+模拟告警池（按告警代码/实例分组）
- 错误注入器（超时/限流/级联故障/数据不一致）

#### 2.4.4 Real API Client（src/real_api/client.py）

| 功能 | 方法 |
|------|------|
| 实例管理 | `get_instance()`, `list_instances()`, `get_instance_metrics()` |
| 告警管理 | `get_alerts()`, `get_alert_detail()`, `acknowledge_alert()`, `resolve_alert()` |
| 会话管理 | `get_sessions()`, `get_session_detail()` |
| 锁管理 | `get_locks()` |
| SQL监控 | `get_slow_sql()`, `get_sql_plan()` |
| 复制状态 | `get_replication_status()` |
| 参数管理 | `get_parameters()`, `update_parameter()` |
| 容量管理 | `get_tablespaces()`, `get_backup_status()`, `get_audit_logs()` |
| 巡检管理 | `get_inspection_results()`, `trigger_inspection()` |
| 工单管理 | `list_workorders()`, `get_workorder_detail()` |

**认证方式**:
- **API Key**: `X-API-Key` 或 `Authorization: ApiKey` 头部
- **OAuth2**: `client_credentials` / `refresh_token` 流程，Bearer Token

**容错机制**:
- 429限流自动重试（根据 Retry-After 等待）
- 401认证失败自动刷新Token并重试
- 网络错误指数退避重试（最多3次）

---

### 2.5 知识模块（知识层）

#### 2.5.1 告警规则库（knowledge/alert_rules.yaml）

**15条告警规则**:

| 告警代码 | 名称 | 严重度 | 风险级别 |
|----------|------|--------|----------|
| LOCK_WAIT_TIMEOUT | 锁等待超时 | warning | L3 |
| DEADLOCK_DETECTED | 死锁检测 | critical | L4 |
| SLOW_QUERY_DETECTED | 慢SQL告警 | info | L2 |
| CPU_HIGH | CPU使用率过高 | warning | L3 |
| MEMORY_HIGH | 内存使用率过高 | warning | L3 |
| DISK_FULL | 磁盘空间不足 | critical | L4 |
| CONNECTION_HIGH | 连接数过高 | warning | L3 |
| CONNECTION_POOL_EXHAUSTED | 连接池耗尽 | critical | L4 |
| REPLICATION_LAG | 主从延迟告警 | warning | L3 |
| REPLICATION_BROKEN | 复制中断 | critical | L4 |
| INSTANCE_DOWN | 实例不可用 | critical | L5 |
| INSTANCE_SLOW | 实例响应慢 | warning | L3 |
| BACKUP_FAILED | 备份失败 | warning | L3 |
| FAILED_LOGIN | 登录失败 | warning | L3 |
| PRIVILEGE_ESCALATION | 权限提升 | critical | L4 |

每条规则包含: `症状` → `可能原因` → `排查步骤` → `解决方案`

#### 2.5.2 SOP库（knowledge/sop/）

| SOP名称 | 适用场景 |
|---------|----------|
| HA切换处理.md | 主备切换时的标准化处理流程 |
| 主从延迟排查.md | 主从复制延迟的排查步骤 |
| 主从延迟诊断.md | 主从延迟的诊断分析 |
| 锁等待排查.md | 锁等待问题的排查流程 |
| 慢SQL分析.md | 慢SQL的标准分析流程 |
| 容量不足处理.md | 存储容量不足的处理方案 |
| 巡检标准流程.md | 日常巡检的标准步骤 |
| 性能瓶颈排查.md | 性能瓶颈的系统化排查 |
| 数据库高负载排查.md | 高负载状态的排查指南 |
| 连接数打满处理.md | 连接数耗尽的处理方案 |

#### 2.5.3 案例库（knowledge/cases/）

| 案例文件 | 事件日期 | 事件类型 |
|----------|----------|----------|
| 2026-01-15-锁等待故障.md | 2026-01-15 | 锁等待故障 |
| 2026-02-20-慢SQL风暴.md | 2026-02-20 | 慢SQL风暴 |
| 2026-03-10-主从延迟.md | 2026-03-10 | 主从延迟 |

---

## 三、API能力列表

### 3.1 内部API（FastAPI路由）

| 类别 | 端点 | 说明 |
|------|------|------|
| 对话 | `POST /api/v1/chat` | 自然语言对话，统一入口 |
| 诊断 | `POST /api/v1/diagnose` | 告警诊断 |
| SQL分析 | `POST /api/v1/analyze/sql` | SQL语句分析 |
| 巡检 | `POST /api/v1/inspect` | 执行健康巡检 |
| 报告 | `POST /api/v1/report` | 生成RCA/巡检报告 |
| 工具 | `GET /api/v1/tools` | 列出可用工具 |
| 工具 | `GET /api/v1/tools/{name}` | 获取工具详情 |
| 健康 | `GET /api/v1/health` | 健康检查 |
| Dashboard | `GET /dashboard/` | Web管理界面 |
| Dashboard | `GET /dashboard/status` | 获取模式状态 |
| Dashboard | `POST /dashboard/switch` | 切换API模式 |
| Dashboard | `GET /dashboard/health-check` | 健康检查 |

### 3.2 Mock API Server接口（端口18080）

| 类别 | 接口数 | 主要端点 |
|------|--------|----------|
| 实例管理 | 3 | `GET /api/v1/instances`, `GET /api/v1/instances/{id}`, `GET /api/v1/instances/{id}/metrics` |
| 告警管理 | 4 | `GET /api/v1/alerts`, `GET /api/v1/alerts/{id}`, `POST /api/v1/alerts/{id}/acknowledge`, `POST /api/v1/alerts/{id}/resolve` |
| 会话管理 | 3 | `GET /api/v1/sessions`, `GET /api/v1/sessions/{id}`, `DELETE /api/v1/sessions/{id}` |
| 锁管理 | 2 | `GET /api/v1/locks`, `GET /api/v1/locks/detail` |
| SQL监控 | 3 | `GET /api/v1/sqls/slow`, `GET /api/v1/sqls/top`, `GET /api/v1/sqls/plan/{id}` |
| 复制状态 | 2 | `GET /api/v1/replication`, `GET /api/v1/replication/detail` |
| 参数管理 | 3 | `GET /api/v1/parameters`, `GET /api/v1/parameters/{name}`, `PUT /api/v1/parameters/{name}` |
| 容量管理 | 5 | `GET /api/v1/capacity/tablespaces`, `GET /api/v1/capacity/backups`, `GET /api/v1/capacity/audit-logs`, `GET /api/v1/capacity/disk`, `GET /api/v1/capacity/processlist` |
| 巡检管理 | 3 | `GET /api/v1/inspection`, `GET /api/v1/inspection/{id}`, `POST /api/v1/inspection/trigger` |
| 工单管理 | 3 | `GET /api/v1/workorders`, `GET /api/v1/workorders/{id}`, `POST /api/v1/workorders` |

### 3.3 Real API Client接口（httpx封装）

| 类别 | 方法数 | 主要接口 |
|------|--------|----------|
| 实例管理 | 3 | `get_instance()`, `list_instances()`, `get_instance_metrics()` |
| 告警管理 | 4 | `get_alerts()`, `get_alert_detail()`, `acknowledge_alert()`, `resolve_alert()` |
| 会话管理 | 2 | `get_sessions()`, `get_session_detail()` |
| 锁管理 | 1 | `get_locks()` |
| SQL监控 | 2 | `get_slow_sql()`, `get_sql_plan()` |
| 复制状态 | 1 | `get_replication_status()` |
| 参数管理 | 2 | `get_parameters()`, `update_parameter()` |
| 容量管理 | 3 | `get_tablespaces()`, `get_backup_status()`, `get_audit_logs()` |
| 巡检管理 | 2 | `get_inspection_results()`, `trigger_inspection()` |
| 工单管理 | 2 | `list_workorders()`, `get_workorder_detail()` |

---

## 四、Agent能力说明

### 4.1 Agent能力总览

| Agent | 名称 | 核心能力 | 工具调用 | 最大迭代 |
|--------|------|----------|----------|----------|
| Orchestrator | 编排Agent | 意图识别、任务分解、多Agent协调 | ❌（通过子Agent） | 5 |
| Diagnostic | 诊断Agent | 根因分析、告警链关联推理 | ✅ 7个查询工具 | 5 |
| Risk | 风险Agent | L1-L5风险分级、审批流控制 | ✅ 3个工具 | 5 |
| SQLAnalyzer | SQL分析Agent | SQL性能分析、执行计划解读 | ✅ 5个工具 | 5 |
| Inspector | 巡检Agent | 健康检查、健康评分、风险项识别 | ✅ 6个工具 | 5 |
| Reporter | 报告Agent | RCA/巡检报告/摘要生成 | ✅ 4个工具 | 5 |

### 4.2 Agent通信机制

```
用户输入
    ↓
OrchestratorAgent._recognize_intent()
    ↓
选择子Agent → _select_agents()
    ↓
构建执行计划 → _build_plan()
    ↓
依次执行Agent → _execute_plan()
    ↓
汇总结果 → _aggregate_results()
    ↓
返回AgentResponse
```

### 4.3 诊断链路示例

```
用户: "告警 ALT-001 是什么问题？"

OrchestratorAgent
    ↓ [识别意图: diagnose]
    选择: DiagnosticAgent + RiskAgent
    ↓
DiagnosticAgent.diagnose_alert("ALT-001")
    ├→ AlertCorrelator.correlate_alerts()
    │   查找关联告警 ALT-002, ALT-003
    │   构建诊断链: ALT-001 → ALT-002 → ALT-003
    │   根因: CPU_HIGH → SLOW_QUERY → RESPONSE_SLOW
    └→ LLM综合分析 → 根因结论
    ↓
RiskAgent.assess_risk()
    评估影响范围 → L3低风险
    ↓
聚合结果 → 返回诊断报告
```

---

## 五、工具能力列表

### 5.1 工具分类总览

| 类别 | 数量 | 风险级别 | 示例工具 |
|------|------|----------|----------|
| 查询工具 | 18 | L1（只读） | query_instance_status, query_session |
| 分析工具 | 4 | L2（诊断） | analyze_impact, analyze_sql_pattern |
| 行动工具 | 4 | L3-L4（中低风险） | trigger_inspection, create_work_order |
| 高风险工具 | 1 | L5（高风险） | kill_session |
| **合计** | **27** | - | - |

### 5.2 工具详细清单

#### L1 - 只读查询工具（18个）

| # | 工具名 | 功能描述 | 关键参数 |
|---|--------|----------|----------|
| 1 | `query_instance_status` | 查询实例CPU/内存/IO/连接数 | instance_id |
| 2 | `query_session` | 查询活跃会话及等待事件 | instance_id, limit |
| 3 | `query_lock` | 查询锁等待和阻塞链 | instance_id |
| 4 | `query_slow_sql` | 查询慢SQL统计 | instance_id, limit, order_by |
| 5 | `query_replication` | 查询主从复制状态和延迟 | instance_id |
| 6 | `query_alert_detail` | 查询指定告警详情 | alert_id |
| 7 | `query_sql_plan` | 获取SQL执行计划 | sql_id |
| 8 | `query_disk_usage` | 查询磁盘使用率 | instance_id |
| 9 | `query_parameters` | 查询数据库参数配置 | instance_id, filter |
| 10 | `query_top_sql` | 查询Top SQL（CPU/IO/逻辑读） | instance_id, sort_by |
| 11 | `query_ha_status` | 查询HA/主备切换状态 | instance_id |
| 12 | `get_inspection_result` | 获取巡检任务结果 | task_id |
| 13 | `query_config_deviation` | 查询配置与标准配置偏差 | instance_id |
| 14 | `query_related_alerts` | 查询关联告警（构建诊断链） | alert_id, time_range_seconds |
| 15 | `query_tablespace` | 查询表空间使用情况 | instance_id, tablespace_name |
| 16 | `query_processlist` | 查询数据库进程列表 | instance_id, limit |
| 17 | `query_audit_log` | 查询审计日志 | instance_id, operation_type |
| 18 | `query_backup_status` | 查询备份状态和历史 | instance_id, backup_type |

#### L2 - 诊断分析工具（4个）

| # | 工具名 | 功能描述 | 关键参数 |
|---|--------|----------|----------|
| 1 | `analyze_impact` | 分析操作影响范围 | instance_id, scope |
| 2 | `analyze_sql_pattern` | 分析SQL语句模式和特征 | sql_text, pattern_type |
| 3 | `diagnose_alert` | 匹配知识库规则进行告警诊断 | alert_type, severity |
| 4 | `analyze_explain_plan` | 分析SQL执行计划识别性能问题 | sql_text, instance_id |

#### L3 - 低风险行动工具（3个）

| # | 工具名 | 功能描述 | 关键参数 |
|---|--------|----------|----------|
| 1 | `trigger_inspection` | 触发健康巡检 | instance_id, inspection_type |
| 2 | `send_notification` | 发送通知（邮件/企微/飞书） | channel, recipient, title, content |
| 3 | `refresh_sampling` | 刷新性能采样数据 | instance_id, sampling_type |

#### L4 - 中风险行动工具（1个）

| # | 工具名 | 功能描述 | 关键参数 |
|---|--------|----------|----------|
| 1 | `create_work_order` | 创建运维工单 | title, description, priority |

#### L5 - 高风险工具（1个）

| # | 工具名 | 功能描述 | 关键参数 | 特殊要求 |
|---|--------|----------|----------|----------|
| 1 | `kill_session` | 强制终止数据库会话 | instance_id, session_id, reason, confirm | 必须confirm=true |

---

## 六、配置说明

### 6.1 主配置文件（configs/config.yaml）

```yaml
# 应用配置
app_name: Javis-DB-Agent
app_version: v1.0
debug: false

# API服务
api:
  host: 0.0.0.0
  port: 8000

# LLM - Ollama
ollama:
  base_url: http://localhost:11434
  model: glm4:latest           # 可切换 qwen3:30b-a3b
  timeout: 60

# Javis-DB-Agent API 模式切换
javis_api:
  base_url: http://localhost:18080
  timeout: 30
  use_mock: true               # ← 切换开关

# Javis-DB-Agent 真实API配置
javis_real_api:
  base_url: https://javis-db.example.com/api/v1
  auth_type: api_key           # 或 oauth2
  api_key: ""
  api_key_header: X-API-Key
  oauth_client_id: ""
  oauth_client_secret: ""
  max_retries: 3

# 数据库/存储
database:
  db_path: data/javis_db_agent.db
  audit_db_path: data/audit.db

# 向量数据库
chroma:
  db_path: data/chroma

# 安全策略
security:
  require_approval_l4: true     # L4需审批
  require_dual_approval_l5: true # L5需双人审批
```

### 6.2 API模式切换

**脚本**: `scripts/switch_api_mode.py`

```bash
# 查看当前模式
python scripts/switch_api_mode.py --status

# 切换到Mock模式
python scripts/switch_api_mode.py --mode mock

# 切换到真实API模式（API Key）
python scripts/switch_api_mode.py --mode real \
  --base-url https://javis-db.example.com/api/v1 \
  --api-key YOUR_API_KEY

# 切换到真实API模式（OAuth2）
python scripts/switch_api_mode.py --mode real \
  --auth-type oauth2 \
  --oauth-client-id YOUR_CLIENT_ID \
  --oauth-client-secret YOUR_CLIENT_SECRET
```

### 6.3 Prompt模板配置（configs/prompts.yaml）

```yaml
system_prompts:
  orchestrator: 数据库运维智能助手统一入口
  diagnostic: 数据库运维诊断专家
  risk: 风险评估专家
  sql_analyzer: SQL分析专家
  inspector: 巡检专家
  reporter: 报告生成专家
```

---

## 七、使用场景

### 场景1：告警诊断

**触发方式**: 用户发送告警ID或告警描述

**处理流程**:
1. Orchestrator识别意图为 `diagnose`
2. DiagnosticAgent接收告警，调用AlertCorrelator查找关联告警
3. 构建告警链：A告警→B告警→C告警
4. 调用查询工具收集诊断数据
5. RiskAgent评估风险级别
6. ReporterAgent生成诊断报告

**输出**: 根因分析 + 告警关联链 + 置信度 + 处置建议

---

### 场景2：慢SQL分析

**触发方式**: 用户提交SQL或指定sql_id

**处理流程**:
1. Orchestrator识别意图为 `sql_analyze`
2. SQLAnalyzerAgent调用 `query_slow_sql` 获取慢SQL
3. 调用 `analyze_explain_plan` 分析执行计划
4. 识别全表扫描、索引缺失等问题
5. 生成优化建议（索引、改写、参数调整）

**输出**: SQL指纹 + 执行计划分析 + 优化建议 + 风险级别

---

### 场景3：健康巡检

**触发方式**: 用户请求巡检指定实例

**处理流程**:
1. Orchestrator识别意图为 `inspect`
2. InspectorAgent依次调用多个查询工具获取数据
3. 汇总CPU/内存/IO/连接数/复制状态/慢SQL等数据
4. 生成健康评分（0-100）
5. 识别风险项并按严重度排序

**输出**: 健康评分 + 状态等级 + 问题列表 + 优先修复项

---

### 场景4：报告生成

**触发方式**: 用户请求生成RCA报告或巡检报告

**处理流程**:
1. ReporterAgent接收报告类型和实例ID
2. 调用 `get_inspection_result` 或 `get_knowledge_case` 获取数据
3. LLM生成结构化报告

**输出**: 执行摘要 + 背景 + 分析过程 + 结论与建议 + 附录

---

### 场景5：会话终止（高风险）

**触发方式**: 用户请求终止异常会话

**处理流程**:
1. RiskAgent评估风险为L5（高风险）
2. PolicyEngine检查用户角色是否为ADMIN
3. 若非ADMIN，返回权限不足
4. 若为ADMIN，检查confirm参数是否为true
5. 调用 `kill_session` 工具终止会话
6. 审计日志记录完整操作

**安全控制**: L5双人审批 + confirm强制确认 + 完整审计

---

### 场景6：模式切换（运维）

**触发方式**: 运维人员在Dashboard中切换API模式

**处理流程**:
1. 用户在Dashboard点击"切换到真实API"
2. Dashboard调用 `/dashboard/switch` 接口
3. 脚本修改 `configs/config.yaml` 中 `javis_api.use_mock`
4. RealClient自动重置单例，重新加载配置
5. 系统切换至真实Javis API

**应用场景**: 开发测试用Mock，生产环境用Real

---

## 八、数据流总图

```
用户消息
    ↓
FastAPI /api/v1/chat
    ↓
OrchestratorAgent.process()
    ↓
意图识别 → Agent选择 → 计划构建
    ↓
子Agent.process()
    ↓
Agent.call_tool()
    ├→ ToolRegistry.get_tool()
    ├→ PolicyEngine.check()  ← 权限检查
    ├→ BaseTool.execute()
    │   ├→ MockZCloudClient （use_mock=true）
    │   └→ ZCloudRealClient （use_mock=false）
    └→ AuditLogger.log()
    ↓
AgentResponse
    ↓
返回用户
```

---

## 九、技术指标

| 指标 | 目标 | 实际 | 状态 |
|------|------|------|------|
| 平均响应时间 | < 30,000ms | 740ms | ✅ |
| P95响应时间 | < 30,000ms | 749ms | ✅ |
| 测试通过率 | ≥ 95% | 99% | ✅ |
| 工具总数 | - | 27个 | ✅ |
| Agent总数 | - | 6个 | ✅ |
| 告警规则数 | - | 15条 | ✅ |
| SOP文档数 | - | 10个 | ✅ |
| 案例数 | - | 3个 | ✅ |
| 总测试数 | - | ~419个 | ✅ |

---

## 十、依赖环境

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 运行环境 |
| Ollama | 最新 | 本地LLM推理 |
| FastAPI | - | Web框架 |
| httpx | - | HTTP客户端 |
| pydantic | - | 数据验证 |
| structlog | - | 结构化日志 |
| pytest | - | 测试框架 |
| uvicorn | - | ASGI服务器 |

---

*文档版本: v20260329_094422*
*项目版本: v1.0*
*生成时间: 2026-03-29 09:44*
