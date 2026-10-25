"""审计日志 - 哈希链防篡改 + 敏感数据脱敏"""
import json
import time
import uuid
import hashlib
import copy
import re
from typing import Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum


class AuditAction(Enum):
    """审计动作类型"""
    SESSION_CREATE = "session.create"
    SESSION_CLOSE = "session.close"
    AGENT_INVOKE = "agent.invoke"
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    POLICY_PASS = "policy.pass"
    POLICY_DENY = "policy.deny"
    POLICY_CHANGE = "policy.change"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_GRANT = "approval.grant"
    APPROVAL_REJECT = "approval.reject"
    APPROVAL_EXECUTE = "approval.execute"
    ERROR = "error"


# 创世哈希（第一个哈希基准）
GENESIS_HASH = "0" * 64


# ---------------------------------------------------------------------------
# 审计写入端体积上限（DEF-2026-1005）
# ---------------------------------------------------------------------------
# 背景：写入端此前对 params 没有任何长度上限，一次 tool.call 就能往不可变的
# 哈希链审计文件里写 100 MiB。
#   爆炸点 tests/v1.5/validation/test_cases_dfx.py:539
#       huge_sql = "SELECT " + "a" * (100 * 1024 * 1024)
#   实测后果：226 条超大记录 = 22.08 GiB
#       (Javis-DB-Agent 15.63 GiB + zhenli 6.45 GiB)
# 处置：单值上限 4 KB、单条落盘上限 64 KB；截断必须留痕（原长度 + sha256），
#       否则「这条 SQL 有 100 MiB」这个事实会被一起抹掉，审计会变成盲的。
MAX_PARAM_VALUE_BYTES = 4 * 1024
MAX_RECORD_BYTES = 64 * 1024
_MAX_CAP_DEPTH = 6


def _mask_ip(ip: str) -> str:
    """脱敏IP地址（前两段）"""
    if not ip:
        return ip
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.*.{parts[3]}"
    return ip[:max(0, len(ip)-4)] + "****"


# 敏感字段模式
# ★ 业务键名全量登记表 (SC 2026-10-25 19:55 函 §二① 裁定, 真理 1330/1400 函实测支持)
# 这批键是**段首前缀**形态 (敏感词在段首: auth|method / password|db / key|value ...),
# 词段整段匹配结构上抓不到 ⟹ 由登记表显式登记。
# 用**精确键名**登记 ⟹ 零误伤 (不像通用子串规则那样误伤 author/spinning/secretary/pinterest/saltwater)。
# 归入 _SENSITIVE_KEYS ⟹ 段尾规则同时覆盖其前缀变体 (如 dbauthmethod),
# 避免「旧实现脱敏、新实现不脱敏」的相对回归。
_EXACT_SENSITIVE_KEYS = frozenset({
    "authmethod", "credentialid", "keyvalue", "passwdvalue",
    "passworddb", "pincode", "saltvalue", "secretstore",
})

_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "api-key",
    "credential", "auth", "private_key", "access_token", "refresh_token",
    "bearer", "authorization", "ssn", "credit_card", "card_number",
    "cvv", "pin", "salt", "client_secret", "oauth_client_secret",
}) | _EXACT_SENSITIVE_KEYS


def _key_segments(key: str) -> list[str]:
    """按键名分词（DEF-2026-1006 P2）。

    分词边界：`_` / `-` / `.` 分隔符 + camelCase 大小写边界。
    "api_key" -> ["api", "key"]；"apiKey" -> ["api", "key"]；
    "x-api-key" -> ["x", "api", "key"]；"userPassword" -> ["user", "password"]。

    非字符串键（如 int / bool / None）先转成其 json 落盘形态，
    避免在此处抛 TypeError（旧的子串实现在 `key.lower()` 处同样会抛）。
    """
    s = re.sub(r"[_\-.]+", " ", _json_key(key))
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    return [x.lower() for x in s.split() if x]


