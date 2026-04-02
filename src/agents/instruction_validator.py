"""InstructionSelfContainValidator - 指令自包含验证Hook (V3.0 Phase 1)

Phase 1 重点功能：检查工具调用参数是否包含完整上下文。

问题背景：
LLM生成的工具调用参数可能包含指代性引用，如"上文"、"上面"、"之前"等，
这些引用在单独执行时没有完整上下文，导致工具执行失败。

验证规则：
1. 参数中不能包含"上文"、"上面"、"之前"、"刚才"、"以下"等指代词
2. 参数必须是完整的、可以直接执行的值
3. 如果参数引用了其他工具的结果，必须显式说明

使用示例：
    validator = InstructionSelfContainValidator()
    runner = AgentRunner(
        llm_client=client,
        tools=tools,
        hooks=[validator]
    )
"""

import re
import logging
from typing import Optional

from src.hooks.hook import AgentHook
from src.hooks.hook_context import AgentHookContext

logger = logging.getLogger(__name__)


class InstructionNotSelfContainedError(Exception):
    """
    指令不自包含错误

    当工具调用参数包含不完整引用时抛出此异常。
    """

    def __init__(self, message: str, tool_name: str = "", param_name: str = "", problematic_value: str = ""):
        super().__init__(message)
        self.tool_name = tool_name
        self.param_name = param_name
        self.problematic_value = problematic_value

    def to_dict(self) -> dict:
        return {
            "error": "InstructionNotSelfContained",
            "message": str(self),
            "tool_name": self.tool_name,
            "param_name": self.param_name,
            "problematic_value": self.problematic_value,
        }


class InstructionSelfContainValidator(AgentHook):
    """
    指令自包含验证Hook

    在 before_execute_tools 阶段检查工具调用参数是否包含完整上下文。

    检查项目：
    1. 关键词检查：检测指代性词汇
    2. 引用完整性：确保参数不是单纯的引用
    3. 上下文依赖：检测需要上文才能理解的参数

    配置项：
    - enabled: 是否启用（默认True）
    - strict_mode: 严格模式（检测到问题直接抛异常，默认False）
    - allowed_references: 允许的引用模式（可自定义）
    """

    name: str = "InstructionSelfContainValidator"
    priority: int = 10  # 高优先级，尽早检查
    enabled: bool = True

    # 指代性词汇模式（按优先级排序）
    # 注意：使用原始字符串，不带 ^ 锚点以检测字符串中任何位置的指代词
    PROBLEMATIC_PATTERNS = [
        # 明确指代上文的词（中文）
        r"上文|上面|之前|刚才|以下|上述|前述",  # 通用指代词
        r"根据上文|按照上文|依据上文",
        r"根据上面|按照上面",
        r"按之前|按照之前|依据之前",
        r"参照上文|参照上面",
        # 指代性表达
        r"这个表|那张表|该表",  # 指示代词 + 名词
        r"这个问题|那个问题|该问题",
        r"这项|该|此",
        r"上文所述|上述方法|之前的方法",
        # 英文指代
        r"\bthe (above|previous|mentioned| aforementioned)\b",
        r"\bas mentioned above\b",
        r"\bfrom above\b",
        r"\bpreviously stated\b",
    ]

    # 参数名中可能包含引用意图的
    SUSPICIOUS_PARAM_PATTERNS = [
        "reference",
        "previous",
        "above",
        "mentioned",
        "last",
        "prior",
        "context",
    ]

    def __init__(
        self,
        strict_mode: bool = False,
        allowed_patterns: list[str] | None = None,
        custom_keywords: list[str] | None = None,
    ):
        """
        初始化验证器

        Args:
            strict_mode: 严格模式（True时检测到问题抛异常）
            allowed_patterns: 自定义允许的模式（正则表达式列表）
            custom_keywords: 自定义关键词（会加入检测列表）
        """
        self.strict_mode = strict_mode
        self._allowed_patterns = allowed_patterns or []
        self._custom_keywords = custom_keywords or []

        # 构建完整的模式列表
        self._all_patterns = list(self.PROBLEMATIC_PATTERNS)

    def before_execute_tools(self, ctx: AgentHookContext) -> AgentHookContext:
        """
        检查工具调用参数是否自包含

        Args:
            ctx: Hook上下文（包含 tools_to_execute 列表）

        Returns:
            修改后的ctx（如果检测到问题且strict_mode=True会抛异常）
        """
        tools_to_exec = ctx.tools_to_execute or []

        if not tools_to_exec:
            return ctx

        errors = []

        for tool_spec in tools_to_exec:
            tool_name = tool_spec.get("name", "unknown")
            params = tool_spec.get("params", {})

            # 检查每个参数
            for param_name, param_value in params.items():
                issue = self._check_param(tool_name, param_name, param_value)
                if issue:
                    errors.append(issue)

                    if self.strict_mode:
                        ctx.set_blocked(f"指令不自包含: {issue}")
                        return ctx

        # 记录警告（但继续执行）
        if errors:
            error_summary = "; ".join(errors)
            ctx.add_warning(f"[InstructionSelfContainValidator] 检测到 {len(errors)} 个不自包含问题: {error_summary}")
            logger.warning(f"[InstructionSelfContainValidator] {error_summary}")

        return ctx

    def _check_param(self, tool_name: str, param_name: str, param_value: any) -> str | None:
        """
        检查单个参数是否自包含

        Args:
            tool_name: 工具名称
            param_name: 参数名称
            param_value: 参数值

        Returns:
            问题描述字符串，无问题返回None
        """
        # 空值跳过
        if param_value is None or param_value == "":
            return None

        # 非字符串值跳过
        if not isinstance(param_value, str):
            return None

        # 检查是否有指代性词汇
        for pattern in self._all_patterns:
            if isinstance(pattern, tuple):
                regex, keyword = pattern
            else:
                regex = pattern
                keyword = "指代性词汇"

            if re.search(regex, param_value, re.IGNORECASE):
                return f"工具 {tool_name} 参数 {param_name} 包含'{keyword}': {param_value[:50]}..."

        # 检查自定义关键词
        for keyword in self._custom_keywords:
            if keyword.lower() in param_value.lower():
                return f"工具 {tool_name} 参数 {param_name} 包含自定义关键词'{keyword}': {param_value[:50]}..."

        # 检查参数名是否可疑
        for suspicious in self.SUSPICIOUS_PARAM_PATTERNS:
            if suspicious in param_name.lower():
                # 参数名可疑，但值看起来正常就放行
                if not self._looks_like_reference(param_value):
                    return None
                return f"工具 {tool_name} 参数 {param_name} 看起来像引用而非实际值: {param_value[:50]}..."

        return None

    def _looks_like_reference(self, value: str) -> bool:
        """
        判断值是否看起来像引用而非实际值

        Args:
            value: 参数值

        Returns:
            True如果看起来像引用
        """
        # 短值且包含"上面"等词的
        if len(value) < 100 and re.search(r"上[文武]|之前|上面|刚才|该|此", value):
            return True

        # 大量使用代词
        pronoun_count = len(re.findall(r"这|那|其|此|该|它", value))
        if pronoun_count > 2:
            return True

        return False

    def add_allowed_pattern(self, pattern: str) -> None:
        """添加允许的模式（白名单）"""
        self._allowed_patterns.append(pattern)

    def add_custom_keyword(self, keyword: str) -> None:
        """添加自定义关键词"""
        self._custom_keywords.append(keyword)


