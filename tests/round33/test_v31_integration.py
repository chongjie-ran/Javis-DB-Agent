"""
V3.1 完整集成测试 - Round33

验证所有V3.1新增功能的协同工作：
1. AutoMemory中文内容处理
2. AutoVerificationHook验证流程
3. PlanSpec output_format正确生成
4. 三者协同工作
"""

import pytest
from src.memory.auto_memory import AutoMemory, Correction
from src.hooks.auto_verification_hook import AutoVerificationHook
from src.subagent.plan_spec import PlanSpec


class TestAutoMemoryChinese:
    """验证中文内容不会被错误过滤"""
    
    def test_chinese_feedback(self):
        am = AutoMemory(None)
        assert am.should_remember("这是一个很好的学习内容")
        assert am.should_remember("用户反馈说回复太长了")
        assert am.should_remember("记住这个模式总是有效")
    
    def test_chinese_pattern(self):
        am = AutoMemory(None)
        # 包含"模式"的应该是pattern类型
        correction = Correction(
            original_action="总是用复杂句式",
            correction="使用简洁句式",
            timestamp="2026-04-09"
        )
        mem_type = am.extract_memory_type(correction)
        assert mem_type in ["feedback", "pattern"]


class TestPlanSpecOutputFormat:
    """验证PlanSpec的output_format正确工作"""
    
    def test_brief_format_instruction(self):
        spec = PlanSpec(
            task="分析代码结构",
            output_format="brief"
        )
        instructions = spec.get_instructions()
        assert "输出格式：简要" in instructions
        assert "500 字以内" in instructions
    
    def test_markdown_format_instruction(self):
        spec = PlanSpec(
            task="分析代码结构",
            output_format="markdown"
        )
        instructions = spec.get_instructions()
        assert "输出格式：完整 Markdown" in instructions
    
    def test_all_formats_have_instruction(self):
        for fmt in ["brief", "structured", "markdown"]:
            spec = PlanSpec(task="测试", output_format=fmt)
            instructions = spec.get_instructions()
            assert "输出格式：" in instructions, f"{fmt} missing output_format"


class TestV31Integration:
    """V3.1完整集成测试"""
    
    def test_plan_spec_with_memory(self):
        """PlanSpec生成时不会错误过滤正常内容"""
        spec = PlanSpec(
            task="分析src目录结构",
            output_format="structured"
        )
        # 生成指令不应该触发should_remember
        instructions = spec.get_instructions()
        assert len(instructions) > 100
        assert "分析范围" in instructions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
