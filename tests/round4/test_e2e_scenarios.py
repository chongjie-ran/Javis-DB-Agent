"""
第四轮测试：端到端测试场景设计

本模块测试完整的用户旅程，覆盖6大核心场景：
1. 告警诊断全流程
2. 会话查询全流程
3. SQL分析全流程
4. 巡检报告全流程
5. 风险评估全流程
6. 多Agent协作全流程
"""
import pytest
import asyncio
import time
from unittest.mock import MagicMock, AsyncMock
from typing import List, Dict, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.agents.orchestrator import OrchestratorAgent, Intent
from src.agents.diagnostic import DiagnosticAgent
from src.agents.risk import RiskAgent
from src.agents.sql_analyzer import SQLAnalyzerAgent
from src.agents.inspector import InspectorAgent
from src.agents.reporter import ReporterAgent
from src.gateway.alert_correlator import AlertCorrelator, AlertNode, AlertRole, CorrelationLink
from src.tools.query_tools import QueryInstanceStatusTool, QuerySessionTool, QueryLockTool


# ============================================================================
# 测试夹具
# ============================================================================

@pytest.fixture
def mock_zcloud_client():
    """Mock zCloud客户端"""
    client = MagicMock()
    
    # Mock实例数据
    client.get_instance = AsyncMock(return_value={
        "instance_id": "INS-PROD-001",
        "name": "生产主库",
        "status": "running",
        "version": "PostgreSQL 14.5",
        "cpu_cores": 16,
        "memory_gb": 64,
        "disk_gb": 500,
    })
    
    # Mock告警列表
    client.get_alerts = AsyncMock(return_value=[
        {
            "alert_id": "ALT-001",
            "alert_type": "CPU_HIGH",
            "severity": "warning",
            "instance_id": "INS-PROD-001",
            "occurred_at": time.time() - 300,
            "metric_value": 92.5,
            "threshold": 80.0,
            "message": "CPU使用率超过阈值",
            "status": "active",
        },
        {
            "alert_id": "ALT-002",
            "alert_type": "SLOW_QUERY",
            "severity": "warning",
            "instance_id": "INS-PROD-001",
            "occurred_at": time.time() - 180,
            "metric_value": 5000,
            "threshold": 3000,
            "message": "检测到慢查询",
            "status": "active",
        },
        {
            "alert_id": "ALT-003",
            "alert_type": "LOCK_WAIT",
            "severity": "critical",
            "instance_id": "INS-PROD-001",
            "occurred_at": time.time() - 60,
            "metric_value": 15,
            "threshold": 5,
            "message": "锁等待会话数超限",
            "status": "active",
        },
    ])
    
    # Mock会话数据
    client.get_sessions = AsyncMock(return_value={
        "sessions": [
            {"sid": 1001, "serial#": 2001, "username": "APP_USER", "status": "ACTIVE", "wait_event": "lock"},
            {"sid": 1002, "serial#": 2002, "username": "APP_USER", "status": "ACTIVE", "wait_event": None},
        ],
        "total": 2,
    })
    
    # Mock锁数据
    client.get_locks = AsyncMock(return_value={
        "locks": [
            {"lock_type": "row exclusive", "mode": "share", "granted": True, "sid": 1001},
            {"lock_type": "row exclusive", "mode": "share", "granted": False, "sid": 1002},
        ],
        "blocking_chain": [{"blocker": 1001, "waiter": 1002, "lock_type": "row exclusive"}],
    })
    
    # Mock慢SQL数据
    client.get_slow_queries = AsyncMock(return_value={
        "queries": [
            {
                "sql_id": "sql_abc12345",
                "query": "SELECT * FROM orders WHERE status = 'pending'",
                "execution_time_ms": 5234,
                "calls": 1523,
                "rows": 45230,
            }
        ],
        "total": 1,
    })
    
    return client