def _norm_segment(seg: str) -> str:
    """段内归一：剥离尾部数字与复数 s（password2 -> password, tokens -> token）。

    DEF-2026-1006 P2 收尾：词段整段匹配消除了 `author`/`spinning`/`secretary` 的误伤，
    但把下面 11 条**原本会被子串实现脱敏**的键变成了明文落盘 —— 那是**净新增泄漏**，
    不是「语义收窄」：

        password2 passwords tokens secrets credentials api_keys
        access_tokens auths client_secrets private_keys credit_cards

    段内归一让「敏感词 + 数字/复数」回到脱敏，同时不动 author 这类误伤。
    """
    out = seg
    while out and out[-1].isdigit():
        out = out[:-1]
    if len(out) > 1 and out.endswith("s"):
        out = out[:-1]
    return out


def _is_sensitive_key(key: str) -> bool:
    """判定键名是否敏感（DEF-2026-1006 P2）。

    敏感键的**词段序列**必须在候选键的词段序列中**连续**出现。

    为什么不能用子串包含（这是本修复的核心）：
      * 子串包含 ⟹ `author` 含 "auth"、`spinning` 含 "pin"、`secretary` 含 "secret"
        ⟹ 正常业务字段被误脱敏 = **业务数据损坏**（比漏脱敏更隐蔽）；
      * 子串包含 ⟹ camelCase 的 `apiKey` / `privateKey`（无分隔符）**漏脱敏**。
    词段整段匹配同时消除误伤与漏脱敏。

    判定同时看**原始词段**与**段内归一后的词段**（`_norm_segment`），
    以覆盖「敏感词 + 数字/复数」形态（password2 / tokens / api_keys ...）——
    否则 P2 的收尾会引入新的明文泄漏。
    """
    cand = _key_segments(key)
    if not cand:
        return False
    variants = [cand, [_norm_segment(c) for c in cand]]
    for sensitive_key in _SENSITIVE_KEYS:
        pat = _key_segments(sensitive_key)
        if not pat:
            continue
        for v in variants:
            if not v:
                continue
            for i in range(len(v) - len(pat) + 1):
                if v[i:i + len(pat)] == pat:
                    return True
        # 段尾形态: 敏感词出现在某一段的**尾部** (dbpassword / mytoken / userauth /
        # xpassword / dbcredentials ...)。
        # ⟹ 这一层**不重建** author/spinning/secretary 那一类误伤: 那三者的敏感词是
        #    **段首前缀**而非段尾 (author[-4:]="thor" != "auth")。
        #    代价: 「敏感词严格位于段首」形态 (passworddb / tokenvalue) 仍不脱敏 ——
        #    与 author 同类, 属**前缀/内嵌**类, 需业务键名全量才能判定, 留待 SC 裁。
        joined = "".join(pat)
        for v in variants:
            for seg in v:
                if len(seg) > len(joined) and seg.endswith(joined):
                    return True
    return False


# ★ 强制层 (SC 2026-10-25 19:55 函 §二②): strict=True 时, 落盘前若见
#   「未登记的键 + 明文值 + 值像凭据」⟹ 直接拦截报错。
#   目的: 将来出现第 9 个未知前缀类键时, 是「写不进去且报错」,
#         而不是「静默明文落盘」。
# ⚠️ 启用前必须先证明「不会误拦现有全部业务键」(SC 硬前提):
#         拿现有全量审计日志回放, strict=True 下必须 0 拦截。
_CREDENTIAL_VALUE_RE = re.compile(r"^[A-Za-z0-9+/=_\-\.]{20,}$")


