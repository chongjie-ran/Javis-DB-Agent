# Javis-DB-Agent 测试用例框架

> 版本：v1.0 | 日期：2026-03-28 | 状态：✅ 准备就绪

---

## 1. 测试环境

| 组件 | 状态 | 说明 |
|------|------|------|
| PostgreSQL | ✅ 运行中 | 端口5432，测试库: zcloud_agent_test |
| 测试数据库 | ✅ 已创建 | 用户: zcloud_test |
| pytest | ✅ 已安装 | 版本 9.0.2 |
| 测试框架 | ✅ 就绪 | 26个单元测试 + 17个集成测试 |

---

## 2. 测试用例统计

### 2.1 单元测试 (26个)

| 模块 | 测试数 | 覆盖内容 |
|------|--------|----------|
| test_tools.py | 12 | Tool定义、参数校验、风险级别、策略引擎 |
| test_agents.py | 14 | 6类Agent的输入输出格式、流程逻辑 |

#### Agent测试覆盖

| Agent | 测试用例 |
|-------|----------|
| OrchestratorAgent | 意图识别、Agent选择、执行计划构建 |
| DiagnosticAgent | 诊断输出格式、置信度范围、下一步建议 |
| RiskAssessmentAgent | 风险级别定义、评估输出格式 |
| SQLAnalyzerAgent | SQL分析输出、锁分析输出 |
| InspectorAgent | 健康评分范围、巡检结果格式 |
| ReporterAgent | 报告类型、RCA报告结构 |

### 2.2 集成测试 (17个)

| 类别 | 测试数 | 覆盖内容 |
|------|--------|----------|
| DatabaseConnection | 2 | 测试库连接、数据库可访问性 |
| GatewayEndpoints | 3 | API请求/响应格式 |
| AgentWorkflow | 3 | 诊断、SQL分析、巡检工作流 |
| SecurityLayer | 3 | 高风险动作阻断、SQL护栏、权限检查 |
| KnowledgeLayer | 2 | 告警规则结构、SOP结构 |
| LLMIntegration | 2 | System Prompt安全规则、Tool Call格式 |
| AuditLogging | 2 | 审计日志结构、操作链覆盖 |

---

## 3. 测试数据 (Mock Fixtures)

位于 `tests/mock/fixtures.py`:

| Mock数据 | 用途 |
|----------|------|
| get_mock_instance_status() | 实例状态查询 |
| get_mock_sessions() | 会话列表 |
| get_mock_locks() | 锁等待信息 |
| get_mock_slow_sqls() | 慢SQL记录 |
| get_mock_replication_status() | 复制状态 |
| get_mock_alert_event() | 告警事件 |
| get_mock_inspection_result() | 巡检结果 |
| get_mock_rca_report() | RCA报告 |
| get_mock_user_permissions() | 用户权限 |

---

## 4. 运行测试

```bash
cd ~/SWproject/Javis-DB-Agent

# 运行所有测试
python3 tests/run_tests.py

# 仅运行单元测试
python3 tests/run_tests.py --unit

# 仅运行集成测试
python3 tests/run_tests.py --integration

# 生成覆盖率报告
python3 tests/run_tests.py --coverage
```

---

## 5. 测试覆盖的P0功能

根据 requirements.md 中的P0优先级:

| P0功能 | 测试覆盖 |
|--------|----------|
| 告警解释与根因诊断 | ✅ 诊断Agent测试、工作流测试 |
| SQL分析 | ✅ SQL分析Agent测试 |
| 安全护栏 | ✅ 策略引擎测试、SQL护栏测试 |
| 审计留痕 | ✅ 审计日志结构测试 |
| 权限分层 | ✅ 权限级别测试 |

---

## 6. 等待悟通完成的功能

悟通开发完成后，需要扩展测试的模块:

| 待测模块 | 前置条件 |
|----------|----------|
| ToolExecutor.execute() | 实际工具实现 |
| OllamaClient | Ollama服务运行 |
| Gateway API | FastAPI路由实现 |
| Agent.process() | Agent类实现 |

---

## 7. 测试用例编写规范

```python
class TestXXX:
    """测试类描述"""
    
    def test_xxx_output_format(self):
        """验证XXX输出格式"""
        result = get_xxx_result()
        required_fields = ["field1", "field2"]
        for field in required_fields:
            assert field in result
    
    def test_xxx_validation(self):
        """验证XXX参数校验"""
        # 参数验证测试
        pass
```

---

## 8. 已知限制

1. **无Ollama环境**：LLM相关测试使用Mock
2. **无Javis平台**：数据源使用Mock数据
3. **未覆盖性能测试**：待系统完整实现后添加
4. **未覆盖端到端场景**：需要完整Agent实现后添加

---

*状态：✅ 测试框架就绪，等待悟通通知核心功能完成后开始测试*
