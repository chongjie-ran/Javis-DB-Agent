# V2.6 R1 测试报告 - Round27

> 测试者：真显 | 日期：2026-04-01 | 状态：**待悟通完成开发后执行**

---

## 一、测试概览

### 1.1 测试范围

| 功能模块 | 测试用例数 | 覆盖内容 |
|----------|-----------|----------|
| F1: Hook 事件驱动系统 | 30+ | HookEngine、HookEvent、RuleEngine |
| F3: SafetyGuardRail | 25+ | Gate 强制审批、DDL 检测、审批流程 |
| 集成测试 | 10+ | Hook + SafetyGuardRail + 真实数据库 |
| **合计** | **65+** | |

### 1.2 测试文件

```
tests/round27/
├── test_hook_system.py   # Hook 系统测试（30 个用例）
├── test_guard_rail.py    # SafetyGuardRail 测试（25 个用例）
└── Round27_Test_Report.md
```

---

## 二、F1: Hook 事件驱动系统测试用例

### 2.1 HookEngine 基础功能（HS 系列）

| 用例ID | 描述 | 预期结果 |
|--------|------|----------|
| HS-01 | HookEngine.emit() 正确触发事件 | Handler 被调用，返回 allowed=True |
| HS-02 | 多个 Hook 监听同一事件 | 所有 handler 均被调用 |
| HS-03 | 规则匹配正确（正则） | 匹配则触发 handler |
| HS-04 | 规则不匹配时不触发 | Handler 不被调用 |
| HS-05 | unregister 移除 Hook | 移除后 handler 不再被调用 |

### 2.2 HookEvent 各类事件（HE 系列）

| 用例ID | 事件类型 | 测试场景 |
|--------|----------|----------|
| HE-01 | TOOL_BEFORE_EXECUTE | 工具执行前事件正确携带 payload |
| HE-02 | TOOL_AFTER_EXECUTE | 工具执行后事件包含结果和执行时间 |
| HE-03 | SQL_DDL_DETECTED | DROP TABLE 被检测并拦截 |
| HE-04 | SQL_DDL_DETECTED | TRUNCATE 被检测并拦截 |
| HE-05 | SQL_DDL_DETECTED | ALTER TABLE 被检测并拦截 |
| HE-06 | APPROVAL_REQUESTED | 审批发起事件携带工具名和风险级别 |
| HE-07 | APPROVAL_APPROVED | 审批通过事件携带审批人信息 |
| HE-08 | APPROVAL_REJECTED | 审批拒绝事件携带拒绝原因 |
| HE-09 | SESSION_START | 会话开始事件正确触发 |
| HE-10 | SESSION_END | 会话结束事件正确触发 |

### 2.3 RuleEngine 规则评估（RE 系列）

| 用例ID | 描述 | 预期结果 |
|--------|------|----------|
| RE-01 | 正则匹配规则 | 各类正则模式正确匹配/不匹配 |
| RE-02 | 条件组合规则（AND） | 多条件同时满足才触发 |
| RE-03 | 阻塞动作（block） | 返回 allowed=False，action=block |
| RE-04 | 警告动作（warn） | 返回 allowed=True，action=warn |
| RE-05 | 日志动作（log） | 仅记录，不阻止执行 |

### 2.4 Hook 与真实数据库集成（HI 系列）

| 用例ID | 描述 | 数据库操作 |
|--------|------|-----------|
| HI-01 | SELECT 查询完整 Hook 流程 | `SELECT 1` 真实执行 |
| HI-02 | DDL 检测（CREATE TABLE） | 拦截 DDL，不实际执行 |
| HI-03 | Hook + SafetyGuardRail 完整流程 | SELECT 通过 L1 检查 |

### 2.5 HookRegistry 注册表（HR 系列）

| 用例ID | 描述 | 预期结果 |
|--------|------|----------|
| HR-01 | 列出指定事件的所有 Hook | 返回正确数量 |
| HR-02 | 启用/禁用 Hook | disable 后不触发，enable 后恢复 |

---

## 三、F3: SafetyGuardRail 安全护栏测试用例

### 3.1 Gate 层强制审批（GE 系列）

| 用例ID | 描述 | 预期结果 |
|--------|------|----------|
| GE-01 | L1 只读操作无需审批 | allowed=True, approval_required=False |
| GE-02 | L2 诊断操作无需审批 | allowed=True, approval_required=False |
| GE-03 | L3 低风险操作允许但需日志 | allowed=True |
| GE-04 | L4 中风险操作必须通过 Gate | 触发审批请求，令牌写入 context |
| GE-05 | L5 高风险操作必须双人审批 | 触发双人审批请求 |
| GE-06 | Tool 无法绕过 Gate | 无令牌时抛出 ApprovalRequiredError |
| GE-07 | 持有有效令牌可执行 | 不抛出异常，正常返回 |

### 3.2 DDL 检测（DD 系列）

| 用例ID | DDL 类型 | 测试场景 |
|--------|----------|----------|
| DD-01 | DROP TABLE | 检测并拦截 DROP TABLE |
| DD-02 | TRUNCATE | 检测并拦截 TRUNCATE TABLE |
| DD-03 | ALTER TABLE | 检测并拦截 ADD/DROP/ALTER COLUMN |
| DD-04 | SELECT 安全 | SELECT 语句不被 DDL 检测拦截 |
| DD-05 | CREATE TABLE 真实拦截 | Hook 阻止 CREATE TABLE，数据库无新建表 |