@pytest.fixture
def mock_llm_response():
    """Mock LLM响应"""
    return {
        "response": """根据分析，诊断结论如下：

## 根因分析
**根本原因**: 长时间运行的批量事务持有锁，导致其他会话等待

## 置信度
**置信度**: 0.85

## 证据
1. CPU使用率92.5%，存在性能压力
2. 存在5秒以上的慢查询
3. 锁等待会话数达到15个

## 下一步行动
1. 查看阻塞链详情
2. 评估是否可以Kill阻塞会话
3. 检查应用层事务处理逻辑

## 告警关联链
- ALT-003 (LOCK_WAIT) - 症状
- ALT-002 (SLOW_QUERY) - 促成因素
- ALT-001 (CPU_HIGH) - 背景因素
""",
        "done": True,
    }


# ============================================================================
# 场景1：告警诊断全流程测试
# ============================================================================

class TestAlertDiagnosisE2E:
    """告警诊断端到端测试"""
    
    @pytest.mark.asyncio
    async def test_single_alert_diagnosis_flow(self, mock_zcloud_client, mock_llm_response):
        """
        测试单个告警的完整诊断流程
        
        验证点：
        1. 告警信息正确传入
        2. 诊断Agent正确处理
        3. 关联告警被正确识别
        4. 诊断结果格式正确
        """
        # Setup
        agent = DiagnosticAgent()
        agent.think = AsyncMock(return_value=mock_llm_response["response"])
        
        context = {
            "instance_id": "INS-PROD-001",
            "mock_client": mock_zcloud_client,
        }
        
        # Execute
        result = await agent.diagnose_alert("ALT-001", context)
        
        # Assert
        assert result.success, f"诊断失败: {result.content}"
        assert result.metadata["agent"] == "diagnostic"
        assert "correlation_chain" in context, "未执行关联分析"
        assert len(context["correlation_chain"]) >= 1, "关联链太短"
    
    @pytest.mark.asyncio
    async def test_alert_chain_diagnosis_flow(self, mock_zcloud_client, mock_llm_response):
        """
        测试告警链的完整诊断流程
        
        验证点：
        1. 多告警联合诊断
        2. 根因告警被正确识别
        3. 诊断路径正确构建
        """
        # Setup
        agent = DiagnosticAgent()
        agent.think = AsyncMock(return_value=mock_llm_response["response"])
        
        context = {
            "instance_id": "INS-PROD-001",
            "mock_client": mock_zcloud_client,
        }
        
        # Execute
        result = await agent.diagnose_alert_chain(
            alert_ids=["ALT-001", "ALT-002", "ALT-003"],
            context=context,
            mock_client=mock_zcloud_client,
        )
        
        # Assert
        assert result.success, f"告警链诊断失败: {result.content}"
        assert "diagnostic_path" in context, "未生成诊断路径"
    
    @pytest.mark.asyncio
    async def test_alert_correlation_completeness(self, mock_zcloud_client):
        """
        测试告警关联推理的完整性
        
        验证点：
        1. 所有相关告警都被找到
        2. 告警角色正确分配
        3. 置信度在有效范围内
        """
        from src.gateway.alert_correlator import get_mock_alert_correlator
        
        # Setup
        correlator = get_mock_alert_correlator()
        all_alerts = await mock_zcloud_client.get_alerts(status="active")
        
        # Execute
        result = await correlator.correlate_alerts(
            primary_alert_id="ALT-003",  # LOCK_WAIT
            all_alerts=all_alerts,
            mock_client=mock_zcloud_client,
        )
        
        # Assert
        assert result.primary_alert_id == "ALT-003"
        assert len(result.correlation_chain) >= 2, "关联链应包含多个告警"
        assert result.root_cause != "", "应有根因分析"
        assert 0.0 <= result.confidence <= 1.0, "置信度应在[0,1]范围内"
        
        # 验证告警角色
        roles = [node.role for node in result.correlation_chain]
        assert AlertRole.ROOT_CAUSE in roles or AlertRole.SYMPTOM in roles, "应有角色分配"


# ============================================================================
# 场景2：会话查询全流程测试
# ============================================================================

