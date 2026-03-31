# Changelog

All notable changes to the Javis-DB-Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [v2.1] - 2026-03-31

### Added
- **YAML SOP Loader** (src/security/execution/yaml_sop_loader.py) - 从YAML加载SOP定义
- **Action→Tool Mapper** (src/security/execution/action_tool_mapper.py) - 22个action映射
- **DirectPostgresConnector** (src/db/direct_postgres_connector.py) - asyncpg直连PG
- **ApprovalGate** (src/gateway/approval.py) - 完整审批流（L4单签/L5双人）
- **Approval Routes** (src/api/approval_routes.py) - REST审批API
- **PGKillSessionTool** - L4高风险会话终止工具
- **3个SOP迁移** - slow_sql_diagnosis, lock_wait_diagnosis, session_cleanup

### Fixed
- **UNION注入Bug** - 删除死代码，改用count检测
- **is_read_only()** - 支持EXPLAIN/VACUUM/ANALYZE
- **白名单正则** - 支持schema.table和带引号标识符
- **pg_explain正则** - FORMAT子句可选
- **BUG-001** - sop_id/step_id字段映射
- **API注册** - approval_router未注册到main.py

### Changed
- **SOPExecutor** - 优先使用YAML SOP，硬编码fallback
- **postgres_tools** - 支持直连和API适配器两种模式

### Security
- **ApprovalGate** - 高风险操作(L4/L5)必须审批

## [V1.4] - 2026-03-30

### Added
- **BackupAgent** (Round 1) - 备份恢复专家，支持备份状态查询/恢复演练
  - 文件: `src/agents/backup_agent.py`
  - 工具: `check_backup_status`, `list_backup_history`, `trigger_backup`, `estimate_restore_time`
- **PerformanceAgent** (Round 1) - 性能分析专家，支持TopSQL提取/执行计划解读
  - 文件: `src/agents/performance_agent.py`
  - 工具: `extract_top_sql`, `explain_sql_plan`, `suggest_parameters`
- **Orchestrator集成** (Round 3) - BackupAgent/PerformanceAgent注册到编排器
  - 新增Intent: `ANALYZE_BACKUP`, `ANALYZE_PERFORMANCE`
  - 新增INTENT_EXAMPLES样本库（各15+条同义表达）
  - 新增语义工具选择分支（备份/性能关键词微调）

### Changed
- **认证鉴权** (Round 1) - 修复refresh_token BUG，启用OAuth2
  - `src/real_api/auth.py` - OAuth2Provider._sync_refresh() RFC6749规范完善

### Fixed
- **OAuth2Provider** (Round 1) - refresh_token grant_type规范完善，添加RFC6749注释

### Added (Tests)
- `tests/round16/test_auth.py` - 认证鉴权测试（OAuth2/API Key双模式）
- `tests/round16/test_backup_agent.py` - BackupAgent测试
- `tests/round16/test_performance_agent.py` - PerformanceAgent测试
- `tests/round16/test_integration_agents.py` - V1.4 BackupAgent/PerformanceAgent路由测试

## [v1.3.1] - 2026-03-30

### Added
- **跨平台安装脚本** (Round 1) - install.sh 支持 Ubuntu/CentOS/RHEL/macOS
  - 动态 Python 版本检测（不再硬编码 python3.11）
  - systemd 服务安装保护（macOS 分支不再调用 install_systemd）
- **Docker 支持** (Round 1) - Dockerfile + docker-compose.yml
- **systemd 服务** (Round 1) - javis-agent.service 开机自启
- **GitHub Actions** (Round 1) - 自动构建+测试+发布
- **Python 包构建** (Round 1) - pyproject.toml + Makefile
- **跨平台兼容性测试** (Round 3) - tests/round15/test_platform_compat.py
  - asyncio.run() 兼容性测试
  - .env 配置加载测试
  - Docker 健康检查端点测试

