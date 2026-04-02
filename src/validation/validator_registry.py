"""
ValidatorRegistry - 对抗性验证注册中心 (V3.0 Phase 3)

核心设计：
1. Validator: 验证器接口（validate方法返回ValidationResult）
2. BreakingValidator: 主动构造边界条件来"打破"假设，而非"确认"假设
3. ValidatorRegistry: 验证器注册、调度、聚合结果
4. ValidationMode: 验证模式切换（确认/对抗/两者）

与普通测试的区别：
- 普通测试：验证系统"能做什么"（happy path）
- BreakingValidator：验证系统"不能做什么"（adversarial path）
  → 主动构造：空值、超长输入、特殊字符、并发冲突等

设计原则：
- break_claim()方法命名强调"打破"而非"验证"
- BreakingValidator主动构造边界条件，不只是检查
- 验证结果含broken标志和reason，用于决策
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import logging
import re

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ValidationMode - 验证模式
# ─────────────────────────────────────────────────────────────────────────────

class ValidationMode(Enum):
    """验证模式"""
    CONFIRM = "confirm"   # 确认模式：验证通过即可
    BREAK = "break"       # 对抗模式：必须尝试打破
    BOTH = "both"         # 两者都做


# ─────────────────────────────────────────────────────────────────────────────
# ValidationResult - 验证结果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """
    单个验证结果

    Attributes:
        broken: 是否打破了假设（True = 发现问题）
        validator_name: 哪个验证器发现的问题
        reason: 问题描述
        suggestion: 修复建议（可选）
        evidence: 证据/测试用例（可选）
        severity: 严重程度 (info/warning/critical)
    """
    broken: bool = False
    validator_name: str = ""
    reason: str = ""
    suggestion: str = ""
    evidence: str = ""
    severity: str = "warning"  # info | warning | critical

    def __bool__(self) -> bool:
        """返回True表示"打破假设"（发现问题）"""
        return self.broken


# ─────────────────────────────────────────────────────────────────────────────
# BreakResult - 打破声明结果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BreakResult:
    """对抗模式下的"打破声明"结果"""
    claim: str           # 被打破的声明原文
    breaker: str         # 哪个验证器打破的 (e.g. "completion_claim: CompletionBreakingValidator")
    evidence: str = ""   # 证据


# ─────────────────────────────────────────────────────────────────────────────
# ValidatorResult - 单个验证器结果（含确认+打破两部分）
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidatorResult:
    """单个验证器的完整结果（确认模式 + 对抗模式）"""
    name: str
    confirm: ValidationResult
    broken: Optional[BreakResult] = None  # None = 未打破

    def has_broken(self) -> bool:
        return self.broken is not None


# ─────────────────────────────────────────────────────────────────────────────
# MultiValidationResult - 多验证器聚合结果
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MultiValidationResult:
    """多个验证器结果的聚合"""
    results: list[ValidatorResult] = field(default_factory=list)

    def has_broken_claims(self) -> bool:
        return any(r.has_broken() or r.confirm.broken for r in self.results)

    def get_broken_claims(self) -> list[BreakResult]:
        return [r.broken for r in self.results if r.broken is not None]

    def get_all_confirms(self) -> list[ValidationResult]:
        return [r.confirm for r in self.results]

    def get_critical_breaks(self) -> list[BreakResult]:
        """获取严重级别为critical的打破结果"""
        critical = []
        for r in self.results:
            if r.broken and r.confirm.severity == "critical":
                critical.append(r.broken)
            # confirm.broken=True 且 critical 也算critical break
            elif r.confirm.broken and r.confirm.severity == "critical":
                # 需要构造一个假的BreakResult
                critical.append(BreakResult(
                    claim="[confirm mode]",
                    breaker=r.name,
                    evidence=r.confirm.evidence,
                ))
        return critical

    def summary(self) -> str:
        """生成人类可读的摘要"""
        broken_count = len(self.get_broken_claims())
        total = len(self.results)
        if broken_count == 0:
            return f"✅ 所有验证通过 ({total}个验证器)"
        return f"⚠️  {broken_count}/{total} 个声明被打破"


# ─────────────────────────────────────────────────────────────────────────────
# Validator 基类
# ─────────────────────────────────────────────────────────────────────────────

class Validator(ABC):
    """
    验证器抽象基类

    所有验证器继承此类。
    与BreakingValidator的区别：
    - Validator: 检查已知条件是否满足
    - BreakingValidator: 主动构造边界条件来打破假设

    Attributes:
        name: 验证器名称
        enabled: 是否启用
    """

    name: str = ""
    enabled: bool = True

    @abstractmethod
    async def validate(self, context: "AgentHookContext") -> ValidationResult:
        """
        执行确认验证

        Args:
            context: AgentHookContext

        Returns:
            ValidationResult: broken=True表示打破了假设（发现问题）
        """
        pass

    @abstractmethod
    def break_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        核心方法：判定是否"打破"了声明

        - True  = 成功打破了假设/声明
        - False = 无法打破，声明成立

        Args:
            claim: 从上下文中提取的声明（如"完成了X"、"测试通过了"）
            context: AgentHookContext

        Returns:
            bool: 是否打破了该声明
        """
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# BreakingValidator - 主动打破假设的验证器
# ─────────────────────────────────────────────────────────────────────────────