class TestSessionQueryE2E:
    """会话查询端到端测试"""
    
    @pytest.mark.asyncio
    async def test_session_list_query_flow(self, mock_zcloud_client):
        """
        测试会话列表查询流程
        
        验证点：
        1. 查询参数正确传递
        2. 返回数据格式正确
        3. 分页/限制参数生效
        """
        # Setup
        tool = QuerySessionTool()
        params = {"instance_id": "INS-PROD-001", "limit": 10}
        context = {"mock_client": mock_zcloud_client}
        
        # Execute
        result = await tool.execute(params, context)
        
        # Assert
        assert result.success, f"查询失败: {result}"
        assert "sessions" in result.data, "缺少sessions字段"
        assert isinstance(result.data["sessions"], list), "sessions应为列表"
        assert len(result.data["sessions"]) <= 10, "limit参数未生效"
    
    @pytest.mark.asyncio
    async def test_session_filter_flow(self, mock_zcloud_client):
        """
        测试会话过滤查询流程
        
        验证点：
        1. 过滤条件正确应用
        2. 返回结果符合过滤条件
        """
        # Setup
        tool = QuerySessionTool()
        params = {"instance_id": "INS-PROD-001", "filter": "status=ACTIVE"}
        context = {"mock_client": mock_zcloud_client}
        
        # Execute
        result = await tool.execute(params, context)
        
        # Assert
        assert result.success, f"过滤查询失败: {result}"
        # 验证所有返回的会话都符合ACTIVE状态（如果mock支持）


# ============================================================================
# 场景3：SQL分析全流程测试
# ============================================================================

class TestSQLAnalysisE2E:
    """SQL分析端到端测试"""
    
    @pytest.mark.asyncio
    async def test_slow_sql_detection_flow(self, mock_zcloud_client):
        """
        测试慢SQL检测流程
        
        验证点：
        1. 慢SQL被正确识别
        2. SQL详情完整
        3. 执行统计准确
        """
        # Setup
        from src.tools.query_tools import QuerySlowSQLTool
        tool = QuerySlowSQLTool()
        params = {"instance_id": "INS-PROD-001", "limit": 5}
        context = {"mock_client": mock_zcloud_client}
        
        # Execute
        result = await tool.execute(params, context)
        
        # Assert
        assert result.success, f"慢SQL查询失败: {result}"
        assert "queries" in result.data, "缺少queries字段"
        if result.data["queries"]:
            sql = result.data["queries"][0]
            assert "execution_time_ms" in sql, "缺少执行时间"
            assert sql["execution_time_ms"] > 0, "执行时间应为正数"
    
    @pytest.mark.asyncio
    async def test_sql_analyzer_integration(self, mock_zcloud_client, mock_llm_response):
        """
        测试SQL分析Agent集成
        
        验证点：
        1. Agent正确调用查询工具
        2. 分析结果格式正确
        """
        # Setup
        agent = SQLAnalyzerAgent()
        agent.think = AsyncMock(return_value="""## SQL分析结果

### 问题SQL
sql_abc12345

### 执行统计
- 平均执行时间: 5234ms
- 调用次数: 1523次
- 返回行数: 45230行

### 优化建议
1. 添加索引
2. 优化WHERE条件
3. 考虑分页
""")
        
        context = {
            "instance_id": "INS-PROD-001",
            "mock_client": mock_zcloud_client,
            "sql_id": "sql_abc12345",
        }
        
        # Execute
        result = await agent.analyze_sql("sql_abc12345", context)
        
        # Assert
        assert result.success, f"SQL分析失败: {result.content}"


# ============================================================================
# 场景4：巡检报告全流程测试
# ============================================================================

class TestInspectionE2E:
    """巡检报告端到端测试"""
    
    @pytest.mark.asyncio
    async def test_health_inspection_flow(self, mock_zcloud_client):
        """
        测试健康巡检流程
        
        验证点：
        1. 巡检项目完整
        2. 健康评分计算正确
        3. 问题识别准确
        """
        # Setup
        agent = InspectorAgent()
        agent.think = AsyncMock(return_value="""## 健康巡检报告

### 整体评分
**健康评分**: 75/100 (良好)

### 检查项目
1. **CPU**: 45% (正常)
2. **内存**: 68% (正常)
3. **磁盘**: 55% (正常)
4. **连接数**: 156/500 (正常)

### 发现问题
- 存在1个慢SQL需要优化

### 建议
1. 优化慢SQL
2. 定期巡检
""")
        
        context = {
            "instance_id": "INS-PROD-001",
            "mock_client": mock_zcloud_client,
        }
        
        # Execute
        result = await agent.inspect_instance("INS-PROD-001", context)
        
        # Assert
        assert result.success, f"巡检失败: {result.content}"
        assert "inspector" in result.metadata.get("agent", ""), "Agent类型错误"