class SelfJustificationGuard(AgentHook):
    """
    自我合理化防护Hook (Phase 4)

    检测Agent是否在"自我合理化"——声称任务已完成但实际未完成。
    用于防止Agent跳过必要步骤直接返回"完成"。

    检测信号：
    1. 频繁使用完成声明词
    2. 缺少具体执行细节
    3. 跳过验证步骤
    """

    name: str = "SelfJustificationGuard"
    priority: int = 20
    enabled: bool = True

    # 完成声明信号词
    COMPLETION_SIGNALS = [
        r"任务完成",
        r"已完成",
        r"全部完成",
        r"搞定",
        r"没问题了",
        r"已经处理完毕",
        r"执行成功",
    ]

    # 需要警惕的跳过信号
    SKIP_SIGNALS = [
        r"不需要",
        r"跳过",
        r"省略",
        r"暂不",
        r"先跳过",
        r"以后再说",
    ]

    def __init__(self, threshold: float = 0.7):
        """
        Args:
            threshold: 触发阈值（0-1），越高越严格
        """
        self.threshold = threshold

    def after_iteration(self, ctx: AgentHookContext) -> AgentHookContext:
        """检查是否在自我合理化"""
        response = ctx.llm_response or ctx.stream_chunk or ""

        if not response:
            return ctx

        # 统计完成声明词出现次数
        completion_count = 0
        for pattern in self.COMPLETION_SIGNALS:
            completion_count += len(re.findall(pattern, response))

        # 统计跳过信号
        skip_count = 0
        for pattern in self.SKIP_SIGNALS:
            skip_count += len(re.findall(pattern, response))

        # 检查是否有具体执行结果
        has_tool_results = len(ctx.tool_results) > 0 if ctx.tool_results else False
        has_concrete_output = len(response) > 100 and any(
            c in response for c in ["数据", "结果", "分析", "报告", "列表"]
        )

        # 自我合理化检测
        if completion_count >= 2 and not has_tool_results:
            ctx.add_warning(
                f"[SelfJustificationGuard] 检测到疑似自我合理化: "
                f"声明完成({completion_count}次)但无工具执行结果"
            )

        if completion_count >= 1 and skip_count >= 1 and not has_concrete_output:
            ctx.add_warning(
                f"[SelfJustificationGuard] 检测到疑似自我合理化: "
                f"声明完成但跳过验证且无具体输出"
            )

        return ctx


class TokenMonitorHook(AgentHook):
    """
    Token监控Hook (Phase 2)

    监控token消耗，在接近预算时发出警告。
    用于防止超过LLM上下文窗口。
    """

    name: str = "TokenMonitorHook"
    priority: int = 5  # 高优先级，尽早监控
    enabled: bool = True

    def __init__(self, warning_threshold: float = 0.8, critical_threshold: float = 0.95):
        """
        Args:
            warning_threshold: 警告阈值（比例）
            critical_threshold: 危险阈值（比例）
        """
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    def before_llm(self, ctx: AgentHookContext) -> AgentHookContext:
        """在LLM调用前检查token预算"""
        ratio = ctx.token_count / ctx.token_budget if ctx.token_budget > 0 else 0

        if ratio >= self.critical_threshold:
            ctx.add_warning(
                f"[TokenMonitor] Token使用率 {ratio:.1%} 超过危险阈值 {self.critical_threshold:.1%}，"
                "即将达到预算限制"
            )
            if ratio >= 1.0:
                ctx.set_blocked("Token预算已用尽")

        elif ratio >= self.warning_threshold:
            ctx.add_warning(
                f"[TokenMonitor] Token使用率 {ratio:.1%} 超过警告阈值 {self.warning_threshold:.1%}"
            )

        return ctx