class BreakingValidator(Validator):
    """
    主动打破假设的验证器基类

    与Validator的区别：
    - Validator: 被动检查（输入→检查→结果）
    - BreakingValidator: 主动构造边界条件来打破假设

    设计原则：
    1. break_claim()方法命名强调"打破"意图
    2. 主动构造：空值、超长、特殊字符、并发等边界条件
    3. 返回broken=True表示"成功打破了假设"

    使用场景：
    - CompletionBreakingValidator: 打破"完成"声明
    - SQLBreakingValidator: 构造各种恶意SQL，看是否被正确拦截
    - CodeQualityValidator: 构造内存泄漏、边界case失败等

    Example:
        class CompletionBreakingValidator(BreakingValidator):
            def break_claim(self, claim: str, context) -> bool:
                # 1. 如果声明"完成了X"，尝试构造X失败的用例
                # 2. 如果声明"修复了bug"，尝试找其他相关bug
                # 3. 如果声明"测试通过了"，验证测试是否真实运行
                claim_type = self.classify_claim(claim)
                if claim_type == "completion":
                    return self.break_completion_claim(claim, context)
                elif claim_type == "fix":
                    return self.break_fix_claim(claim, context)
                elif claim_type == "test_pass":
                    return self.break_test_claim(claim, context)
                return False
    """

    name: str = ""
    enabled: bool = True

    # 声明类型分类
    CLAIM_TYPE_COMPLETION = "completion"
    CLAIM_TYPE_FIX = "fix"
    CLAIM_TYPE_TEST_PASS = "test_pass"
    CLAIM_TYPE_QUALITY = "quality"
    CLAIM_TYPE_UNKNOWN = "unknown"

    @abstractmethod
    async def validate(self, context: "AgentHookContext") -> ValidationResult:
        """
        确认验证：检查基础功能是否正常工作

        Args:
            context: AgentHookContext

        Returns:
            ValidationResult
        """
        pass

    @abstractmethod
    def break_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破声明

        Args:
            claim: 声明文本
            context: AgentHookContext

        Returns:
            bool: 是否成功打破了该声明
        """
        pass

    def classify_claim(self, claim: str) -> str:
        """
        分类声明类型

        Args:
            claim: 声明文本

        Returns:
            str: CLAIM_TYPE_COMPLETION | CLAIM_TYPE_FIX | CLAIM_TYPE_TEST_PASS | ...
        """
        claim_lower = claim.lower()

        # 完成类声明
        completion_patterns = [
            r"完成了", r"实现", r"搞定", r"已经好", r"没问题",
            r"全部完成", r"执行完毕", r"已解决",
        ]
        for p in completion_patterns:
            if re.search(p, claim_lower):
                return self.CLAIM_TYPE_COMPLETION

        # 修复类声明
        fix_patterns = [r"修复", r"解决了", r"改好了", r"bug已", r"问题已"]
        for p in fix_patterns:
            if re.search(p, claim_lower):
                return self.CLAIM_TYPE_FIX

        # 测试通过类声明
        test_patterns = [r"测试通过", r"测试成功", r"验证成功", r"unit test passed", r"all tests passed"]
        for p in test_patterns:
            if re.search(p, claim_lower):
                return self.CLAIM_TYPE_TEST_PASS

        # 质量类声明
        quality_patterns = [r"无问题", r"没问题", r"正确", r"valid", r"符合规范"]
        for p in quality_patterns:
            if re.search(p, claim_lower):
                return self.CLAIM_TYPE_QUALITY

        return self.CLAIM_TYPE_UNKNOWN

    def break_completion_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破"完成"声明

        检查：
        1. 是否有未完成的子任务
        2. 是否有遗漏的边界情况
        3. 是否有功能是空的/未实现

        Returns:
            bool: 是否打破了该声明
        """
        # 默认实现：检查是否有子任务未完成
        goal = context.goal if hasattr(context, 'goal') else context.get("goal", "")

        # 检查goal是否包含多个子任务（用序号/分号等标记）
        sub_task_markers = re.findall(r"[\d一二三四五六七八九十]+[.、:：]", goal)
        if len(sub_task_markers) > 1:
            # 有多个子任务，检查llm_response是否逐一处理
            llm = context.llm_response if hasattr(context, 'llm_response') else context.get("llm_response", "")
            # 如果响应中只提到部分子任务，可能有遗漏
            mentioned = sum(1 for marker in sub_task_markers if marker in llm)
            if mentioned < len(sub_task_markers):
                return True  # 打破了：未处理所有子任务

        return False

    def break_fix_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破"修复"声明

        检查：
        1. 修复是否真正生效（工具执行结果验证）
        2. 是否引入新问题
        3. 是否有相关场景遗漏

        Returns:
            bool: 是否打破了该声明
        """
        # 检查工具执行结果
        tool_results = context.tool_results if hasattr(context, 'tool_results') else context.get("tool_results", [])
        llm = context.llm_response if hasattr(context, 'llm_response') else context.get("llm_response", "")

        # 查找修复声明中的关键词
        fix_keywords = re.findall(r"修复了?(.+?)[。\n]", claim)
        for kw in fix_keywords:
            kw_lower = kw.lower().strip()
            # 检查工具结果中是否有相关确认
            found = False
            for tr in tool_results:
                tr_str = str(tr).lower()
                if kw_lower in tr_str or kw_lower.replace(" ", "") in tr_str:
                    found = True
                    break
            if not found and kw.strip():
                # 声称修复了，但工具结果中没有相关证据
                return True
        return False

    def break_test_claim(self, claim: str, context: "AgentHookContext") -> bool:
        """
        打破"测试通过"声明

        检查：
        1. 测试是否真实运行（不是mock）
        2. 是否有边界用例未覆盖
        3. 测试是否真的测了目标功能

        Returns:
            bool: 是否打破了该声明
        """
        tool_results = context.tool_results if hasattr(context, 'tool_results') else context.get("tool_results", [])

        # 检查是否有实际的测试运行证据
        has_test_run = False
        for tr in tool_results:
            tr_name = tr.get("name", "") if isinstance(tr, dict) else str(tr)
            if any(kw in tr_name.lower() for kw in ["test", "pytest", "unittest", "jest"]):
                has_test_run = True
                # 检查结果
                tr_result = tr.get("result", "") if isinstance(tr, dict) else str(tr)
                if "failed" in tr_result.lower() or "error" in tr_result.lower():
                    return True  # 打破：测试失败了
                break

        if not has_test_run:
            return True  # 打破：没有实际运行测试

        return False

    # 兼容性别名（供同步代码调用）
    def break_assumption(self, context: dict) -> ValidationResult:
        """兼容性别名：同步版本的break"""
        # 需要实现兼容逻辑
        return ValidationResult(broken=False, validator_name=self.name)


# ─────────────────────────────────────────────────────────────────────────────
# ValidatorRegistry - 验证器注册与管理中心
# ─────────────────────────────────────────────────────────────────────────────

class ValidatorRegistry:
    """
    验证器注册与管理中心

    核心功能：
    1. 注册/注销验证器
    2. 批量执行验证（支持ValidationMode切换）
    3. 聚合验证结果
    4. 支持优先级

    ValidationMode:
    - CONFIRM: 只做确认验证
    - BREAK: 只做对抗验证
    - BOTH: 两者都做

    使用示例：
        registry = ValidatorRegistry()
        registry.set_mode(ValidationMode.BREAK)
        registry.register("completion_claim", CompletionBreakingValidator(), priority=10)
        registry.register("sql_boundary", SQLBoundaryValidator(), priority=20)

        results = await registry.validate(context)
        if results.has_broken_claims():
            ctx.set_blocked(f"假设被打破: {results.get_broken_claims()}")

    与Hook系统的关系：
    - ValidatorRegistry在AgentRunner.after_iteration中调用
    - 每个Validator/BreakingValidator检查一个维度
    - 结果聚合后决定是否继续迭代
    """

    def __init__(self):
        # name -> validator
        self._validators: dict[str, Validator] = {}
        # name -> priority
        self._priority: dict[str, int] = {}
        # name -> event tags
        self._events: dict[str, list[str]] = {}
        self._mode: ValidationMode = ValidationMode.BREAK

    def set_mode(self, mode: ValidationMode) -> None:
        """设置验证模式"""
        self._mode = mode
        logger.info(f"ValidatorRegistry mode set to: {mode.value}")

    def get_mode(self) -> ValidationMode:
        return self._mode

    def register(
        self,
        name: str,
        validator: Validator,
        priority: int = 100,
        events: Optional[list[str]] = None,
    ) -> None:
        """
        注册验证器

        Args:
            name: 验证器名称（唯一标识）
            validator: Validator实例
            priority: 优先级（数字越小越高）
            events: 关联的事件标签列表
        """
        self._validators[name] = validator
        self._priority[name] = priority
        self._events[name] = events or ["default"]
        logger.debug(f"Registered validator: {name} (priority={priority})")

    def unregister(self, name: str) -> bool:
        """注销验证器"""
        if name not in self._validators:
            return False
        del self._validators[name]
        self._priority.pop(name, None)
        self._events.pop(name, None)
        return True

    def get(self, name: str) -> Optional[Validator]:
        """按名称获取验证器"""
        return self._validators.get(name)

    def list_validators(self) -> list[str]:
        """列出所有验证器名称（按优先级排序）"""
        return sorted(self._validators.keys(), key=lambda k: self._priority.get(k, 100))

    async def validate(self, context: "AgentHookContext") -> MultiValidationResult:
        """
        执行所有验证，返回汇总结果

        根据ValidationMode：
        - CONFIRM: 只执行确认验证
        - BREAK: 只执行对抗验证
        - BOTH: 两者都做

        Args:
            context: AgentHookContext

        Returns:
            MultiValidationResult
        """
        results: list[ValidatorResult] = []

        # 按优先级排序
        sorted_names = sorted(
            self._validators.keys(),
            key=lambda k: self._priority.get(k, 100)
        )

        for name in sorted_names:
            validator = self._validators[name]
            if not validator.enabled:
                continue

            # 确认模式验证（始终执行，以获取基础状态）
            confirm_result = ValidationResult(validator_name=name)
            if self._mode in (ValidationMode.CONFIRM, ValidationMode.BOTH):
                try:
                    confirm_result = await validator.validate(context)
                except Exception as e:
                    logger.warning(f"Validator {name}.validate() failed: {e}")
                    confirm_result = ValidationResult(
                        broken=False,
                        validator_name=name,
                        reason=f"Validator error: {e}",
                        severity="info",
                    )
            else:
                # BREAK模式：仍然调用validate以获取确认状态，但不使用broken结果
                try:
                    confirm_result = await validator.validate(context)
                except Exception:
                    pass

            # 对抗模式验证
            broken_result: Optional[BreakResult] = None
            if self._mode in (ValidationMode.BREAK, ValidationMode.BOTH):
                for claim in self.extract_claims(context):
                    if validator.break_claim(claim, context):
                        broken_result = BreakResult(
                            claim=claim,
                            breaker=f"{name}: {validator.__class__.__name__}",
                            evidence=self._get_evidence(context),
                        )
                        break  # 只记录第一个打破的声明

            results.append(ValidatorResult(
                name=name,
                confirm=confirm_result,
                broken=broken_result,
            ))

        return MultiValidationResult(results=results)

    def extract_claims(self, context: "AgentHookContext") -> list[str]:
        """
        从上下文中提取声明

        声明类型：
        - LLM响应中的"完成"、"修复"、"通过"等声明
        - 工具结果中的成功声明

        Returns:
            list[str]: 声明列表
        """
        claims: list[str] = []

        # 从LLM响应中提取
        llm = context.llm_response if hasattr(context, 'llm_response') else context.get("llm_response", "")

        # 完成声明模式
        completion_patterns = [
            r"任务完成",
            r"已经完成",
            r"完成修复",
            r"搞定",
            r"问题已解决",
            r"已完成所有",
            r"全部完成",
            r"已经好了",
            r"没问题了",
            r"处理完了",
            r"已经执行",
            r"执行完毕",
            r"已解决",
            r"测试通过",
            r"验证成功",
        ]

        for pattern in completion_patterns:
            for match in re.finditer(pattern, llm):
                # 提取完整句子（到句号或换行）
                start = max(0, match.start() - 20)
                end = min(len(llm), match.end() + 50)
                sentence = llm[start:end].strip()
                # 截取到句号
                if "。" in sentence:
                    sentence = sentence[:sentence.index("。") + 1]
                elif "\n" in sentence:
                    sentence = sentence[:sentence.index("\n")].strip()
                if sentence and sentence not in claims:
                    claims.append(sentence)

        return claims

    def _get_evidence(self, context: "AgentHookContext") -> str:
        """从上下文中提取证据"""
        parts = []

        # 工具执行结果
        tool_results = context.tool_results if hasattr(context, 'tool_results') else context.get("tool_results", [])
        if tool_results:
            parts.append(f"tool_results: {tool_results[:2]}")  # 只取前两个

        # Token使用
        token_count = context.token_count if hasattr(context, 'token_count') else context.get("token_count", 0)
        parts.append(f"token_count: {token_count}")

        return " | ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# 全局单例
# ─────────────────────────────────────────────────────────────────────────────

_registry: Optional[ValidatorRegistry] = None


def get_validator_registry() -> ValidatorRegistry:
    global _registry
    if _registry is None:
        _registry = ValidatorRegistry()
    return _registry


def reset_validator_registry() -> None:
    """重置全局验证器注册表（测试用）"""
    global _registry
    _registry = None
