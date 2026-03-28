# zCloudNewAgentProject - 数据库运维智能体系统

> 版本：v1.0 | 日期：2026-03-28 | 状态：✅ Round 4 完成（70/70测试通过）

---

## 项目概述

面向**数据库运维场景**的本地智能体系统，赋能DBA和运维人员实现智能诊断、自动巡检与安全闭环处置。

### 核心能力

- 🔍 **告警诊断** - 智能根因分析，A→B→C告警链关联推理
- 📊 **SQL分析** - 慢SQL诊断、锁分析、执行计划解读
- 🔒 **风险评估** - L1-L5风险分级，审批流控制
- 📚 **知识库** - 告警规则、SOP、案例库自动检索
- 🛡️ **安全护栏** - SQL护栏、权限分层、审计留痕
- 💾 **会话持久化** - SQLite持久化，重启后上下文恢复

---

## 架构概览

```
用户层
  ↓
Agent Gateway（会话管理、工具注册、策略引擎、审计）
  ↓
智能决策层（编排Agent + 诊断Agent + 风险Agent + SQL分析Agent + 巡检Agent + 报告Agent）
  ↓
知识层（告警规则库 / SOP库 / 案例库）
  ↓
工具执行层（查询工具 / 分析工具 / 行动工具）
  ↓
zCloud Mock API（12个接口）
  ↓
LLM层（Ollama 本地运行）
```

详见：[docs/architecture.md](docs/architecture.md)

---

## 项目结构

```
zCloudNewAgentProject/
├── src/
│   ├── agents/          # Agent实现（编排、诊断、风险、SQL、巡检、报告）
│   ├── gateway/         # Gateway核心（会话、策略、审计、告警关联）
│   ├── tools/          # 工具集（查询、分析、行动）
│   ├── knowledge/      # 知识库（告警规则、SOP、案例）
│   ├── llm/            # LLM交互（Ollama客户端）
│   ├── mock_api/       # Mock zCloud API
│   └── api/            # FastAPI路由
├── tests/              # 测试（Round 2-4，共70个测试）
├── mock_zcloud_api/    # Mock API Server（12个接口）
├── configs/            # 配置文件
├── knowledge/          # 知识内容（15条告警规则、8个SOP、3个案例）
├── scripts/            # 工具脚本
└── docs/               # 架构文档、需求文档
```

---

## 快速开始

### 环境要求

- Python 3.10+
- Ollama（本地LLM推理）
- macOS / Linux

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动 Mock API

```bash
cd ~/SWproject/zCloudNewAgentProject
python3 -m uvicorn mock_zcloud_api.server:app --host 0.0.0.0 --port 18080
```

### 运行测试

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行 Round 4 测试
python3 -m pytest tests/round4/ -v
```

---

## 性能基线

| 指标 | 目标 | 实际 | 达标 |
|------|------|------|------|
| 平均响应时间 | < 30,000ms | **740ms** | ✅ |
| P95 响应时间 | < 30,000ms | **749ms** | ✅ |
| 测试通过率 | ≥ 95% | **100%** | ✅ |

---

## 核心模块

### 告警关联推理链（Round 3）

- **文件**：`src/gateway/alert_correlator.py`（603行）
- **功能**：15+因果规则，支持 A→B→C 链式诊断
- **测试**：`tests/round3/test_alert_correlation.py`（9个测试）

### Session 持久化（Round 3）

- **文件**：`src/gateway/persistent_session.py`（605行）
- **功能**：SQLite持久化，TTL管理，重启恢复
- **测试**：`tests/round3/test_session_persistence.py`（14个测试）

### Mock API 增强（Round 3）

- **文件**：`src/mock_api/error_injector.py`
- **功能**：超时注入、限流模拟、级联故障模拟
- **测试**：`tests/round3/test_error_injector.py`（17个测试）

---

## 迭代历史

| 轮次 | 完成时间 | 核心成果 | 测试数 |
|------|----------|----------|--------|
| Round 2 | 2026-03-28 | 知识库扩展、6个工具实现、Mock API | 26 |
| Round 3 | 2026-03-28 | 告警关联推理链、Session持久化、错误注入 | 98 |
| Round 4 | 2026-03-28 | 70/70端到端测试通过、性能基线验证 | 70 |

---

## 文档

- [架构文档](docs/architecture.md)
- [需求文档](docs/requirements.md)
- [技术方案](docs/tech-spec.md)
- [zCloud API研究](docs/zcloud-api-research.md)
- [认证设计](docs/zcloud-auth-design.md)
- [Round 3执行报告](docs/round3-execution-report.md)
- [Round 4性能报告](docs/round4-performance-report.md)

---

## 下一步

1. 接入真实 zCloud API（替换 Mock）
2. 前端界面开发
3. 知识库持续沉淀
4. 生产环境部署验证

---

*项目负责人：道衍 | 开发者：悟通 | 测试者：真显*