def _looks_like_credential(value: Any) -> bool:
    """值是否「像凭据」—— 保守判据, 宁可漏拦不可误拦现有业务数据。

    判据 (全满足才算像): 长串 + 无空白 + 字符集受限 + 含字母 + 含数字或大写或符号。
    排除: 句子/含空格的散文、路径、URL、短值。
    """
    if not isinstance(value, str):
        return False
    s = value.strip()
    if len(s) < 20 or len(s) > 4096:
        return False
    if not _CREDENTIAL_VALUE_RE.match(s):
        return False
    has_lower = any(c.islower() for c in s)
    has_upper = any(c.isupper() for c in s)
    has_digit = any(c.isdigit() for c in s)
    has_symbol = any(c in "+/=_-." for c in s)
    if not (has_lower or has_upper):
        return False
    if not (has_digit or has_upper or has_symbol):
        return False
    return True


def _strict_unregistered_credentials(log: "AuditLog") -> list[str]:
    """列出「未登记的键 + 明文值 + 值像凭据」的违例 (SC ② 强制层)。

    「未登记」= 该键名不会被脱敏器识别 ⟹ 其值会**原样**落盘。
    「明文值」= 脱敏后仍是完整可读串 (已脱敏的敏感键值是 "***xxxx", 长度短 ⟹ 不会命中)。
    """
    out: list[str] = []
    for section in ("params", "metadata"):
        data = getattr(log, section, None)
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            k = _json_key(key)
            if _is_sensitive_key(k):
                continue  # 已登记 ⟹ 已被脱敏 ⟹ 放行
            if _looks_like_credential(value):
                out.append(f"{section}.{k}")
    return out

def _sanitize_value(value: Any, key: str) -> Any:
    """对单个值进行脱敏（如果key是敏感字段）

    DEF-2026-1006(P2)：判据由子串包含改为词段整段匹配，见 `_is_sensitive_key`。
    """
    if not _is_sensitive_key(key):
        return value
    if isinstance(value, str):
        if len(value) <= 4:
            return "***"
        return "***" + value[-4:]
    return "***REDACTED***"


def _sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_size(value: Any) -> int:
    """估算任意值的 JSON 字节数（用于计量/排序）"""
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return len(str(value).encode("utf-8"))


def _truncate_text(text: str, max_bytes: int = MAX_PARAM_VALUE_BYTES):
    """截断超大字符串并留痕。

    返回 (新值, 留痕信息)。留痕 = 原字节数 + 原内容 sha256 + 实际保留字节数。
    留痕写两份：值内嵌人可读标记 + metadata._audit_cap 机器可读。
    """
    raw = text.encode("utf-8", errors="surrogatepass")
    if len(raw) <= max_bytes:
        return text, None
    digest = _sha256_hex(raw)
    marker = f" ... <truncated, original_bytes={len(raw)}, sha256={digest}>"
    budget = max(0, max_bytes - len(marker.encode("utf-8")))
    head = raw[:budget].decode("utf-8", errors="ignore")
    return head + marker, {
        "original_bytes": len(raw),
        "sha256": digest,
        "kept_bytes": len(head.encode("utf-8")),
    }


def _cap_value(value: Any, depth: int = 0):
    """递归截断容器里的超大字符串叶子。返回 (新值, 留痕信息)。"""
    if isinstance(value, str):
        return _truncate_text(value)
    if depth >= _MAX_CAP_DEPTH:
        return value, None
    if isinstance(value, dict):
        trail = {}
        out = {}
        for key, item in value.items():
            new_item, info = _cap_value(item, depth + 1)
            out[key] = new_item
            if info:
                trail[str(key)] = info
        return out, (trail or None)
    if isinstance(value, (list, tuple)):
        trail = {}
        out = []
        for idx, item in enumerate(value):
            new_item, info = _cap_value(item, depth + 1)
            out.append(new_item)
            if info:
                trail[str(idx)] = info
        return (out if isinstance(value, list) else tuple(out)), (trail or None)
    return value, None


