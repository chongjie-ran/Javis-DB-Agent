"""
探索模式规格 (ExploreSpec) - P1改进

Claude Code Explore模式：只读、快速、低成本

改进点（V3.1）：
- 增强只读约束（显式禁止写操作）
- 结构化探索报告输出
- 快速失败策略（3次搜索失败换策略）
"""

from dataclasses import dataclass
from typing import Optional, List
from src.subagent.subagent_spec import SubagentMode, SubagentSpec


@dataclass
class ExploreSpec(SubagentSpec):
    """探索模式规格"""
    timeout: int = 300          # 5分钟上限
    max_cost: int = 30000       # 30k token上限

    # 探索专用字段
    search_paths: Optional[List[str]] = None    # 优先搜索路径
    search_keywords: Optional[List[str]] = None  # 搜索关键词
    exploration_type: str = "information"        # 探索类型: information/config/code/architecture

    @property
    def mode(self) -> SubagentMode:
        return SubagentMode.EXPLORE

    def get_instructions(self) -> str:
        search_paths_str = ", ".join(self.search_paths) if self.search_paths else "整个代码库"
        search_keywords_str = ", ".join(self.search_keywords) if self.search_keywords else "无"
        exploration_type_instruction = self._get_type_instruction()

        return f"""【探索模式 - 只读快速定位】
任务：{self.task}
搜索范围：{search_paths_str}
搜索关键词：{search_keywords_str}
{exploration_type_instruction}

⚠️【强制规则】只读模式
- 禁止创建、修改、删除任何文件
- 禁止执行任何可能修改代码的命令
- 如需修改，通过主Agent执行

策略要求：
- 使用快速搜索定位信息
- {self.timeout // 60}分钟内必须产出
- 3次搜索失败后换策略

{exploration_type_instruction}

探索报告格式：
## 找到的信息
- 信息1：[具体内容]
- 信息2：[具体内容]

## 未能找到的信息
（如有）

## 建议的下一步
（供主Agent参考的后续行动）
"""

    def _get_type_instruction(self) -> str:
        types = {
            "information": "探索类型：信息定位（快速查找文档、配置、注释）",
            "config": "探索类型：配置分析（查找配置项、环境变量、参数）",
            "code": "探索类型：代码定位（查找函数、类、变量定义）",
            "architecture": "探索类型：架构分析（查找模块关系、依赖、接口）",
        }
        return types.get(self.exploration_type, types["information"])

    def validate_result(self, result) -> bool:
        return result is not None and len(result) > 0
