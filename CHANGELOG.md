# Changelog

All notable changes to the Javis-DB-Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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
