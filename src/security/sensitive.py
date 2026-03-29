"""敏感数据脱敏模块"""
import re
import json
import copy
from typing import Any, Optional, Callable, Union
from dataclasses import dataclass
from functools import wraps


# 需要脱敏的字段模式（不区分大小写）
SENSITIVE_FIELD_PATTERNS: list[re.Pattern] = [
    re.compile(r"^.*password.*$", re.I),
    re.compile(r"^.*secret.*$", re.I),
    re.compile(r"^.*token.*$", re.I),
    re.compile(r"^.*api[_-]?key.*$", re.I),
    re.compile(r"^.*credential.*$", re.I),
    re.compile(r"^.*auth.*$", re.I),
    re.compile(r"^.*private[_-]?key.*$", re.I),
    re.compile(r"^.*access[_-]?token.*$", re.I),
    re.compile(r"^.*refresh[_-]?token.*$", re.I),
    re.compile(r"^.*bearer.*$", re.I),
    re.compile(r"^.*authorization.*$", re.I),
    re.compile(r"^.*ssn.*$", re.I),          # 社保号
    re.compile(r"^.*credit[_-]?card.*$", re.I),
    re.compile(r"^.*card[_-]?number.*$", re.I),
    re.compile(r"^.*cvv.*$", re.I),
    re.compile(r"^.*pin.*$", re.I),
    re.compile(r"^.*salt.*$", re.I),          # 密码盐
]

# IP地址脱敏模式
IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")
# 邮箱脱敏模式
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
# 手机号脱敏模式（中国大陆）
PHONE_PATTERN = re.compile(r"\b1[3-9]\d{9}\b")


def _is_sensitive_field(key: str) -> bool:
    """判断字段名是否为敏感字段"""
    key_lower = key.lower()
    for pattern in SENSITIVE_FIELD_PATTERNS:
        if pattern.match(key_lower):
            return True
    return False


def mask_value(value: str, show_last: int = 4, mask_char: str = "*") -> str:
    """对敏感值进行脱敏"""
    if not value:
        return value
    if len(value) <= show_last:
        return mask_char * len(value)
    return mask_char * (len(value) - show_last) + value[-show_last:]


def mask_ip(ip: str) -> str:
    """脱敏IP地址（前两段），非IP字符串返回固定掩码"""
    parts = ip.split(".")
    if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
        return f"{parts[0]}.{parts[1]}.*.{parts[3]}"
    return "****"  # 非IP字符串不透露长度


def mask_email(email: str) -> str:
    """脱敏邮箱"""
    if "@" not in email:
        return mask_value(email, show_last=3)
    local, domain = email.rsplit("@", 1)
    if len(local) <= 2:
        local_masked = mask_value(local, show_last=0)
    else:
        local_masked = local[0] + "*" * (len(local) - 2) + local[-1]
    return f"{local_masked}@{domain}"


def mask_phone(phone: str) -> str:
    """脱敏手机号（保留前3后4）"""
    if len(phone) < 7:
        return mask_value(phone, show_last=0)
    return phone[:3] + "****" + phone[-4:]


@dataclass
class MaskRule:
    """自定义脱敏规则"""
    field: str
    mask_type: Literal["full", "partial", "last4", "none"] = "partial"
    show_chars: int = 0