### 3.3 审批流程集成（AF 系列）

| 用例ID | 描述 | 预期结果 |
|--------|------|----------|
| AF-01 | 发起审批触发 APPROVAL_REQUESTED | 事件携带完整信息 |
| AF-02 | 审批通过触发 APPROVAL_APPROVED | 事件携带审批人信息 |
| AF-03 | 审批拒绝触发 APPROVAL_REJECTED | 事件携带拒绝原因 |
| AF-04 | 令牌正确写入上下文 | context["approval_tokens"] 有值 |
| AF-05 | 审批拒绝阻止执行 | 抛出 ApprovalRequiredError |

### 3.4 端到端集成测试（E2E 系列）

| 用例ID | 描述 | 覆盖范围 |
|--------|------|----------|
| E2E-01 | Hook + Guard + 真实 SELECT | 全链路无 mock |
| E2E-02 | DDL 被阻止，无审批令牌 | Hook + Guard 双重拦截 |
| E2E-03 | L4 有令牌可执行 | 令牌验证通过 |
| E2E-04 | 会话生命周期 Hook | SESSION_START → query → SESSION_END |

### 3.5 风险级别映射（RL 系列）

| 用例ID | 描述 | 预期结果 |
|--------|------|----------|
| RL-01 | 风险级别顺序 | L1 < L2 < L3 < L4 < L5 |
| RL-02 | Gate 风险阈值 | L1-L3 放行，L4-L5 要求审批 |
| RL-03 | 工具风险级别映射 | 各工具正确映射到对应级别 |

---

## 四、测试设计原则

### 4.1 真实环境要求（强制）

- ✅ 所有集成测试使用真实 PostgreSQL 连接
- ✅ 不 mock 数据库连接
- ✅ 测试完整的 SQL 执行流程
- ✅ 使用 `javis_test_db` 数据库（PostgreSQL localhost:5432）

### 4.2 测试隔离

- 每个测试用例使用独立的 session_id
- DDL 测试使用 `_rollback` 机制，不污染数据库
- 测试后清理创建的表

### 4.3 测试覆盖矩阵

| 类别 | 单元测试 | 集成测试 | E2E测试 |
|------|----------|----------|---------|
| HookEngine | ✅ HS 系列 | ✅ HI 系列 | ✅ E2E 系列 |
| HookEvent | ✅ HE 系列 | ✅ HI 系列 | ✅ E2E 系列 |
| RuleEngine | ✅ RE 系列 | ✅ HI 系列 | - |
| SafetyGuardRail | ✅ GE 系列 | ✅ AF 系列 | ✅ E2E 系列 |
| DDL 检测 | ✅ DD 系列 | ✅ DD-05 | ✅ E2E-02 |

---

## 五、执行条件

### 5.1 前置条件

```bash
# 1. 启动 PostgreSQL
pg_ctl -D /usr/local/var/postgresql@16/postgresql.conf start

# 2. 创建测试数据库
createdb javis_test_db -h localhost -U chongjieran

# 3. 安装依赖
cd ~/SWproject/Javis-DB-Agent
pip install -r requirements.txt

# 4. 运行测试
python3 -m pytest tests/round27/ -v --tb=short
```

### 5.2 依赖模块（R1 开发后提供）

```python
# 需要悟通在 R1 中实现以下模块：
src/gateway/hooks/
├── __init__.py
├── engine.py      # HookEngine, HookResult
├── registry.py    # HookRegistry
├── rule_engine.py # RuleEngine
├── context.py     # HookContext
├── events.py      # HookEvent 枚举
└── loader.py      # YAML 配置加载器

src/security/guard_rail.py  # SafetyGuardRail, ApprovalRequiredError
```

---

## 六、预期结果与验收标准

### 6.1 验收标准

| 标准 | 要求 |
|------|------|
| 测试通过率 | ≥ 90% |
| 覆盖率 | HookEngine 核心方法 100% |
| 真实数据库测试 | 所有 E2E 测试通过 |
| DDL 拦截 | DROP/TRUNCATE/ALTER 100% 拦截 |
| 审批 Gate | L4/L5 无令牌 100% 拦截 |

### 6.2 已知限制

1. **R1 开发前测试无法运行**：测试依赖尚未开发的 `src/gateway/hooks/` 和 `src/security/guard_rail.py` 模块
2. **审批 Gate mock**：部分测试使用 mock，需真实审批环境补充
3. **并行测试未覆盖**：R2 才有并行执行，R1 测试覆盖 Hook 和 Guard

---

## 七、后续计划

| 阶段 | 任务 | 依赖 |
|------|------|------|
| 悟通开发 R1 | 实现 Hook 系统 + SafetyGuardRail | - |
| Round28 | 运行 Round27 测试用例，汇报结果 | R1 开发完成 |
| Round29（R2 测试） | Hook + 并行执行测试 | R2 开发完成 |
| Round30（R3 测试） | 可观测性框架测试 | R3 开发完成 |

---

*测试用例设计：真显 | 2026-04-01*
