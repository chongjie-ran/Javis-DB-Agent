"""
执行模式规格 (ExecuteSpec)
精确、可写、长时间，适合需要修改文件的复杂任务

改进 (V3.1): 增强验证优先机制
- mandatory_verification: 强制验证标记
- 验证失败阻止提交
- 改进指令格式，强制包含验证步骤
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
    mandatory_verification: bool = True         # 强制验证（默认开启）

    @property
    def mode(self) -> SubagentMode:
        return SubagentMode.EXECUTE

    def get_instructions(self) -> str:
        target_files_str = self.target_files if self.target_files else "未指定"
        expected_outcome_str = self.expected_outcome if self.expected_outcome else "未指定"
        verification_str = self.verification_method if self.verification_method else "未指定"

        # 验证优先指令
        verification_priority = "⚠️【验证优先】你必须先完成验证，证明你的改动正确后才能报告完成。" if self.mandatory_verification else ""
        verification_block = f"""
【验证步骤】（必须执行）
验证方法: {verification_str}
预期结果: {expected_outcome_str}
{verification_priority}

完成标准：
1. 修改已应用到目标文件
2. 验证命令执行通过
3. 预期结果已确认""" if self.verification_method else """
【验证步骤】
- 完成后必须运行验证
- 记录验证结果
- 如验证失败，立即修复"""

        return f"""【执行模式】
任务：{self.task}
目标文件：{target_files_str}
{verification_block}

输出格式：
## 完成的修改
（列出具体修改了什么）

## 验证结果
（必须包含：执行的命令 + 输出 + 是否通过）

## 如未完成
（说明原因和已尝试的方案）

⚠️ 注意：未经验证的修改不能视为完成！"""

    def validate_result(self, result) -> bool:
        # 检查是否完成了预期结果
        if self.expected_outcome:
            return self.expected_outcome in str(result)
        return result is not None and len(result) > 0
    
    def has_verification(self) -> bool:
        """检查是否配置了验证方法"""
        return bool(self.verification_method)
    
    def requires_verification(self) -> bool:
        """检查是否需要验证"""
        return self.mandatory_verification or self.has_verification()
