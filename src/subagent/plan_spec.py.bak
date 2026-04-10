"""
规划模式规格 (PlanSpec) - P1改进

Claude Code Plan Mode: 只读探索，只分析不修改

与ExploreSpec的区别：
- ExploreSpec: 快速定位信息，5分钟上限
- PlanSpec: 深度分析+规划，允许更长时间

特点：
- 只读模式，禁止任何写操作
- 输出结构化探索报告
- 包含建议的后续行动
"""

from dataclasses import dataclass
from typing import Optional, List
from src.subagent.subagent_spec import SubagentMode, SubagentSpec


@dataclass
class PlanSpec(SubagentSpec):
    """规划模式规格"""
    timeout: int = 600          # 10分钟上限（比Explore更长）
    max_cost: int = 50000       # 50k token上限

    # 规划专用字段
    target_scope: Optional[List[str]] = None    # 分析范围
    analysis_depth: str = "detailed"            # 分析深度: brief/detailed/comprehensive
    output_format: str = "structured"            # 输出格式: brief/structured/markdown

    @property
    def mode(self) -> SubagentMode:
        return SubagentMode.EXPLORE  # 复用EXPLORE模式（都是只读）

    def get_instructions(self) -> str:
        target_scope_str = ", ".join(self.target_scope) if self.target_scope else "整个代码库"
        analysis_depth_instruction = self._get_depth_instruction()
        output_format_instruction = self._get_format_instruction()

        return f"""【规划模式 - 只读分析】
任务：{self.task}
分析范围：{target_scope_str}
{analysis_depth_instruction}

⚠️【强制规则】只读模式
- 禁止创建、修改、删除任何文件
- 禁止执行可能修改代码的命令（如sed -i, git commit等）
- 如需修改，建议通过主Agent执行

{output_format_instruction}

探索报告格式：
## 1. 发现总结
（用2-3句话总结关键发现）

## 2. 代码结构
（关键文件、类、函数的关系）

## 3. 关键洞察
- 发现1：[具体说明]
- 发现2：[具体说明]

## 4. 潜在问题
（如有）

## 5. 建议行动
基于分析，建议的下一步行动（供主Agent参考）
"""

    def _get_depth_instruction(self) -> str:
        depths = {
            "brief": "分析深度：简要（快速概览，不深入细节）",
            "detailed": "分析深度：详细（覆盖主要组件和关系）",
            "comprehensive": "分析深度：全面（深入每个细节，包括边缘情况）",
        }
        return depths.get(self.analysis_depth, depths["detailed"])

    def _get_format_instruction(self) -> str:
        formats = {
            "brief": "输出格式：简要（纯文本，500字以内）",
            "structured": "输出格式：结构化（Markdown段落，1000字以内）",
            "markdown": "输出格式：完整Markdown（标题+列表+代码块，可更长）",
        }
        return formats.get(self.output_format, formats["structured"])

    def validate_result(self, result) -> bool:
        # 检查是否完成了规划任务
        if not result or len(result) < 30:
            return False

        # 检查是否包含结构化输出
        required_sections = ["发现总结", "代码结构", "建议行动"]
        result_str = str(result)
        return any(section in result_str for section in required_sections)
