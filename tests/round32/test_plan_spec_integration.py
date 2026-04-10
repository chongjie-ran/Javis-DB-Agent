"""
PlanSpec 集成测试 - V3.1 P1功能

测试覆盖：
1. PlanSpec 默认值
2. get_instructions 生成
3. validate_result 验证
4. analysis_depth 配置
5. output_format 配置
6. target_scope 配置
7. 与 SubagentMode 集成

运行：
    cd ~/.openclaw/workspace/Javis-DB-Agent
    python3 -m pytest tests/round32/test_plan_spec_integration.py -v --tb=short

已知 Bug:
- output_format 配置未正确反映在指令中（_get_format_instruction 未被调用）
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.subagent.plan_spec import PlanSpec
from src.subagent.subagent_spec import SubagentMode


class TestPlanSpecDefaults:
    """PlanSpec 默认值测试"""

    def test_default_timeout(self):
        """默认超时 10 分钟"""
        spec = PlanSpec(task="分析代码结构")
        assert spec.timeout == 600

    def test_default_max_cost(self):
        """默认最大开销 50k"""
        spec = PlanSpec(task="分析代码结构")
        assert spec.max_cost == 50000

    def test_default_analysis_depth(self):
        """默认分析深度"""
        spec = PlanSpec(task="分析")
        assert spec.analysis_depth == "detailed"

    def test_default_output_format(self):
        """默认输出格式"""
        spec = PlanSpec(task="分析")
        assert spec.output_format == "structured"

    def test_default_target_scope(self):
        """默认目标范围"""
        spec = PlanSpec(task="分析")
        assert spec.target_scope is None


class TestPlanSpecMode:
    """PlanSpec 模式测试"""

    def test_mode_is_explore(self):
        """规划模式复用 EXPLORE"""
        spec = PlanSpec(task="深度分析")
        assert spec.mode == SubagentMode.EXPLORE


class TestPlanSpecInstructions:
    """PlanSpec 指令生成测试"""

    def test_instructions_contains_planning_mode(self):
        """指令包含规划模式标记"""
        spec = PlanSpec(task="分析用户认证模块")
        instructions = spec.get_instructions()
        
        assert "规划模式" in instructions
        assert "只读分析" in instructions

    def test_instructions_contains_task(self):
        """指令包含任务描述"""
        spec = PlanSpec(task="分析支付模块")
        instructions = spec.get_instructions()
        
        assert "分析支付模块" in instructions

    def test_instructions_default_scope(self):
        """默认范围是整个代码库"""
        spec = PlanSpec(task="分析")
        instructions = spec.get_instructions()
        
        assert "整个代码库" in instructions

    def test_instructions_with_target_scope(self):
        """自定义目标范围"""
        spec = PlanSpec(
            task="安全审计",
            target_scope=["src/auth/", "src/payment/"]
        )
        instructions = spec.get_instructions()
        
        assert "src/auth/" in instructions
        assert "src/payment/" in instructions

    def test_instructions_readonly_warning(self):
        """指令包含只读警告"""
        spec = PlanSpec(task="分析")
        instructions = spec.get_instructions()
        
        assert "只读模式" in instructions
        assert "禁止" in instructions

    def test_instructions_depth_brief(self):
        """分析深度：简要"""
        spec = PlanSpec(task="分析", analysis_depth="brief")
        instructions = spec.get_instructions()
        
        assert "简要" in instructions
        assert "快速概览" in instructions

    def test_instructions_depth_detailed(self):
        """分析深度：详细"""
        spec = PlanSpec(task="分析", analysis_depth="detailed")
        instructions = spec.get_instructions()
        
        assert "详细" in instructions
        assert "主要组件" in instructions

    def test_instructions_depth_comprehensive(self):
        """分析深度：全面"""
        spec = PlanSpec(task="分析", analysis_depth="comprehensive")
        instructions = spec.get_instructions()
        
        assert "全面" in instructions
        assert "深入每个细节" in instructions

    def test_instructions_format_brief(self):
        """输出格式：简要 - 验证 format 正确反映"""
        spec = PlanSpec(task="分析", output_format="brief")
        instructions = spec.get_instructions()
        
        # Fixed: output_format 正确反映在指令中
        assert "简要" in instructions
        assert "500 字以内" in instructions

    def test_instructions_format_structured(self):
        """输出格式：结构化 - 验证 format 正确反映"""
        spec = PlanSpec(task="分析", output_format="structured")
        instructions = spec.get_instructions()
        
        # Fixed: output_format 正确反映在指令中
        assert "结构化" in instructions
        assert "1000 字以内" in instructions

    def test_instructions_format_markdown(self):
        """输出格式：完整 Markdown - 验证 format 正确反映"""
        spec = PlanSpec(task="分析", output_format="markdown")
        instructions = spec.get_instructions()
        
        # Fixed: output_format 正确反映在指令中
        assert "完整 Markdown" in instructions


class TestPlanSpecReportStructure:
    """规划报告结构测试"""

    def test_instructions_contains_required_sections(self):
        """指令要求包含必需章节"""
        spec = PlanSpec(task="分析")
        instructions = spec.get_instructions()
        
        assert "发现总结" in instructions
        assert "代码结构" in instructions
        assert "建议行动" in instructions

    def test_instructions_optional_sections(self):
        """指令包含可选章节"""
        spec = PlanSpec(task="分析")
        instructions = spec.get_instructions()
        
        assert "关键洞察" in instructions
        assert "潜在问题" in instructions


class TestPlanSpecValidation:
    """PlanSpec 结果验证测试"""

    def test_validate_result_valid_long(self):
        """有效结果：足够长"""
        spec = PlanSpec(task="分析")
        result = "这是一个有效的分析结果，包含了很多详细的内容和发现总结，以及代码结构的描述，还有建议行动。"
        
        assert spec.validate_result(result) is True

    def test_validate_result_valid_with_sections(self):
        """有效结果：包含必需章节"""
        spec = PlanSpec(task="分析")
        result = """
        ## 1. 发现总结
        分析完成
        
        ## 2. 代码结构
        包含主要模块
        
        ## 3. 建议行动
        建议下一步
        """
        
        assert spec.validate_result(result) is True

    def test_validate_result_invalid_none(self):
        """无效结果：None"""
        spec = PlanSpec(task="分析")
        assert spec.validate_result(None) is False

    def test_validate_result_invalid_short(self):
        """无效结果：太短"""
        spec = PlanSpec(task="分析")
        assert spec.validate_result("太短") is False

    def test_validate_result_invalid_empty(self):
        """无效结果：空字符串"""
        spec = PlanSpec(task="分析")
        assert spec.validate_result("") is False


class TestPlanSpecCustomConfig:
    """PlanSpec 自定义配置测试"""

    def test_custom_timeout(self):
        """自定义超时"""
        spec = PlanSpec(task="深度分析", timeout=900)
        assert spec.timeout == 900

    def test_custom_max_cost(self):
        """自定义最大开销"""
        spec = PlanSpec(task="分析", max_cost=100000)
        assert spec.max_cost == 100000

    def test_all_custom_params(self):
        """全自定义参数"""
        spec = PlanSpec(
            task="全面安全审计",
            timeout=1200,
            max_cost=100000,
            target_scope=["src/security/", "src/auth/"],
            analysis_depth="comprehensive",
            output_format="markdown"
        )
        
        assert spec.timeout == 1200
        assert spec.max_cost == 100000
        assert spec.target_scope == ["src/security/", "src/auth/"]
        assert spec.analysis_depth == "comprehensive"
        assert spec.output_format == "markdown"


class TestPlanSpecIntegration:
    """PlanSpec 集成测试"""

    def test_full_spec_to_instructions(self):
        """完整规格生成指令"""
        spec = PlanSpec(
            task="分析订单处理模块",
            timeout=600,
            max_cost=50000,
            target_scope=["src/order/", "src/payment/"],
            analysis_depth="detailed",
            output_format="structured"
        )
        
        instructions = spec.get_instructions()
        
        assert "分析订单处理模块" in instructions
        assert "src/order/" in instructions
        assert "详细" in instructions
        assert "只读模式" in instructions

    def test_roundtrip_validation(self):
        """生成 - 验证往返"""
        spec = PlanSpec(task="代码审计")
        
        valid_report = """
        ## 1. 发现总结
        审计发现 3 个安全问题
        
        ## 2. 代码结构
        模块 A 依赖模块 B
        
        ## 3. 建议行动
        修复 SQL 注入
        """
        
        assert spec.validate_result(valid_report) is True

    def test_explore_vs_plan_comparison(self):
        """探索模式 vs 规划模式对比"""
        from src.subagent.explore_spec import ExploreSpec
        
        explore = ExploreSpec(task="快速查找")
        plan = PlanSpec(task="深度分析")
        
        # Explore 应该更快/成本更低
        assert explore.timeout < plan.timeout  # 300 < 600
        assert explore.max_cost < plan.max_cost  # 30000 < 50000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