class SensitiveDataMask:
    """
    敏感数据脱敏器
    
    功能：
    1. 自动识别敏感字段并脱敏
    2. 支持自定义脱敏规则
    3. 支持深拷贝（不修改原始数据）
    4. 递归处理嵌套字典/列表
    """
    
    # 默认保留显示的字符数
    DEFAULT_SHOW_LAST = 4
    
    def __init__(self, custom_rules: Optional[list[MaskRule]] = None):
        self.custom_rules: dict[str, MaskRule] = {}
        if custom_rules:
            for rule in custom_rules:
                self.custom_rules[rule.field.lower()] = rule
    
    def _get_rule(self, key: str) -> Optional[MaskRule]:
        return self.custom_rules.get(key.lower())
    
    def _apply_mask(self, value: Any, key: str, show_last: int = DEFAULT_SHOW_LAST) -> Any:
        """对单个值应用脱敏"""
        rule = self._get_rule(key)
        if rule:
            if rule.mask_type == "full":
                return "***REDACTED***"
            elif rule.mask_type == "partial":
                if isinstance(value, str):
                    return mask_value(value, show_last=rule.show_chars or show_last)
                return value
            elif rule.mask_type == "last4":
                if isinstance(value, str):
                    return mask_value(value, show_last=4)
                return value
            else:  # none
                return value
        
        # 默认：自动识别
        if isinstance(value, str):
            return mask_value(value, show_last=show_last)
        return value
    
    def mask_dict(self, data: dict, show_last: int = DEFAULT_SHOW_LAST) -> dict:
        """脱敏字典中的敏感字段"""
        result = copy.deepcopy(data)
        for key, value in result.items():
            if isinstance(value, dict):
                # 字典/列表始终递归处理（即使key看起来敏感）
                result[key] = self.mask_dict(value, show_last)
            elif isinstance(value, list):
                result[key] = self.mask_list(value, show_last)
            elif _is_sensitive_field(key):
                # 仅对非容器类型的值应用掩码
                result[key] = self._apply_mask(value, key, show_last)
        return result
    
    def mask_list(self, data: list, show_last: int = DEFAULT_SHOW_LAST) -> list:
        """脱敏列表中的敏感字段"""
        result = []
        for item in data:
            if isinstance(item, dict):
                result.append(self.mask_dict(item, show_last))
            else:
                result.append(item)
        return result
    
    def mask(self, data: Any, show_last: int = DEFAULT_SHOW_LAST) -> Any:
        """
        统一入口：自动识别类型并脱敏
        
        Args:
            data: 待脱敏数据（dict/list/str等）
            show_last: 部分脱敏时保留的末尾字符数
        """
        if isinstance(data, dict):
            return self.mask_dict(data, show_last)
        elif isinstance(data, list):
            return self.mask_list(data, show_last)
        elif isinstance(data, str) and _is_sensitive_field("value"):
            return mask_value(data, show_last=show_last)
        return data
    
    def mask_ip_addresses(self, data: Union[str, dict, list]) -> Any:
        """专门脱敏IP地址"""
        if isinstance(data, str):
            return IP_PATTERN.sub(lambda m: mask_ip(m.group()), data)
        elif isinstance(data, dict):
            result = {}
            for k, v in data.items():
                if k.lower() in ("ip", "ip_address", "client_ip", "remote_addr"):
                    result[k] = IP_PATTERN.sub(lambda m: mask_ip(m.group()), str(v)) if v else v
                else:
                    result[k] = self.mask_ip_addresses(v)
            return result
        elif isinstance(data, list):
            return [self.mask_ip_addresses(item) for item in data]
        return data
    
    def mask_pii(self, data: Any) -> Any:
        """
        脱敏PII（个人身份信息）
        
        包括：邮箱、手机、IP地址
        """
        if isinstance(data, str):
            data = EMAIL_PATTERN.sub(lambda m: mask_email(m.group()), data)
            data = PHONE_PATTERN.sub(lambda m: mask_phone(m.group()), data)
            data = IP_PATTERN.sub(lambda m: mask_ip(m.group()), data)
            return data
        elif isinstance(data, dict):
            result = {}
            for k, v in data.items():
                if isinstance(v, str):
                    v = EMAIL_PATTERN.sub(lambda m: mask_email(m.group()), v)
                    v = PHONE_PATTERN.sub(lambda m: mask_phone(m.group()), v)
                    v = IP_PATTERN.sub(lambda m: mask_ip(m.group()), v)
                result[k] = self.mask_pii(v)
            return result
        elif isinstance(data, list):
            return [self.mask_pii(item) for item in data]
        return data


# 全局单例
_masker: Optional[SensitiveDataMask] = None


def get_masker() -> SensitiveDataMask:
    global _masker
    if _masker is None:
        _masker = SensitiveDataMask()
    return _masker


def mask_sensitive_data(data: Any, show_last: int = 4) -> Any:
    """
    快捷函数：对数据进行敏感数据脱敏
    """
    return get_masker().mask(data, show_last=show_last)


# ---- 装饰器：API响应自动脱敏 ----

def mask_response_fields(*fields: str):
    """
    装饰器：自动脱敏响应中的指定字段
    
    Usage:
        @mask_response_fields("password", "api_key", "token")
        async def get_user():
            return {"password": "secret123", "api_key": "key123"}
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            if isinstance(result, dict):
                for field in fields:
                    if field in result:
                        result[field] = "***REDACTED***"
            return result
        return wrapper
    return decorator


def mask_audit_log(log_entry: dict) -> dict:
    """
    对审计日志进行脱敏处理
    
    脱敏规则：
    1. 敏感字段（password, token, api_key等）完全掩码
    2. IP地址部分掩码
    3. 邮箱/手机号部分掩码
    4. params中的敏感参数掩码
    """
    masker = get_masker()
    
    # 深度拷贝避免修改原始数据
    entry = copy.deepcopy(log_entry)
    
    # 脱敏params
    if "params" in entry and isinstance(entry["params"], dict):
        entry["params"] = masker.mask(entry["params"])
    
    # 脱敏user_id（如果不是管理员）
    if entry.get("user_id") and entry.get("role") != "admin":
        entry["user_id"] = mask_value(entry.get("user_id", ""), show_last=4)
    
    # 脱敏IP地址
    if "ip_address" in entry and entry["ip_address"]:
        entry["ip_address"] = mask_ip(entry["ip_address"])
    
    # 脱敏metadata中的敏感信息
    if "metadata" in entry and isinstance(entry["metadata"], dict):
        entry["metadata"] = masker.mask(entry["metadata"])
    
    return entry
