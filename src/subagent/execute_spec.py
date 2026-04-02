"""
执行模式规格 (ExecuteSpec)
精确、可写、长时间，适合需要修改文件的复杂任务
"""

from dataclasses import dataclass, field
from typing import Optional, List
from src.subagent.subagent_spec import SubagentMode, SubagentSpec


@dataclass
class ExecuteSpec(SubagentSpec):
    """执行模式规格"""
    timeout: int = 3600         # 60分钟
    max_cost: int = 100000     # 100k token上限

    # 执行专用字段
    target_files: Optional[List[str]] = None    # 目标文件
    expected_outcome: Optional[str] = None      # 预期结果
    verification_method: Optional[str] = None   # 验证方法

    @property
    def mode(self) -> SubagentMode:
        return SubagentMode.EXECUTE

    def get_instructions(self) -> str:
        target_files_str = self.target_files if self.target_files else "未指定"
        expected_outcome_str = self.expected_outcome if self.expected_outcome else "未指定"
        verification_str = self.verification_method if self.verification_method else "未指定"

        return f"""【执行模式】
任务：{self.task}
目标文件：{target_files_str}
预期结果：{expected_outcome_str}
验证方法：{verification_str}

要求：
- 精确修改指定文件
- 完成修改后执行验证
- 如果无法完成，说明原因

输出格式：
- 完成的修改
- 验证结果
- 如未完成，说明原因和已尝试的方案"""

    def validate_result(self, result) -> bool:
        # 检查是否完成了预期结果
        if self.expected_outcome:
            return self.expected_outcome in str(result)
        return result is not None and len(result) > 0