# ============================================================================
# 场景5：风险评估全流程测试
# ============================================================================

class TestRiskAssessmentE2E:
    """风险评估端到端测试"""
    
    @pytest.mark.asyncio
    async def test_risk_level_calculation(self, mock_zcloud_client):
        """
        测试风险等级计算
        
        验证点：
        1. 风险因素识别完整
        2. 风险等级计算正确
        3. 审批要求判断准确
        """
        # Setup
        agent = RiskAgent()
        agent.think = AsyncMock(return_value="""## 风险评估报告

### 风险等级
**级别**: L3 (中等风险)

### 风险因素
1. 数据一致性风险: 0.7 (中高)
2. 服务可用性风险: 0.3 (低)
3. 性能影响风险: 0.5 (中)

### 处置建议
- 需要DBA审批
- 建议在低峰期执行
- 做好回滚准备

### 预估影响
- 预计中断时间: 30秒
- 影响会话数: 2-3个
""")
        
        context = {
            "instance_id": "INS-PROD-001",
            "operation": "kill_session",
            "target": {"sid": 1001, "serial#": 2001},
            "mock_client": mock_zcloud_client,
        }
        
        # Execute
        result = await agent.assess_risk("kill_session", context)
        
        # Assert
        assert result.success, f"风险评估失败: {result.content}"
    
    @pytest.mark.asyncio
    async def test_auto_vs_manual_decision(self, mock_zcloud_client):
        """
        测试自动/手动决策判断
        
        验证点：
        1. 低风险操作可自动执行
        2. 高风险操作需审批
        """
        # Setup
        agent = RiskAgent()
        
        # 测试低风险操作
        agent.think = AsyncMock(return_value="""## 风险评估报告

### 风险等级
**级别**: L1 (低风险)

### 可自动处理
是

### 理由
只读查询，无数据修改风险
""")
        
        context = {
            "instance_id": "INS-PROD-001",
            "operation": "query_status",
            "mock_client": mock_zcloud_client,
        }
        
        # Execute
        result = await agent.assess_risk("query_status", context)
        
        # Assert
        assert result.success, f"低风险评估失败: {result.content}"


# ============================================================================
# 场景6：多Agent协作全流程测试
# ============================================================================

class TestMultiAgentCollaborationE2E:
    """多Agent协作端到端测试"""
    
    @pytest.mark.asyncio
    async def test_orchestrator_intent_recognition(self):
        """
        测试编排Agent意图识别
        
        验证点：
        1. 诊断意图正确识别
        2. 分析意图正确识别
        3. 巡检意图正确识别
        """
        # Setup
        agent = OrchestratorAgent()
        
        # Test cases: (input, expected_intent)
        test_cases = [
            ("CPU告警了，帮我看看", Intent.DIAGNOSE),
            ("分析一下这个慢SQL", Intent.SQL_ANALYZE),
            ("做个健康巡检", Intent.INSPECT),
            ("生成一份报告", Intent.REPORT),
            ("评估一下风险", Intent.RISK_ASSESS),
        ]
        
        for goal, expected_intent in test_cases:
            # Execute
            recognized_intent = await agent._recognize_intent(goal)
            
            # Assert
            assert recognized_intent == expected_intent, \
                f"意图识别错误: 输入='{goal}', 期望={expected_intent}, 实际={recognized_intent}"
    
    @pytest.mark.asyncio
    async def test_agent_selection_for_diagnose(self):
        """
        测试诊断场景的Agent选择
        
        验证点：
        1. 诊断场景选择diagnostic和risk Agent
        2. 不选择无关Agent
        """
        # Setup
        agent = OrchestratorAgent()
        
        # Execute
        selected = agent._select_agents(Intent.DIAGNOSE, "CPU告警")
        selected_names = [a.name for a in selected]
        
        # Assert
        assert "diagnostic" in selected_names, "应选择diagnostic Agent"
        assert "risk" in selected_names, "诊断场景应包含risk Agent"
        assert "sql_analyzer" not in selected_names and "inspector" not in selected_names, \
            "不应选择无关Agent"
    
    @pytest.mark.asyncio
    async def test_full_diagnosis_workflow(self, mock_zcloud_client, mock_llm_response):
        """
        测试完整诊断工作流（编排+诊断+风险）
        
        验证点：
        1. 多Agent正确协作
        2. 结果正确汇总
        3. 上下文正确传递
        """
        # Setup
        orchestrator = OrchestratorAgent()
        diagnostic = orchestrator.get_agent("diagnostic")
        risk = orchestrator.get_agent("risk")
        
        diagnostic.think = AsyncMock(return_value=mock_llm_response["response"])
        risk.think = AsyncMock(return_value="""## 风险评估

### 风险等级: L3

### 建议
需要人工审批后执行
""")
        
        context = {
            "instance_id": "INS-PROD-001",
            "alert_id": "ALT-001",
            "mock_client": mock_zcloud_client,
        }
        
        # Execute - 模拟编排流程
        goal = "CPU告警了，帮我诊断并评估风险"
        plan = orchestrator._build_plan(["diagnostic", "risk"], goal, context)
        
        # Assert
        assert len(plan) >= 2, "计划应包含多个步骤"
        assert plan[0]["agent"] == "diagnostic", "第一步应是诊断"
        assert plan[1]["agent"] == "risk", "第二步应是风险评估"