### Changed
- **asyncio 兼容性** (Round 2) - asyncio.run() 替换废弃的 get_event_loop()
- **多平台支持** (Round 2) - Dockerfile 支持 amd64/arm64
- **Makefile 测试目标** (Round 3) - `make test` 自动创建/使用 .venv

### Fixed
- **Python 3.9+ 兼容性** (Round 2) - 扫描并修复潜在兼容性问题

## [v1.3] - 2026-03-30

### Added
- **语义工具选择增强** (Round 3) - `_select_agents()` 基于语义的动态工具选择
  - 不只是硬编码 intent→agent mapping，而是理解用户意图后选择最合适的工具
  - 例如："MySQL 慢查询" → 不仅仅是 INSPECT intent，还要选择慢查询分析工具
- **端到端泛化测试** (Round 3) - 完整的泛化能力验证测试套件
  - 同义表达泛化：10种不同说法表达同一个意图
  - 上下文理解：多轮对话中的指代理解
  - 语义工具选择：不同场景下选择不同工具
  - 测试文件：`tests/round15/test_e2e_generalization.py` (31个测试用例)
- **LLM Fallback 完善** (Round 3) - 纯 LLM 语义匹配效果增强
  - Prompt 优化：让 LLM 能准确理解用户意图的语义
  - 新增明确的识别规则示例
  - "MySQL instances" → INSPECT 在 LLM 模式下正确工作

### Changed
- **意图样本库扩展** (Round 1) - 各意图现在有更丰富的同义表达示例
  - INTENT_EXAMPLES: 16个Intent × 6-13个同义表达
  - "MySQL instances" 已加入 INSPECT 示例
- **LLM 语义匹配 Prompt** (Round 1) - 增强为包含意图描述和识别规则
- **语义路由增强** (Round 2) - `_semantic_intent_recognize()` 余弦相似度匹配
  - 复用 EmbeddingService + Chroma 意图向量库
  - 阈值 0.75，超过直接返回
- **样本自演化闭环** (Round 2) - IntentExampleCollector 自动收集用户反馈
  - `auto_learn_from_feedback()` 防重复添加，长度过滤防注入
  - 持久化到 `data/intent_examples.json`
- **上下文融合** (Round 2) - `_build_conversation_history()` 融入最近3轮对话
- **语义工具选择增强** (Round 3) - `_select_agents()` 基于语义的动态工具选择
  - 不只是硬编码 intent→agent mapping，而是理解用户意图后选择最合适的工具
  - 例如："MySQL 慢查询" → 不仅仅是 INSPECT intent，还要选择慢查询分析工具
- **端到端泛化测试** (Round 3) - 完整的泛化能力验证测试套件
  - 同义表达泛化：10种不同说法表达同一个意图
  - 上下文理解：多轮对话中的指代理解
  - 语义工具选择：不同场景下选择不同工具
  - 测试文件：`tests/round15/test_e2e_generalization.py` (31个测试用例)
- **LLM Fallback 完善** (Round 3) - 纯 LLM 语义匹配效果增强
  - Prompt 优化：让 LLM 能准确理解用户意图的语义
  - 新增明确的识别规则示例
  - "MySQL instances" → INSPECT 在 LLM 模式下正确工作

## [v1.2] - 2026-03-30

### Added
- **Taxonomy API** (Round 17) - REST API + Service + Repository三层架构
- **KnowledgeBase增强** (Round 18) - 结构化改造，支持Entity/Resource/ObservationPoint模型
- **依赖传播引擎** (Round 19) - 资源依赖传播与根因分析
- **观察点元数据服务** (Round 20) - ObservationPointMetadataService
- **知识库自演化闭环** (Round 21) - LLM+可观测驱动知识库自演化
- **routes目录重构** - src/api/routes/ → knowledge_routes/（消除命名遮蔽）

### Fixed
- **路由遮蔽Bug** - src/api/routes/ 目录遮蔽 routes.py 模块，核心端点从未注册（v1.2.0发布时即存在）
- **routes遮蔽Bug** - 修复src/api/routes/与knowledge_routes/命名冲突
- **taxonomy测试导入路径** - 更新test_taxonomy_routes.py引用knowledge_routes
- **persistent_session清理** - 添加存在性检查避免remove报错

