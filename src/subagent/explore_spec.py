"""
探索模式规格 (ExploreSpec)
只读、快速、低成本，适合信息定位和初步探索
"""

from dataclasses import dataclass
from src.subagent.subagent_spec import SubagentMode, SubagentSpec


@dataclass
class ExploreSpec(SubagentSpec):
    """探索模式规格"""
    timeout: int = 300          # 5分钟上限
    max_cost: int = 30000       # 30k token上限

    @property
    def mode(self) -> SubagentMode:
        return SubagentMode.EXPLORE

    def get_instructions(self) -> str:
        return f"""【探索模式】
任务：{self.task}
要求：
- 只读，不修改任何文件
- 快速定位信息，不深度实现
- 如果3次搜索找不到目标，换策略
- {self.timeout // 60}分钟内必须产出

输出格式：
- 找到的信息
- 未能找到的信息
- 建议的下一步"""

    def validate_result(self, result) -> bool:
        return result is not None and len(result) > 0