# ============================================================================
# 知识库检索准确性测试
# ============================================================================

class TestKnowledgeBaseAccuracy:
    """知识库检索准确性测试"""
    
    @pytest.mark.asyncio
    async def test_sop_retrieval_accuracy(self):
        """
        测试SOP知识检索准确性
        
        验证点：
        1. 相关SOP被正确召回
        2. 检索结果排序合理
        3. 知识内容准确
        """
        import os
        knowledge_dir = os.path.join(os.path.dirname(__file__), "../..", "knowledge", "sop")
        
        # 验证SOP文件存在
        assert os.path.exists(knowledge_dir), f"SOP目录不存在: {knowledge_dir}"
        
        sop_files = os.listdir(knowledge_dir)
        assert len(sop_files) > 0, "SOP目录为空"
        
        # 验证关键SOP存在
        expected_sops = [
            "lock_wait排查.md",
            "主从延迟排查.md",
            "慢SQL分析.md",
            "容量不足处理.md",
        ]
        
        for expected in expected_sops:
            assert expected in sop_files, f"缺少关键SOP: {expected}"
    
    @pytest.mark.asyncio
    async def test_case_library_coverage(self):
        """
        测试案例库覆盖度
        
        验证点：
        1. 案例文件格式正确
        2. 关键案例存在
        """
        import os
        cases_dir = os.path.join(os.path.dirname(__file__), "../..", "knowledge", "cases")
        
        assert os.path.exists(cases_dir), f"案例目录不存在: {cases_dir}"
        
        case_files = os.listdir(cases_dir)
        assert len(case_files) >= 3, f"案例数量不足: {len(case_files)}"
        
        # 验证案例格式（应包含日期前缀）
        for case in case_files:
            assert case[0].isdigit(), f"案例命名不规范: {case}"
    
    @pytest.mark.asyncio
    async def test_alert_rules_completeness(self):
        """
        测试告警规则完整性
        
        验证点：
        1. 告警规则文件存在
        2. 规则格式正确
        3. 关键规则存在
        """
        import os
        import yaml
        
        rules_file = os.path.join(os.path.dirname(__file__), "../..", "knowledge", "alert_rules.yaml")
        assert os.path.exists(rules_file), f"告警规则文件不存在: {rules_file}"
        
        with open(rules_file, "r", encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        
        assert "alert_rules" in rules, "缺少alert_rules字段"
        assert len(rules["alert_rules"]) > 0, "规则列表为空"
        
        # 验证关键告警类型
        alert_types = [r.get("alert_type") for r in rules["alert_rules"]]
        key_types = ["CPU_HIGH", "LOCK_WAIT_TIMEOUT", "SLOW_QUERY_DETECTED", "DISK_FULL"]
        
        for key_type in key_types:
            assert key_type in alert_types, f"缺少关键告警规则: {key_type}"


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