### Changed
- **ObservationPointService** - 重构为纯async/await

## [v1.1] - 2026-03-29

### Added
- **双引擎路由** (`src/tools/db_adapter.py`) - DualEngineToolExecutor
  - 自动识别 db_type 路由到 MySQL/PostgreSQL 工具实现
  - 支持 mysql/pg/oracle 三种数据库类型
- **SessionAnalyzerAgent** (Round 13) - 会话分析专家
  - 会话状态分析、连接池分析、死锁检测
  - 工具: session_list, session_detail, connection_pool, deadlock_detection
- **SQL/会话分析增强** (Round 13)
  - 慢SQL查询、锁等待链分析、SessioListTool、DeadlockDetectionTool
- **CapacityAgent** (Round 14) - 容量管理专家
  - 存储分析、增长预测、容量报告、阈值告警
  - 工具: storage_analysis, growth_prediction, capacity_report, capacity_alert
- **安全功能增强** (Round 14)
  - 细粒度权限控制、风险级别动态调整
- **AlertAgent** (Round 15) - 告警专家
  - 告警分析、去重压缩、根因分析、预测性告警
  - 工具: alert_analysis, alert_deduplication, root_cause_analysis, predictive_alert
- **智能告警增强** (Round 15)
  - PG特有告警规则、告警链优化
- **Round 16 集成测试** (`tests/round16/`)
  - Agent + Orchestrator 集成测试 (SessionAnalyzer, Capacity, Alert)
  - 双引擎 E2E 测试 (MySQL + PostgreSQL)
  - 意图路由集成测试

### Changed
- **意图路由扩展** - 新增 4 个意图 (analyze_alert, deduplicate_alerts, root_cause, predictive_alert)
- **Orchestrator 增强** - 支持多Agent协作编排
- **知识库向量化** - `_load_alert_rules` 支持 dict/str 混合类型 check_steps
- **Dashboard 标题** - 统一为 "zCloud Agent" 品牌

### Fixed
- **知识库加载Bug** - `_load_alert_rules` 中 check_steps/resolution 字段解析问题
  - 修复 dict 被当作 str join 导致的 TypeError
- **Dashboard 测试** - 更新标题断言为 "zCloud Agent"

---

## [v1.0-Beta] - 2026-03-29

### 首发版本
- Beta商用版本发布

---

## [1.0.0] - 2026-03-28

### Added
- **RealClient** (`src/real_api/`) - 真实 Javis-DB-Agent API 客户端
  - `client.py` - RealZCloudClient 实现，9个API接口
  - `auth.py` - 认证提供者（API Key + OAuth2）
  - `config.py` - RealAPIConfig 配置管理
  - `routers/` - 9个子路由（instances, alerts, sessions, locks, sqls, replication, capacity, inspection, workorders）
- **OAuth2 认证** - 支持 client_credentials 模式
- **API 模式切换** (`scripts/switch_api_mode.py`) - mock↔real 一键切换
- **管理界面** (`templates/dashboard.html`) - Web Dashboard
- **Dashboard API** (`src/api/dashboard.py`) - 7个 API 路由
- **Round 9 测试** (`tests/round9/`) - 90个新测试
- **Round 9 执行报告** (`docs/round9-execution-report.md`)
- **项目整体总结** (`PROJECT_SUMMARY.md`)
- **CHANGELOG.md** - 本文件

### Changed
- **README.md** - 更新为 Round 9 内容
- **架构图** - 新增 Real API 层

### Deprecated
- 无

### Removed
- **pycache 清理** - 移除所有 `__pycache__` 和 `.pyc` 文件

### Fixed
- 无

### Security
- 无

---

## Prior Versions

- Round 4 (2026-03-28): 70/70 端到端测试通过
- Round 3 (2026-03-28): 告警关联推理链、Session持久化、错误注入
- Round 2 (2026-03-28): 知识库扩展、6个工具实现、Mock API
