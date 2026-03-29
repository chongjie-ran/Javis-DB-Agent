# Changelog

All notable changes to the Javis-DB-Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