def _record_size(log: "AuditLog") -> int:
    """估算整条记录落盘后的字节数（用未脱敏版本估算：脱敏只会变小）"""
    try:
        return len(json.dumps(log.to_dict(), ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        return 0


def _cap_record(log: "AuditLog") -> dict:
    """落盘前给整条记录封顶（DEF-2026-1005）。

    1. 单值封顶：字符串叶子截断到 4 KB，值内嵌留痕标记（original_bytes + sha256）
    2. 记录封顶：仍超 64 KB 时，按体积从大到小丢弃 params 键，并留痕
    3. 机器可读留痕写进 metadata._audit_cap

    必须在 seal() 之前调用：哈希链覆盖的就是落盘内容，顺序反了链会自断。
    """
    trail = {"values": {}, "dropped_keys": []}

    params = log.params
    if isinstance(params, dict):
        for key in list(params.keys()):
            new_value, info = _cap_value(params[key])
            if info:
                params[key] = new_value
                trail["values"][f"params.{_json_key(key)}"] = info

    metadata = log.metadata
    if not isinstance(metadata, dict):
        metadata = {}
        log.metadata = metadata
    for key in list(metadata.keys()):
        if key == "_audit_cap":
            continue
        new_value, info = _cap_value(metadata[key])
        if info:
            metadata[key] = new_value
            trail["values"][f"metadata.{_json_key(key)}"] = info

    for field_name in ("error_message", "result"):
        current = getattr(log, field_name, None)
        if isinstance(current, str):
            new_value, info = _truncate_text(current)
            if info:
                setattr(log, field_name, new_value)
                trail["values"][field_name] = info

    if trail["values"] or trail["dropped_keys"]:
        metadata["_audit_cap"] = trail

    # 记录级封顶：params 仍把记录撑爆时，丢最大的键（并留痕）
    size = _record_size(log)
    if size > MAX_RECORD_BYTES and isinstance(params, dict) and params:
        ordered = sorted(params.keys(), key=lambda k: _json_size(params[k]), reverse=True)
        for key in ordered:
            if size <= MAX_RECORD_BYTES:
                break
            value = params.pop(key)
            raw = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            trail["dropped_keys"].append({
                "key": _json_key(key),
                "original_bytes": len(raw),
                "sha256": _sha256_hex(raw),
            })
            size = _record_size(log)
    trail["record_bytes_after_cap"] = size
    return trail


def _sanitize_audit_record(record: dict) -> dict:
    """
    对审计日志记录进行敏感数据脱敏
    
    脱敏规则：
    1. params中的敏感字段值部分掩码（保留后4位）
    2. IP地址部分掩码（前两段）
    3. metadata中的敏感数据脱敏
    """
    record = copy.deepcopy(record)
    
    # 脱敏params
    if "params" in record and isinstance(record["params"], dict):
        for key, value in record["params"].items():
            record["params"][key] = _sanitize_value(value, key)
    
    # 脱敏metadata
    if "metadata" in record and isinstance(record["metadata"], dict):
        for key, value in record["metadata"].items():
            record["metadata"][key] = _sanitize_value(value, key)
    
    # 脱敏IP
    if "ip_address" in record and record["ip_address"]:
        record["ip_address"] = _mask_ip(record["ip_address"])
    
    # 脱敏error_message（可能包含敏感信息）
    if "error_message" in record and record["error_message"]:
        em = record["error_message"]
        # 掩码可能的token/key
        import re
        em = re.sub(r"(token[key]?['\"]?[:=]\s*['\"]?)([a-zA-Z0-9_\-\.]{8,})", r"\1***REDACTED***", em)
        em = re.sub(r"(api[_-]?key['\"]?[:=]\s*['\"]?)([a-zA-Z0-9_\-\.]{8,})", r"\1***REDACTED***", em)
        em = re.sub(r"(password['\"]?[:=]\s*['\"]?)([^\s'\"]{6,})", r"\1***REDACTED***", em)
        record["error_message"] = em
    
    return record


def _json_key(key: Any) -> str:
    """把 dict 的键转成 `json.dumps` 落盘时使用的字符串形态。

    规则与 json 一致: str 原样; True->"true"; False->"false"; None->"null";
    int/float -> 其十进制字面量 ("1" / "2.5" / "Infinity")。
    """
    if isinstance(key, str):
        return key
    if key is True:
        return "true"
    if key is False:
        return "false"
    if key is None:
        return "null"
    if isinstance(key, (int, float)):
        return json.dumps(key)
    return str(key)


def _normalize_json_keys(value: Any) -> Any:
    """把嵌套 dict 的键统一成 json 落盘后的字符串形态（DEF-2026-1006）。

    目的：让**内存对象**与**重载后的对象**形态完全一致 ⟹
    「被哈希的内容」==「被落盘的内容」在**键层面**也不会分叉。

    不做这一步时的两类分叉/崩溃（真理特别自问点名要答）：
      1. 键冲突：params = {1: "a", "1": "b"} ⟹ json 落盘产生**重复键**
         "1" ⟹ 重载时 json.loads 只保留最后一个 ⟹ 重算哈希 != 落盘 hash ⟹ 链断。
      2. 混合类型键：params = {1: "a", "b": 2} ⟹ `json.dumps(sort_keys=True)`
         抛 TypeError（int 与 str 不可比较）⟹ 密封即崩。
    归一化后：键全是字符串 ⟹ 冲突按「后者覆盖前者」（与 json 落盘行为一致）⟹
    重载对象与内存对象逐字段相等 ⟹ 链自洽。
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out[_json_key(k)] = _normalize_json_keys(v)
        return out
    if isinstance(value, (list, tuple)):
        # tuple 落盘后即为 list ⟹ 内存侧也转成 list，保证与重载对象同形态
        return [_normalize_json_keys(v) for v in value]
    return value


def _sanitize_audit_log_inplace(log: "AuditLog") -> None:
    """就地脱敏 AuditLog 对象的四个来源字段（DEF-2026-1006 P1）。

    背景：`log()` 原先的顺序是
        seal(prev_hash)  →  _persist(log)
    而 `_persist()` 内部才做脱敏且 `_sanitize_audit_record()` 首行是
    `copy.deepcopy(record)` ⟹ **脱敏结果不回写到被 seal() 的对象** ⟹
    「算哈希的输入」≠「落盘的内容」⟹ 未被篡改的记录被报「疑似篡改」。

    本函数把脱敏**就地**写回 log 对象，使 log 成为**唯一的最终对象**：
    `_logs` 内存链与落盘链持有同一份脱敏后的内容 ⟹ 链自洽。

    幂等性：脱敏重复调用结果稳定（真理 4 轮实测），故 `_persist()` 内部的
    二次脱敏是幂等空操作，可原样保留。
    """
    sanitized = _sanitize_audit_record(_normalize_json_keys(log.to_dict()))
    for field_name in ("params", "metadata", "ip_address", "error_message"):
        if field_name in sanitized:
            setattr(log, field_name, sanitized[field_name])


@dataclass
class AuditLog:
    """审计日志条目"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    action: str = ""
    user_id: str = ""
    session_id: str = ""
    agent_name: str = ""
    tool_name: str = ""
    risk_level: int = 0
    params: dict = field(default_factory=dict)
    result: str = ""  # success/failure/denied
    error_message: str = ""
    ip_address: str = ""
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)
    # 哈希链字段
    prev_hash: str = ""       # 前一条记录的哈希
    hash: str = ""            # 本条记录的哈希（SHA256）

    @property
    def timestamp_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).isoformat()

    def _compute_hash(self, prev_hash: str) -> str:
        """计算本条记录的哈希"""
        content = json.dumps({
            "id": self.id,
            "timestamp": self.timestamp,
            "action": self.action.value if isinstance(self.action, AuditAction) else self.action,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_name": self.agent_name,
            "tool_name": self.tool_name,
            "risk_level": self.risk_level,
            "params": self.params,
            "result": self.result,
            "error_message": self.error_message,
            "ip_address": self.ip_address,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "prev_hash": prev_hash,
        }, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def seal(self, prev_hash: str, strict: bool = False):
        """密封记录，绑定前驱哈希并计算自身哈希

        strict=True 时启用**强制层** (SC 2026-10-25 19:55 函 §二②):
        落盘前若见「未登记的键 + 明文值 + 值像凭据」⟹ 直接拦截报错。
        ⟹ 检查发生在 seal 内部 ⟹ 违例记录**不进链、不落盘** (内存链与落盘链都不含它)。
        """
        if strict:
            violations = _strict_unregistered_credentials(self)
            if violations:
                raise ValueError(
                    "审计落盘被强制层拦截 (strict=True): 检出「未登记的键 + 明文值 + 值像凭据」: "
                    + ", ".join(violations[:10])
                    + (" ..." if len(violations) > 10 else "")
                    + " ⟹ 请把该键登记进 _SENSITIVE_KEYS (精确键名) 或改用非敏感字段名"
                )
        self.prev_hash = prev_hash
        self.hash = self._compute_hash(prev_hash)

    def verify(self, prev_hash: str) -> bool:
        """验证本条记录是否被篡改"""
        expected = self._compute_hash(prev_hash)
        return self.hash == expected

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value if isinstance(self.action, AuditAction) else self.action
        return d


class AuditLogger:
    """审计日志记录器 - 哈希链防篡改"""

    def __init__(self, log_file: str = "data/audit.jsonl", auto_load: bool = True, strict: bool = False):
        self._logs: list[AuditLog] = []
        self._log_file = log_file
        # strict=True 启用 SC ② 强制层 (默认关闭; 启用前须先过全量日志回放 0 拦截证明)
        self.strict = strict
        self._ensure_storage()
        if auto_load:
            self._load()

    def _ensure_storage(self):
        import os
        os.makedirs("data", exist_ok=True)

    def _load(self):
        """加载已有日志并重建哈希链"""
        import os
        if not os.path.exists(self._log_file):
            return
        prev_hash = GENESIS_HASH
        with open(self._log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    d["action"] = AuditAction(d["action"]) if d["action"] in [a.value for a in AuditAction] else d["action"]
                    record = AuditLog(**d)
                    self._logs.append(record)
                    prev_hash = record.hash
                except Exception:
                    pass

    def _persist(self, log: AuditLog):
        """持久化到文件（敏感数据脱敏）"""
        import os
        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)
        
        # 敏感数据脱敏处理
        record_dict = log.to_dict()
        sanitized = _sanitize_audit_record(record_dict)
        
        with open(self._log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(sanitized, ensure_ascii=False) + "\n")

    def log(self, log: AuditLog) -> str:
        """记录日志（自动密封哈希链）"""
        prev_hash = self._logs[-1].hash if self._logs else GENESIS_HASH
        # DEF-2026-1005: 落盘前体积上限（截断 + 留痕），必须在 seal() 之前
        _cap_record(log)
        # DEF-2026-1006: 先就地脱敏，再对**脱敏后**的字段密封 ⟹
        #   「被哈希的内容 == 被落盘的内容」，内存链与落盘链不再分叉。
        #   ⚠️ 顺序不可与 _cap_record 交换：cap 必须先于 sanitize，否则秘密先被
        #   掩成 "***xxxx"（7 B）根本不触发封顶 ⟹ DEF-2026-1005 的
        #   original_bytes 留痕被静默摧毁（且测试不一定报错）。
        _sanitize_audit_log_inplace(log)
        log.seal(prev_hash, strict=self.strict)
        self._logs.append(log)
        self._persist(log)
        return log.id

    def log_action(
        self,
        action: AuditAction,
        user_id: str = "",
        session_id: str = "",
        **kwargs
    ) -> AuditLog:
        """快捷记录方法"""
        log = AuditLog(
            action=action,
            user_id=user_id,
            session_id=session_id,
            **kwargs
        )
        self.log(log)
        return log

    def verify_chain(self) -> tuple[bool, Optional[str], Optional[int]]:
        """
        验证哈希链完整性
        Returns: (is_valid, error_message, broken_index)
        """
        if not self._logs:
            return True, None, None

        prev_hash = GENESIS_HASH
        for i, record in enumerate(self._logs):
            # 验证前驱哈希匹配
            if record.prev_hash != prev_hash:
                return False, f"记录 {i} 前驱哈希不匹配（期望 {prev_hash[:16]}..., 实际 {record.prev_hash[:16]}...）", i
            # 验证自身哈希完整
            if not record.verify(prev_hash):
                return False, f"记录 {i} 自身哈希不匹配（疑似篡改）", i
            prev_hash = record.hash
        return True, None, None

    def detect_tampering(self, check_from: Optional[float] = None) -> list[dict]:
        """
        篡改检测：返回可疑记录列表
        check_from: 可选，只检查此时间点之后的记录
        """
        suspicious = []
        prev_hash = GENESIS_HASH
        for i, record in enumerate(self._logs):
            if check_from and record.timestamp < check_from:
                prev_hash = record.hash
                continue
            if record.prev_hash != prev_hash:
                suspicious.append({
                    "index": i,
                    "id": record.id,
                    "timestamp": record.timestamp,
                    "reason": "prev_hash_mismatch",
                    "expected_prev": prev_hash[:16] + "...",
                    "actual_prev": record.prev_hash[:16] + "...",
                })
            elif not record.verify(prev_hash):
                suspicious.append({
                    "index": i,
                    "id": record.id,
                    "timestamp": record.timestamp,
                    "reason": "hash_mismatch",
                    "action": record.action.value if isinstance(record.action, AuditAction) else record.action,
                })
            prev_hash = record.hash
        return suspicious

    def query(
        self,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        tool_name: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100
    ) -> list[AuditLog]:
        """查询审计日志"""
        results = []
        for log in reversed(self._logs):
            if user_id and log.user_id != user_id:
                continue
            if session_id and log.session_id != session_id:
                continue
            if action and (log.action.value if isinstance(log.action, AuditAction) else log.action) != action.value:
                continue
            if tool_name and log.tool_name != tool_name:
                continue
            if start_time and log.timestamp < start_time:
                continue
            if end_time and log.timestamp > end_time:
                continue
            results.append(log)
            if len(results) >= limit:
                break
        return results

    def get_session_audit(self, session_id: str) -> list[AuditLog]:
        """获取会话的所有审计日志"""
        return [log for log in self._logs if log.session_id == session_id]

    def get_user_audit(self, user_id: str, hours: int = 24) -> list[AuditLog]:
        """获取用户最近N小时的审计日志"""
        cutoff = time.time() - hours * 3600
        return [log for log in self._logs if log.user_id == user_id and log.timestamp >= cutoff]

    def export(self, start_time: float, end_time: float, file_path: str):
        """导出指定时间范围的日志"""
        with open(file_path, "w", encoding="utf-8") as f:
            for log in self._logs:
                if start_time <= log.timestamp <= end_time:
                    f.write(json.dumps(log.to_dict(), ensure_ascii=False) + "\n")

    def get_stats(self) -> dict:
        """获取审计统计信息"""
        return {
            "total_records": len(self._logs),
            "first_record": self._logs[0].timestamp_str if self._logs else None,
            "last_record": self._logs[-1].timestamp_str if self._logs else None,
            "genesis_hash": GENESIS_HASH,
            "chain_valid": self.verify_chain()[0],
        }


# 全局单例
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(log_file: str = "data/audit.jsonl") -> AuditLogger:
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger(log_file=log_file)
    return _audit_logger
