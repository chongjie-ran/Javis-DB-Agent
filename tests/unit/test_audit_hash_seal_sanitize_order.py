"""P1 回归：审计哈希链在**脱敏之后**必须仍然可验（DEF-2026-1006）

背景（2026-10-25 真理发现，真显独立复现并确认）
------------------------------------------------
`src/gateway/audit.py` 的 `log()` 顺序是：

    log.seal(prev_hash)      # ← 先对**脱敏前**的字段算哈希
    ...
    self._persist(log)       # ← 再写入**脱敏后**的内容

⟹ **算哈希的输入 ≠ 落盘的内容** ⟹ 重新加载后用落盘内容重算哈希必然对不上，
`verify_chain()` 会把**根本没被篡改**的记录报成「疑似篡改」。

实测（真显 2026-10-25 复现，`src/gateway/audit.py:356-364`）：

    plain (无敏感字段)      → verify_chain() = True
    params 含 api_key        → verify_chain() = False 「记录 1 自身哈希不匹配（疑似篡改）」
    ip_address 非空          → verify_chain() = False 同上
    metadata 含 token       → verify_chain() = False 同上

影响面（比看上去大）：

* `src/gateway/distributed.py:457` 用 `audit.verify_chain()` 判 `audit_chain_valid`，
  并据此把整体健康度判成 `degraded` ⟹ **一条带 IP 的正常日志就能让集群健康检查报降级**。
* `src/api/audit_routes.py:150` 有对外的 `verify_chain` 接口 ⟹ 对外误报「疑似篡改」，
  这是**安全控制误报**，比漏报更危险（真出事的告警会被淹没）。

为什么现有单测测不出来：`tests/unit/test_audit_hash_chain.py` 的用例全是
`session_id` / `user_id` / `tool_name` 这类无敏感字段的记录，恰好绕开了触发条件。

修复方向（交由开发实施）：必须让**被哈希的内容 == 被落盘的内容** —— 即
先脱敏 → 再对脱敏后的字段密封 → 落盘同一份对象（`_logs` 内存里也要持有同一份脱敏对象，
否则内存链与落盘链会分叉）。**不能**改成「先落盘再算哈希」，那会破坏防篡改语义。

本文件用 xfail 固化该缺陷：修好之后本用例应转为 XPASS，届时删除 xfail 标记。

**2026-10-25 修复已入库**（悟通）：4 条 xfail 已删除并转为常规用例，另补 5 类不变量/回归测试
（落盘行哈希不变量 / 防篡改未被削弱 / P2 敏感键矩阵 / cap 先于 sanitize 的留痕守卫）。
"""
import hashlib
import json
import os
import tempfile

import pytest

from src.gateway.audit import AuditAction, AuditLogger


def _write_and_reload(records):
    """写若干条记录后**从文件重新加载**（关键：空验证测不出来）。"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    for kwargs in records:
        logger.log_action(AuditAction.TOOL_CALL, user_id="u", tool_name="t", **kwargs)
    # auto_load=True 才会从文件把记录读回来 —— 这一步是本缺陷的触发条件
    reloaded = AuditLogger(log_file=path, auto_load=True)
    return reloaded


def test_chain_valid_for_plain_record():
    """基线：无敏感字段时链必须有效（证明用例本身有效，不是恒真）。"""
    logger = _write_and_reload([{}])
    assert len(logger._logs) == 1
    ok, err, idx = logger.verify_chain()
    assert ok, f"无敏感字段时链应有效, 实际: {err} @ {idx}"


def test_chain_valid_when_params_contain_sensitive_key():
    """params 含敏感键（脱敏会改值）⟹ 链必须仍有效。"""
    logger = _write_and_reload([{"params": {"api_key": "sk-secret-value-1234"}}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"含敏感键的记录不应被判篡改, 实际: {err} @ {idx}"


def test_chain_valid_when_ip_address_present():
    """ip_address 非空 ⟹ 链必须仍有效（这条是集群健康降级的实际触发路径）。"""
    logger = _write_and_reload([{"ip_address": "10.1.2.3"}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"带 IP 的记录不应被判篡改, 实际: {err} @ {idx}"


def test_chain_valid_when_metadata_contains_token():
    """metadata 含 token ⟹ 链必须仍有效。"""
    logger = _write_and_reload([{"metadata": {"token": "abc123"}}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"metadata 含 token 的记录不应被判篡改, 实际: {err} @ {idx}"


def test_chain_valid_when_error_message_contains_token():
    """★ 用例 D：error_message 含 token ⟹ 链必须仍有效。

    派单函验收标准 1 的用例 D。error_message 是四个脱敏来源之一，
    其脱敏走正则替换（`token=xxx` -> `token=***REDACTED***`）⟹ 同样会改值 ⟹ 同样触发本缺陷。
    """
    logger = _write_and_reload([{"error_message": "token=abcdef12345678"}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"error_message 含 token 的记录不应被判篡改, 实际: {err} @ {idx}"


def test_sensitive_and_benign_params_are_redacted_and_kept_at_record_level():
    """★ 用例 F（记录级）：params 里的敏感键必须被脱敏，正常业务键必须保持原样。

    派单函验收标准 1 的用例 F。注意这是**记录级**断言（不只测 `_sanitize_value` 单元），
    覆盖「落盘后仍然是脱敏值 / 仍然是原值」。
    """
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t",
        params={
            "author": "X", "spinning": "X", "secretary": "X",
            "api_key": "SECRETVALUE1234",
        },
    )
    rec = _read_lines(path)[0]
    for benign in ("author", "spinning", "secretary"):
        assert rec["params"][benign] == "X", (
            f"params[{benign!r}] 不得被脱敏（子串包含误伤 ⟹ 静默数据损坏），实际 {rec['params'][benign]!r}"
        )
    assert rec["params"]["api_key"] != "SECRETVALUE1234", "params['api_key'] 必须被脱敏"
    # 脱敏后链必须仍有效
    reloaded = AuditLogger(log_file=path, auto_load=True)
    ok, err, idx = reloaded.verify_chain()
    assert ok, f"脱敏后链应有效, 实际: {err} @ {idx}"


def test_sensitive_key_matching_is_not_substring():
    """P2：敏感键判定不能是子串包含 ⟹ `author` / `spinning` / `secretary` 不得被脱敏。

    背景（真理发现，真显独立复现）：`_sanitize_value` 判据是
    `if sensitive_key in key_lower` ⟹ 含 'auth' 的 `author`、含 'pin' 的 `spinning`、
    含 'secret' 的 `secretary` 全被误脱敏 ⟹ **正常业务字段被破坏**（数据损坏）。
    """
    from src.gateway.audit import _sanitize_value

    for key in ("author", "spinning", "secretary", "consultant"):
        assert _sanitize_value("BENIGNVALUE123", key) == "BENIGNVALUE123", (
            f"字段名 {key!r} 不该被脱敏（子串包含误伤 ⟹ 业务数据损坏）"
        )


# ---------------------------------------------------------------------------
# DEF-2026-1006 修复后新增：不变量 + 回归
# ---------------------------------------------------------------------------

# 必须脱敏的键名（30 条，真理实测矩阵）
MUST_REDACT = [
    "api_key", "api-key", "apiKey", "auth_token", "authToken",
    "access_token", "refresh_token", "token", "password", "passwd",
    "secret", "credential", "auth", "authorization", "bearer",
    "private_key", "privateKey", "credit_card", "card_number", "cvv",
    "pin", "salt", "client_secret", "oauth_client_secret",
    "user_api_key", "my_pin_code", "myAuthorization", "userPassword",
    "x-api-key", "Authorization",
]

# 不得脱敏的键名（13 条 —— 子串实现下 12 条被误伤）
MUST_NOT_REDACT = [
    "author", "spinning", "secretary", "consultant", "pinterest",
    "saltwater", "authoring", "authorizer", "secretariat", "spinner",
    "tokenizer", "spinning_top", "authoring_service",
]


def _read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _recompute_hash(line: dict) -> str:
    """**独立**重算落盘行的哈希。

    刻意不复用生产代码的字段清单 —— 若生产侧漏掉某个字段参与哈希，
    这里独立写一遍就能测出来。
    """
    content = json.dumps({
        "id": line["id"],
        "timestamp": line["timestamp"],
        "action": line["action"],
        "user_id": line["user_id"],
        "session_id": line["session_id"],
        "agent_name": line["agent_name"],
        "tool_name": line["tool_name"],
        "risk_level": line["risk_level"],
        "params": line["params"],
        "result": line["result"],
        "error_message": line["error_message"],
        "ip_address": line["ip_address"],
        "duration_ms": line["duration_ms"],
        "metadata": line["metadata"],
        "prev_hash": line["prev_hash"],
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def test_persisted_line_hash_equals_recomputed_hash():
    """★ 核心不变量：对**实际落盘的 JSON 行**重算哈希，必须等于该行落盘的 hash 字段。

    即「哈希输入 == 落盘内容」。这是 DEF-2026-1006 的判据本身。
    """
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t",
        params={"api_key": "sk-secret-1234", "sql": "SELECT 1"},
        ip_address="10.1.2.3",
        metadata={"token": "abc123", "author": "someone"},
    )
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t2",
        params={"password": "hunter2"},
    )

    lines = _read_lines(path)
    assert len(lines) == 2, f"应落盘 2 行，实际 {len(lines)}"
    for i, line in enumerate(lines):
        assert _recompute_hash(line) == line["hash"], (
            f"第 {i} 行：落盘内容重算哈希 != 落盘 hash 字段（哈希输入 ≠ 落盘内容）"
        )


def test_tampering_is_still_detected_after_fix():
    """防篡改能力不得因本次修复而削弱：篡改后仍须检出，且断点索引正确。"""
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t",
        params={"api_key": "sk-secret-1234"}, ip_address="10.1.2.3",
    )
    logger.log_action(AuditAction.TOOL_CALL, user_id="u", tool_name="t2")

    lines = _read_lines(path)
    lines[0]["user_id"] = "attacker"
    with open(path, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")

    reloaded = AuditLogger(log_file=path, auto_load=True)
    ok, err, idx = reloaded.verify_chain()
    assert not ok, "篡改后链仍被判有效 ⟹ 防篡改能力被削弱"
    assert idx == 0, f"篡改点索引应为 0，实际 {idx}"


# --- P2 收尾: 段内归一 (DEF-2026-1006) ---
#
# 词段整段匹配消除了 author/spinning/secretary 的误伤, 但把 11 条**原本会被
# 子串实现脱敏**的键变成了明文落盘 —— 那是净新增泄漏, 不是「语义收窄」。
# 段内归一（去尾部数字 + 复数 s）把它们拉回脱敏, 同时不动 author 这类误伤。

SENSITIVE_SUFFIX_VARIANTS = [
    "password2", "passwords", "tokens", "secrets", "credentials",
    "api_keys", "access_tokens", "auths", "client_secrets",
    "private_keys", "credit_cards",
]

# 段内归一会扩大脱敏面 ⟹ 必须锁住「不新增误伤」(真理 1440 函的 29 条风险词)
NORMALIZE_SAFE_WORDS = [
    "status", "process", "address", "business", "analysis", "access", "class",
    "bonus", "gas", "args", "opts", "flags", "metrics", "series", "alias",
    "bias", "basis", "hints", "lens", "tips", "notes", "docs", "tools",
    "books", "cars", "keys", "cards", "creds", "creds2",
]


@pytest.mark.parametrize("key", SENSITIVE_SUFFIX_VARIANTS)
def test_sensitive_key_suffix_variants_are_still_masked(key):
    """段内归一后, 「敏感词+数字/复数」的键仍必须脱敏 (防 P2 收尾引入新泄漏)."""
    from src.gateway.audit import _sanitize_value

    out = _sanitize_value("SECRETVALUE1234", key)
    assert out != "SECRETVALUE1234", f"敏感键 {key!r} 未脱敏 ⟹ 明文落盘"


@pytest.mark.parametrize("key", NORMALIZE_SAFE_WORDS)
def test_normalization_does_not_add_false_positives(key):
    """段内归一不得把正常业务键误伤 (归一化扩大了脱敏面, 需锁住)."""
    from src.gateway.audit import _sanitize_value

    out = _sanitize_value("BENIGNVALUE123", key)
    assert out == "BENIGNVALUE123", f"字段名 {key!r} 被误脱敏 ⟹ 业务数据损坏"


# ★ 已知边界（待 SC 裁）: 「敏感词**严格位于段首/内嵌**」的键当前**不脱敏**。
#
# 这与 author/spinning/secretary **同类** —— 段首前缀无法与业务词区分
# (author 的敏感词 "auth" 正是段首前缀). 旧子串实现会脱敏它们 (旧实现更安全),
# 但会同时误伤 author 类 ⟹ **两类需求直接冲突**, 需业务键名全量才能判定.
#
# **显式在册** ⟹ 不是静默放过: 本表即 SC 的待裁清单.
# 将来若补上前缀/内嵌规则, 从此表移除 + 放开差集守卫即可.
# 前缀类三类归属 (SC 2026-10-25 19:55 函 §二① 裁定「走业务键名全量登记表」之后):
#   REGISTERED    = SC 裁定纳入登记表的 8 条 ⟹ **现已脱敏** (精确键名, 零误伤)
#   GAPS          = 段首前缀、SC 尚未纳入 ⟹ 仍不脱敏 (已知边界, 待裁)
#   UNREGISTERED  = 段首前缀、既未登记也未裁定 ⟹ 仍不脱敏 ⟹ 需 SC 裁定 (新暴露面)
#
# 探针语料 11 条 = REGISTERED 8 + GAPS 1 + UNREGISTERED 2
# (探针是样本, 类不封闭 ⟹ 另有「段尾层语料随敏感词表同步」的断言守住整类)
KNOWN_PREFIX_CLASS_REGISTERED = [
    "authmethod", "credentialid", "keyvalue", "passwdvalue",
    "passworddb", "pincode", "saltvalue", "secretstore",
]

# 已知边界显式在册: 这类键当前不脱敏, 待 SC 裁（不静默放过）。
KNOWN_PREFIX_GAPS = [
    "tokenvalue",   # 敏感词在段首；SC ① 登记表未纳入它 ⟹ 仍在册待裁
]

# --- 前缀类探针语料 (真理 1215 §五(2) / 1330 §四 的 P0: 前缀类明文落盘 + 守卫盲区) ---
# 事实基础 (悟通 2026-10-25 实测 src.gateway.audit 的 _SENSITIVE_KEYS / _is_sensitive_key):
#   本语料 11 个键, ① 登记前**全部不被新实现脱敏**;
#   其中 10 个是「旧子串实现会脱敏、新实现不脱敏」= 净新增明文暴露;
#   另 1 个 (keyvalue) 旧新都不脱敏 (旧实现的敏感词表里也没有 key 子串)。
#   ⟹ 10 - 2(已登记在 KNOWN_PREFIX_GAPS) = **8 条未登记暴露** ⟹ 真理 1330 函报的「8 个键明文落盘」对上。
#   ⟹ 「已登记 2 条」**不等于**「只剩 2 条」⟹ 本组把暴露面在册且条数写死 (见下面钉死断言)。
KNOWN_PREFIX_CLASS_PROBE = [
    "passworddb",    # 已登记 (REGISTERED)
    "tokenvalue",    # 已登记 (GAPS: SC 未纳入, 待裁)
    "secretkey",     # 未登记 (需 SC 裁定)
    "keyvalue",      # 已登记 (REGISTERED; 旧实现也不命中 ⟹ 靠登记表才脱敏)
    "passwdvalue",   # 已登记 (REGISTERED)
    "credentialid",  # 已登记 (REGISTERED)
    "tokentype",     # 未登记 (需 SC 裁定)
    "secretstore",   # 已登记 (REGISTERED)
    "authmethod",    # 已登记 (REGISTERED)
    "pincode",       # 已登记 (REGISTERED)
    "saltvalue",     # 已登记 (REGISTERED)
]

# 仍未脱敏且尚未被 SC 裁定的暴露面 —— SC ① 只登记了 8 条, 探针里这 2 条**不在**其列。
# ⟹ 需 SC 裁定: 是「真实业务键 ⟹ 放行」还是「应脱敏 ⟹ 纳入登记表」。
KNOWN_PREFIX_CLASS_UNREGISTERED = [
    "secretkey", "tokentype",
]

# 旧新都不命中的键: ① 登记后**已无** (keyvalue 已进登记表 ⟹ 现已脱敏)。
KNOWN_PREFIX_CLASS_INERT = [
]

# --- 段尾规则专属语料 (真理 1440 函 MUT-I) ---
# 段尾规则抓的键**旧子串实现不脱敏**(myapikey: 旧=False 新=True) ⟹ 落在差集守卫的
# **定义域之外**, 差集守卫永远看不见它 ⟹ 必须有专属断言守着这一层。
# 语料: ① 每个敏感词的「尾部形态」= my + 词段拼接 (系统生成 ⟹ 类不封闭)
#       ② 真理 1440 函手挑的多词段形态 (db+password / auth+token ...)
SEGMENT_TAIL_VARIANTS = [
    # 系统生成: 每个敏感词一条 (段尾规则专抓这一形态)
    "myaccesstoken", "myapikey", "myauth", "myauthorization", "mybearer",
    "mycardnumber", "myclientsecret", "mycredential", "mycreditcard", "mycvv",
    "myoauthclientsecret", "mypassword", "mypasswd", "mypin", "myprivatekey",
    "myauthmethod", "mycredentialid", "mykeyvalue", "mypasswdvalue",
    "mypassworddb", "mypincode", "mysaltvalue", "mysecretstore",
    "myrefreshtoken", "mysalt", "mysecret", "myssn", "mytoken",
    # 真理 1440 函手挑的多词段形态
    "dbpassword", "userauth", "xpassword", "dbcredentials",
    "myauthtoken", "authtoken2", "userpassword",
]


@pytest.mark.parametrize("key", KNOWN_PREFIX_GAPS)
def test_known_prefix_gap_is_tracked_not_silent(key):
    """已知边界显式在册: 这类键当前不脱敏, 待 SC 裁（不静默放过）."""
    from src.gateway.audit import _sanitize_value

    out = _sanitize_value("SECRETVALUE1234", key)
    assert out == "SECRETVALUE1234", (
        f"{key!r} 现已脱敏 ⟹ 前缀/内嵌规则已生效 ⟹ "
        f"请从 KNOWN_PREFIX_GAPS 移除并同步放开差集守卫"
    )


def test_new_matcher_never_redacts_less_than_old_substring_matcher():
    """★ 差集守卫 (真理 1440 函的教训: 修「误伤类」缺陷必须同时做新旧实现差集比对).

    旧实现 = 子串包含; 新实现 = 词段整段匹配 + 段内归一.
    本断言: 除**已登记**的误伤类 (allow-list = MUST_NOT_REDACT 那 13 条, 经确认属正常
    业务字段) 外, **新实现脱敏的键集必须是旧实现的超集** ⟹ 任何
    「旧会脱敏、新不脱敏」的回归都当场红, 而不是静默变成明文落盘。
    """
    from src.gateway.audit import _SENSITIVE_KEYS, _is_sensitive_key

    def old_impl(k: str) -> bool:
        return any(sk in k.lower() for sk in _SENSITIVE_KEYS)

    corpus = sorted(
        set(MUST_REDACT) | set(MUST_NOT_REDACT)
        | set(SENSITIVE_SUFFIX_VARIANTS) | set(NORMALIZE_SAFE_WORDS)
        | set(KNOWN_PREFIX_GAPS) | set(KNOWN_PREFIX_CLASS_PROBE)
        | set(SEGMENT_TAIL_VARIANTS)
    )
    # 允许清单 = 已登记的误伤类 (13 条) + 已登记的前缀缺口 (待 SC 裁)
    # 前缀类 11 条全部在册 (已登记 2 + 未登记 8 + 旧新都不命中 1) ⟹ 进入语料作用域但**不**被误判为新回归;
    # 该类的「有无变化」由下面的钉死断言负责 (条数与构成写死), 职责不重叠。
    allow = (set(MUST_NOT_REDACT) | set(KNOWN_PREFIX_GAPS)
            | set(KNOWN_PREFIX_CLASS_PROBE))
    leaks = [
        k for k in corpus
        if old_impl(k) and not _is_sensitive_key(k) and k not in allow
    ]
    assert not leaks, (
        f"新实现比旧实现脱敏得少 (明文落盘回归): {leaks}"
    )


@pytest.mark.parametrize("key", KNOWN_PREFIX_CLASS_PROBE)
def test_prefix_class_probe_is_registered(key):
    """前缀类探针语料必须**在册** (真理 1215 §五(2): 原始语料不入库 ⟹ 别人无法复现结论)。

    本断言把「SC 已登记」/「已知边界待裁」/「仍待裁定」三类分开 ⟹ 杜绝「只登记 N 条 == 只剩 N 条」的误读。
    """
    registered = (set(KNOWN_PREFIX_CLASS_REGISTERED) | set(KNOWN_PREFIX_GAPS)
                 | set(KNOWN_PREFIX_CLASS_UNREGISTERED) | set(KNOWN_PREFIX_CLASS_INERT))
    assert key in registered, (
        f"前缀类探针键 {key!r} 未登记 ⟹ 守卫对它无盲区保护, 别人无法复现该结论。"
        "请补进 KNOWN_PREFIX_CLASS_REGISTERED (SC 已裁定纳入) / KNOWN_PREFIX_GAPS (已知边界待裁)"
        " / KNOWN_PREFIX_CLASS_UNREGISTERED (待 SC 裁定) / KNOWN_PREFIX_CLASS_INERT (旧新都不命中)"
    )


@pytest.mark.parametrize("key", KNOWN_PREFIX_CLASS_REGISTERED)
def test_prefix_class_registered_is_masked(key):
    """SC ① 裁定纳入登记表的键**必须脱敏** ⟹ 登记表被摘掉/键名写错, 当场红。

    SC 2026-10-25 19:55 函 §二①: 走「业务键名全量登记表」⟹ 这 8 条精确键名必须脱敏,
    且**不得**误伤 author/spinning/secretary/pinterest/saltwater 那类业务键 (由差集守卫守)。
    """
    from src.gateway.audit import _sanitize_value
    out = _sanitize_value("SUPERSECRET1234", key)
    assert out != "SUPERSECRET1234", (
        f"SC 已裁定登记的键 {key!r} 现在**没有**脱敏 ⟹ 登记表未生效 (或键名写错)"
    )


@pytest.mark.parametrize("key", KNOWN_PREFIX_CLASS_UNREGISTERED)
def test_prefix_class_unregistered_gap_is_still_open(key):
    """尚未被 SC 裁定的暴露**必须仍然是「未脱敏」** ⟹ 任何变化当场可见。

    两种变化都会红, 且含义不同:
      - 变**成脱敏** ⟹ SC 已裁定纳入 ⟹ 该条应移出本组、移入 KNOWN_PREFIX_CLASS_REGISTERED
      - 仍不脱敏但**结构变了**(如旧实现不再命中) ⟹ 暴露面构成变化 ⟹ 需重测并更新条数
    """
    from src.gateway.audit import _is_sensitive_key
    assert not _is_sensitive_key(key), (
        f"前缀类键 {key!r} 现在被脱敏了 ⟹ SC 已裁定纳入, 请把它移出"
        " KNOWN_PREFIX_CLASS_UNREGISTERED 并移入 KNOWN_PREFIX_CLASS_REGISTERED"
    )


def test_prefix_class_exposure_surface_is_pinned():
    """前缀类暴露面**条数与构成写死** ⟹ 任何变更当场可见 (增=新暴露, 减=已裁定/已修)。

    这是真理 1215 §五(2) 要的「让这一类今后任何变更都被当场抓住」: 语料在库 + 条数钉死。
    """
    from src.gateway.audit import _SENSITIVE_KEYS, _is_sensitive_key

    def old_impl(k: str) -> bool:
        return any(sk in k.lower() for sk in _SENSITIVE_KEYS)

    probe = set(KNOWN_PREFIX_CLASS_PROBE)
    not_redacted = {k for k in probe if not _is_sensitive_key(k)}
    divergence = {k for k in probe if old_impl(k) and not _is_sensitive_key(k)}
    assert not_redacted == {"tokenvalue", "secretkey", "tokentype"}, (
        f"前缀类探针的脱敏状态变了: 仍未脱敏的 = {sorted(not_redacted)}"
    )
    assert len(divergence) == 3, (
        f"前缀类「旧脱敏/新不脱敏」的条数变了: {len(divergence)} (期望 3) "
        f"实际 {sorted(divergence)}"
    )
    unregistered = divergence - set(KNOWN_PREFIX_GAPS)
    assert unregistered == set(KNOWN_PREFIX_CLASS_UNREGISTERED), (
        f"未登记暴露面构成变了: 实际 {sorted(unregistered)}"
    )
    assert len(unregistered) == 2, (
        f"未登记暴露面条数变了: {len(unregistered)} (期望 2)"
    )
    # SC ① 登记的 8 条 ⟹ 必须**已脱敏** (在探针里 ⟹ 不在 not_redacted)
    assert probe & set(KNOWN_PREFIX_CLASS_REGISTERED) == set(KNOWN_PREFIX_CLASS_REGISTERED), (
        f"登记表与探针语料不一致: {sorted(set(KNOWN_PREFIX_CLASS_REGISTERED) - probe)}"
    )
    assert not ((probe & set(KNOWN_PREFIX_CLASS_REGISTERED)) & not_redacted), (
        f"登记表的键仍在未脱敏集合里: {sorted((probe & set(KNOWN_PREFIX_CLASS_REGISTERED)) & not_redacted)}"
    )


@pytest.mark.parametrize("key", SEGMENT_TAIL_VARIANTS)
def test_segment_tail_variants_are_still_masked(key):
    """段尾形态键必须仍被脱敏 ⟹ 段尾规则被削弱/删除时当场红。

    这一层是**差集守卫的定义域之外**的: 差集守卫的 leak 定义是
    old_impl(k) and not _is_sensitive_key(k) (旧脱敏/新不脱敏 = 回归),
    而段尾规则抓的键**旧实现本就不脱敏** ⟹ 差集守卫永远看不见它们。
    ⟹ 真理 1440 函 MUT-I: 删掉段尾规则整层, 套件仍全绿, 而 myapikey 明文落盘。
    本断言给该层单独建语料, 让整层被删时逐条指明失守。
    """
    from src.gateway.audit import _sanitize_value
    out = _sanitize_value("SUPERSECRET1234", key)
    assert out != "SUPERSECRET1234", (
        f"段尾形态键 {key!r} 未被脱敏 ⟹ 段尾规则被削弱/删除 (MUT-I)"
    )


def test_segment_tail_corpus_covers_every_sensitive_word():
    """段尾层语料必须**随敏感词表同步** ⟹ 新增敏感词而未加尾部样本, 当场红。

    真理 1440 §3.4: 探针是**样本**不是类 (1050 条合成候选里探针只覆盖 9 条)。
    ⟹ 正解不是手挑更多探针, 而是按「层」建语料 ⟹ 这里保证语料对每个敏感词都有覆盖。
    """
    from src.gateway.audit import _SENSITIVE_KEYS, _key_segments
    missing = []
    for sk in _SENSITIVE_KEYS:
        pat = _key_segments(sk)
        if not pat:
            continue
        tf = "my" + "".join(pat)
        if tf not in SEGMENT_TAIL_VARIANTS:
            missing.append((sk, tf))
    assert not missing, (
        f"段尾层语料落后于敏感词表: 缺 {missing} ⟹ 补进 SEGMENT_TAIL_VARIANTS"
    )

def test_strict_layer_blocks_unregistered_credential_like_value():
    """★ 强制层 (SC 2026-10-25 19:55 函 §二②): 未登记的键 + 明文值 + 值像凭据 ⟹ 拒绝落盘。

    目的: 将来出现第 9 个未知前缀类键时, 是「写不进去且报错」, 而不是「静默明文落盘」。
    """
    from src.gateway.audit import AuditLog, AuditAction

    log = AuditLog(
        action=AuditAction.TOOL_CALL,
        params={"some_unregistered_key": "AKIA0123456789ABCDEF"},
    )
    try:
        log.seal("0" * 64, strict=True)
    except ValueError as exc:
        assert "强制层" in str(exc), str(exc)
        assert "some_unregistered_key" in str(exc), str(exc)
    else:
        raise AssertionError("强制层未拦截: 未登记的键 + 明文凭据值竟然被允许落盘")

    # 违例记录**不进链**: prev_hash/hash 未被写入
    assert log.hash == "", "被拦截的记录不应产生哈希"
    assert log.prev_hash == "", "被拦截的记录不应绑定前驱哈希"


def test_strict_layer_allows_registered_and_normal_values():
    """强制层不得误拦: 已登记的键、以及普通业务值都必须放行。

    SC 硬前提: 「不会误拦现有全部业务键」⟹ 靠这条断言 + 全量日志回放共同保证。
    """
    from src.gateway.audit import AuditLog, AuditAction, _sanitize_value

    # ① 已登记的键: 值照样脱敏, 不该被强制层拦
    masked = _sanitize_value("AKIA0123456789ABCDEF", "authmethod")
    assert masked != "AKIA0123456789ABCDEF", "已登记的键应脱敏"

    # ② 普通业务值: 短句/路径/URL/布尔 ⟹ 放行
    for value in (
        "正常业务描述, 含空格",
        "/usr/local/bin/tool --flag",
        "https://example.com/path?q=1",
        "short",
        12345,
        True,
        None,
        {"a": 1},
    ):
        log = AuditLog(
            action=AuditAction.TOOL_CALL,
            params={"business_field": value},
        )
        log.seal("0" * 64, strict=True)  # 不应抛异常
        assert log.hash != "", "放行的记录应正常产生哈希"


def test_strict_layer_enabled_by_default_but_can_be_disabled():
    """强制层默认**开启** (SC 1955 函 §三② 门槛已过: 全量日志回放 0 拦截), 且可显式关闭。"""
    from src.gateway.audit import AuditLog, AuditAction, AuditLogger

    # ① 默认开启 ⟹ 违例被拦
    log = AuditLog(
        action=AuditAction.TOOL_CALL,
        params={"some_unregistered_key": "AKIA0123456789ABCDEF"},
    )
    try:
        log.seal("0" * 64, strict=True)
    except ValueError:
        pass
    else:
        raise AssertionError("强制层未拦截")

    # ② logger 默认 strict=True ⟹ 走强制层
    assert AuditLogger.__init__.__defaults__[-1] is True, "强制层默认应开启"

    # ③ 可显式关闭 (单实例级)
    log2 = AuditLog(
        action=AuditAction.TOOL_CALL,
        params={"some_unregistered_key": "AKIA0123456789ABCDEF"},
    )
    log2.seal("0" * 64, strict=False)  # 不应抛异常
    assert log2.hash != "", "显式关闭时路径应正常密封"

def test_nested_sensitive_key_is_masked_end_to_end():
    """DEF-2026-1007: 嵌套层敏感键必须脱敏 (端到端读落盘字节).

    真理 1345 函独立实测: params 形如 {cfg: {api_key: <假密钥>}} 落盘行**含明文**;
    同一密钥放顶层 params 则正确脱敏 ⟹ 问题只在嵌套层 (脱敏只作用于第一层)。
    """
    import json
    from src.gateway.audit import _sanitize_audit_record

    secret = "SUPERSECRET1234"
    record = {
        "action": "tool.call",
        "params": {"cfg": {"api_key": secret, "note": "plain"}, "api_key": secret},
        "metadata": {},
    }
    sanitized = _sanitize_audit_record(record)
    blob = json.dumps(sanitized, ensure_ascii=False)
    assert secret not in blob, "嵌套层 api_key 明文落盘 (DEF-2026-1007 未修)"
    # 对照组: 顶层必须已脱敏 (证明不是「全都不脱敏」)
    assert sanitized["params"]["api_key"] != secret, "顶层 api_key 应脱敏"
    # 嵌套层的普通业务值不应被误伤
    assert sanitized["params"]["cfg"]["note"] == "plain", "普通业务值被误脱敏"


def test_audit_cap_trail_survives_recursive_sanitize():
    """★ DEF-2026-1007 留痕反例: _audit_cap 子树必须**原样保留**。

    这是第三档方案的关键: 朴素递归会把 metadata._audit_cap.values 的键
    (形如 params.api_key) 当成敏感键 ⟹ 整条封顶留痕被掩码 ⟹ DEF-2026-1005 的
    original_bytes / sha256 留痕被静默摧毁。
    ⟹ 递归时必须**显式排除** _audit_cap 子树。
    """
    from src.gateway.audit import _sanitize_audit_record

    trail = {
        "values": {"params.api_key": {"original_bytes": 20, "sha256": "deadbeef"}},
        "dropped_keys": [],
    }
    record = {"params": {}, "metadata": {"_audit_cap": trail}}
    sanitized = _sanitize_audit_record(record)
    assert sanitized["metadata"]["_audit_cap"] == trail, (
        "_audit_cap 留痕被递归脱敏摧毁 (DEF-2026-1005 留痕失效)"
    )


def test_nested_audit_cap_trail_also_survives():
    """留痕反例的加强版: _audit_cap 出现在**嵌套**层也必须原样保留。"""
    from src.gateway.audit import _sanitize_audit_record

    trail = {"values": {"params.token": {"original_bytes": 9, "sha256": "cafe"}}, "dropped_keys": []}
    record = {"params": {"cfg": {"_audit_cap": trail}}, "metadata": {}}
    sanitized = _sanitize_audit_record(record)
    assert sanitized["params"]["cfg"]["_audit_cap"] == trail, (
        "嵌套层的 _audit_cap 留痕被递归摧毁"
    )

@pytest.mark.parametrize("key", MUST_REDACT)
def test_sensitive_key_must_be_redacted(key):
    """敏感键必须脱敏（防修复时削弱脱敏能力）。"""
    from src.gateway.audit import _sanitize_value

    out = _sanitize_value("SUPERSECRET1234", key)
    assert out != "SUPERSECRET1234", f"敏感键 {key!r} 未被脱敏 ⟹ 泄露"


@pytest.mark.parametrize("key", MUST_NOT_REDACT)
def test_non_sensitive_key_must_not_be_redacted(key):
    """非敏感键必须**不**被脱敏（防业务数据被损坏）。"""
    from src.gateway.audit import _sanitize_value

    out = _sanitize_value("BENIGNVALUE123", key)
    assert out == "BENIGNVALUE123", f"字段名 {key!r} 被误脱敏 ⟹ 业务数据损坏"


def test_cap_trail_records_original_length_even_for_sensitive_key():
    """★ cap 必须先于 sanitize：敏感键上的超大值也必须留下 original_bytes 原始长度留痕。

    若顺序反了（sanitize → cap），秘密先被掩成 "***xxxx"（7 B）⟹ 根本不触发封顶
    ⟹ DEF-2026-1005 的留痕彻底消失，且测试不一定报错。

    现有 size_cap 用例的键名是 "sql"（非敏感），**覆盖不到这个坑** ⟹ 此用例专门兜它。
    """
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    payload = "A" * 8003
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t",
        params={"api_key": payload},
    )

    rec = _read_lines(path)[0]
    cap = rec.get("metadata", {}).get("_audit_cap")
    assert cap is not None, (
        "敏感键上的超大值未留下 _audit_cap 留痕 ⟹ cap 可能被排在了 sanitize 之后"
    )
    assert "params.api_key" in cap["values"], (
        f"留痕缺少 params.api_key，实际: {list(cap['values'])}"
    )
    assert cap["values"]["params.api_key"]["original_bytes"] == len(payload), (
        "留痕的 original_bytes 不是原始长度 ⟹ 留痕记的是脱敏后长度"
    )


# ---------------------------------------------------------------------------
# 真理特别自问：有没有办法让「落盘内容」与「被哈希内容」再次分叉？
#   （例如攻击者构造 params 内特殊键名）
# ---------------------------------------------------------------------------

def test_non_string_params_key_does_not_break_chain():
    """非字符串键（int / bool / None）不得让写入崩溃，也不得让链分叉。

    旧实现的两个问题（本修复一并消除）：
      * `_sanitize_value` 对 int 键抛 AttributeError（旧: `key.lower()`）
        ⟹ 崩溃发生在 `_persist()` 内，即 **seal() 与 _logs.append() 之后**
        ⟹ 内存链多一条、磁盘没有 ⟹ **内存/落盘链分叉**；
      * 混合类型键 {1: "a", "b": 2} 在 `json.dumps(sort_keys=True)` 处抛 TypeError。
    现已归一化为 json 落盘形态的字符串键 ⟹ 写入成功且链自洽。
    """
    for label, params in [
        ("int 键", {1: "a"}),
        ("bool 键", {True: "a"}),
        ("None 键", {None: "a"}),
        ("int+str 混合键", {1: "a", "b": 2}),
    ]:
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "audit.jsonl")
        logger = AuditLogger(log_file=path, auto_load=False)
        logger.log_action(AuditAction.TOOL_CALL, user_id="u", tool_name="t", params=params)

        lines = _read_lines(path)
        assert len(lines) == 1, f"{label}: 应落盘 1 行，实际 {len(lines)}"
        for line in lines:
            assert _recompute_hash(line) == line["hash"], (
                f"{label}: 落盘内容重算哈希 != 落盘 hash（键形态未归一化 ⟹ 链会分叉）"
            )
        reloaded = AuditLogger(log_file=path, auto_load=True)
        ok, err, idx = reloaded.verify_chain()
        assert ok, f"{label}: 链应有效, 实际: {err} @ {idx}"
        # 内存链与落盘链必须同长度（旧实现在这里会分叉）
        assert len(logger._logs) == len(reloaded._logs), (
            f"{label}: 内存链 {len(logger._logs)} 条 != 重载链 {len(reloaded._logs)} 条 ⟹ 链分叉"
        )


def test_colliding_params_keys_do_not_diverge():
    """键冲突（int 1 与 str "1" 同时存在）不得造成「落盘 ≠ 被哈希」。

    冲突时 json 落盘会产生**重复键** "1" ⟹ 若不归一化，重载时 json.loads 只保留最后一个
    ⟹ 重算哈希 != 落盘 hash ⟹ **未被篡改的记录被判篡改**。
    归一化后冲突按「后者覆盖前者」（与 json 落盘行为一致）⟹ 链自洽。
    """
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(AuditAction.TOOL_CALL, user_id="u", tool_name="t",
                      params={1: "a", "1": "b"})

    lines = _read_lines(path)
    assert len(lines) == 1
    line = lines[0]
    assert _recompute_hash(line) == line["hash"], (
        "键冲突导致落盘内容重算哈希 != 落盘 hash ⟹ 链分叉"
    )
    reloaded = AuditLogger(log_file=path, auto_load=True)
    ok, err, idx = reloaded.verify_chain()
    assert ok, f"键冲突时链应有效, 实际: {err} @ {idx}"


@pytest.mark.parametrize("key", [True, False, None, 1, 2.5, "api_key", "plain"])
def test_cap_trail_key_matches_persisted_key(key):
    """cap 留痕的 key 必须与落盘 key 一致（审计按留痕查得到落盘记录）.

    根因: _cap_record 跑在键归一化之前 ⟹ bool/None 键的留痕记 params.True / params.None,
    而落盘是 params.true / params.null。不影响哈希链，但纯留痕可追溯性会断。
    """
    import json
    import os
    import tempfile

    from src.gateway.audit import AuditAction, AuditLogger

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t", params={key: "X" * 9000}
    )
    rec = json.loads(
        [ln for ln in open(path, encoding="utf-8") if ln.strip()][0]
    )
    trail = rec.get("metadata", {}).get("_audit_cap", {}).get("values", {})
    derived = sorted(k.split(".", 1)[1] for k in trail)
    persisted = sorted(rec["params"].keys())
    assert derived == persisted, "cap trail key mismatch"


# ==== DEF-2026-1010: 强制层递归下钻 + 路径/URL 排除 (真理 1510 函缺口 2) ====


def _cred_like(prefix: str) -> str:
    """构造一个「像凭据」的值: 长度/字符集/大小写+数字 全部满足 _looks_like_credential。

    刻意用拼接而非字面量, 避免长随机串在日志/截图里被误当真实凭据。
    """
    return prefix + "A1b2C3d4E5f6G7h8"


def test_strict_layer_blocks_nested_unregistered_credential():
    """★ 缺口 2: 嵌套层的「未登记键 + 明文值 + 值像凭据」必须被强制层拦。

    真理 1510 函: 强制层只遍历顶层 ⟹ 嵌套的未知键既不脱敏、也不被拦 ⟹ 明文落盘,
    与 e23fd8a 的递归脱敏**不对称**。
    """
    from src.gateway.audit import AuditLog, AuditAction

    log = AuditLog(
        action=AuditAction.TOOL_CALL,
        params={"cfg": {"secretkey": _cred_like("AKIA")}},
    )
    try:
        log.seal("0" * 64, strict=True)
    except ValueError as exc:
        assert "cfg.secretkey" in str(exc), str(exc)
    else:
        raise AssertionError("嵌套层未登记凭据未被强制层拦 ⟹ 明文落盘")
    assert log.hash == "", "被拦截的记录不应产生哈希"
    assert log.prev_hash == "", "被拦截的记录不应绑定前驱哈希"


def test_strict_layer_does_not_flag_audit_cap_trail():
    """★ 封顶留痕的 sha256 (64 位十六进制) 形似凭据 ⟹ 强制层必须跳过 _audit_cap 子树。

    不跳过 ⟹ 每一条封顶留痕都成违例 ⟹ 强制层恒真 ⟹ 业务调用全断。
    """
    import json
    import os
    import tempfile

    from src.gateway.audit import AuditAction, AuditLogger

    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL, user_id="u", tool_name="t", params={"api_key": "X" * 9000}
    )
    rec = json.loads([ln for ln in open(path, encoding="utf-8") if ln.strip()][0])
    assert rec["metadata"].get("_audit_cap"), "本用例前提: 产生了封顶留痕"
    # 落盘成功 ⟹ 强制层没把留痕里的 sha256 当成违例
    assert rec.get("hash"), "记录应正常密封并落盘"


def test_strict_layer_does_not_block_business_paths_or_urls():
    """★ docstring 承诺的「排除: 路径 / URL」必须真的排除。

    缺这一步 ⟹ 普通业务路径 (references/.../config-reference.md) 被当成凭据 ⟹
    强制层误拦 ⟹ 业务调用当场中断 (真显 DEF-2026-1009 报的触发面正是这一类)。
    """
    from src.gateway.audit import AuditLog, AuditAction

    for value in (
        "references/mysql/mysql-5/mgr/config-reference.md",
        "data/audit.jsonl",
        "/usr/local/bin/tool/--flag",
        "https://example.com/path?q=1",
    ):
        log = AuditLog(
            action=AuditAction.TOOL_CALL,
            params={"file_path": value},
        )
        log.seal("0" * 64, strict=True)  # 不应抛异常
        assert log.hash != "", f"普通业务值应正常密封: {value}"


def test_strict_layer_still_blocks_base64_like_value_containing_slash():
    """★ 路径排除不得放宽到漏拦真凭据: 无 padding 的 base64 (含 /) 仍须被拦。

    ""abcd/efghijklmnopqrstuv" 既像路径又像 base64 ⟹ 末段无扩展名 ⟹ 判为凭据。
    """
    from src.gateway.audit import AuditLog, AuditAction

    log = AuditLog(
        action=AuditAction.TOOL_CALL,
        params={"file_path": "abcd" + "/" + "efghijklmnopqrstuv"},
    )
    try:
        log.seal("0" * 64, strict=True)
    except ValueError as exc:
        assert "file_path" in str(exc), str(exc)
    else:
        raise AssertionError("无 padding 的 base64 值未被拦 ⟹ 漏拦真凭据")

# ==== DEF-2026-1008: cap 留痕语义自明 (真理 1510 函 5(2)) ====


def _write_record_with_long_values(path):
    # 落一条含长值的记录: 1 个敏感键 (password) + 1 个普通键 (note)
    import json
    from src.gateway.audit import AuditAction, AuditLogger
    logger = AuditLogger(log_file=path, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL,
        user_id="u",
        tool_name="t",
        params={"password": "A" * 9000, "note": "B" * 9000},
    )
    with open(path, encoding="utf-8") as f:
        return json.loads(f.read().strip())


def test_cap_trail_declares_pre_sanitize_stage():
    # 留痕必须自报: 我描述的是脱敏前状态
    # 真理 1510 函 5(2): kept_bytes=3986 但盘上并无这 3986 字节
    # => 读者会误以为被保留的头部还在盘上 => 阶段语义必须写出来
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    rec = _write_record_with_long_values(path)
    trail = rec["metadata"]["_audit_cap"]
    assert trail["stage"] == "pre_sanitize", trail.get("stage")
    assert "盘上无此副本" in trail.get("stage_note", ""), trail.get("stage_note")


def test_cap_trail_kept_bytes_on_disk_false_for_sensitive_key():
    # 敏感键: kept_bytes 是脱敏前口径 => 头部并不在盘上 => 必须显式给真值
    import hashlib
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    rec = _write_record_with_long_values(path)
    trail = rec["metadata"]["_audit_cap"]
    info = trail["values"]["params.password"]
    assert info["original_bytes"] == 9000, info
    assert info["sha256"] == hashlib.sha256(("A" * 9000).encode()).hexdigest(), info
    assert info["kept_bytes_on_disk"] is False, info
    pw = rec["params"]["password"]
    assert pw.startswith("***") and len(pw) == 7, pw
    assert ("A" * 9000) not in str(rec)


def test_cap_trail_kept_bytes_on_disk_true_for_plain_key():
    # 非敏感键: 截断头部确实在盘上 => kept_bytes_on_disk 必须为 True
    # 这是对照组 => 防止该标记恒为 False 而失去意义
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    rec = _write_record_with_long_values(path)
    trail = rec["metadata"]["_audit_cap"]
    info = trail["values"]["params.note"]
    assert info["kept_bytes_on_disk"] is True, info
    landed = rec["params"]["note"]
    assert len(landed.encode("utf-8")) > info["kept_bytes"], landed[:80]


def test_cap_trail_order_invariant_keeps_sensitive_original_hash():
    # 顺序不变式 (cap 必须先于 sanitize) 的具名守卫
    # 真理 1510 函 1 结论「1ec5809 让留痕顺序无关」=> 我实测不成立:
    # 交换 cap/sanitize 两行 (逐字符回读确认注入成功) 后:
    #   敏感键的留痕条目整个消失 (原值长度与散列一并丢失)
    #   盘上掩码从 ***b7b> 变成 ***AAAA (脱敏的是原值而非截断值)
    #   tests/unit 601 -> 3 failures
    # => 正确的不变式是: cap 先于 sanitize => 敏感键的原值长度/散列仍被留痕
    #
    # ★ 顺序哨兵只有**两条** (真显 1525 函实测的 M1 敏感性对照):
    #   顺序敏感 (M1 下必红): 本用例 + test_cap_trail_kept_bytes_on_disk_false_for_sensitive_key
    #   顺序免疫 (M1 下仍绿): test_cap_trail_declares_pre_sanitize_stage (只断言 stage 字段存在)
    #                        test_cap_trail_kept_bytes_on_disk_true_for_plain_key (只管非敏感键)
    # ⟹ 别以为 4 条 trail 用例都在守顺序 ⟹ 真正咬住顺序的是上面标出的两条。
    import os
    import tempfile
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "audit.jsonl")
    rec = _write_record_with_long_values(path)
    trail = rec["metadata"]["_audit_cap"]
    values = trail["values"]
    assert "params.password" in values, sorted(values)
    assert values["params.password"]["original_bytes"] == 9000


def test_strict_layer_does_not_block_english_snake_case_prose():
    # 英文下划线分词的散文 (任务描述) 必须放行 —— 真显 1855 函 P0 放大项:
    # base.py 行 62 (AGENT_INVOKE, metadata.goal) 位于 process() 的 try 块之前
    # ⟹ 误拦会让**整个 agent 入口起不来**
    import os
    import tempfile

    from src.gateway.audit import AuditAction, AuditLogger

    for goal in (
        "verify_audit_sanitization_behavior_20261025",
        "refactor_the_audit_sanitizer_module",
        "fix_the_bug_in_audit_sanitizer",
    ):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "audit.jsonl")
        logger = AuditLogger(log_file=path, auto_load=False)
        logger.log_action(
            AuditAction.AGENT_INVOKE, user_id="u", tool_name="t",
            metadata={"goal": goal}, result="ok",
        )
        assert os.path.getsize(path) > 0, goal


def test_strict_layer_still_blocks_credential_like_values_after_prose_rule():
    # 散文排除不得放宽成漏拦真凭据: 混合大小写 / base64url 形态仍须被拦
    import os
    import tempfile

    from src.gateway.audit import AuditAction, AuditLogger

    for value in (
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",   # 混合大小写 ⟹ 不是散文
        "a1b2_c3d4e5f6g7h8i9j0",             # 段以数字开头 ⟹ 不是散文
        "a1b2c3d4e5f6g7h8i9j0k1l2",            # 无下划线 ⟹ 不是散文
    ):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "audit.jsonl")
        logger = AuditLogger(log_file=path, auto_load=False)
        blocked = False
        try:
            logger.log_action(
                AuditAction.TOOL_CALL, user_id="u", tool_name="t",
                params={"myapikeyz": value}, result="ok", metadata={},
            )
        except ValueError:
            blocked = True
        assert blocked, ("该值应被强制层拦下, 却被当成散文放过: " + value)
def test_strict_layer_does_not_block_business_hostname():
    # 主机名形态的普通业务值必须放行 (真显 1510 函之后实测的残留触发面)
    # 69b4847 只排除了路径与 URL (二者都含斜杠) ⟹ 不含斜杠的主机名当时仍被拦
    import os
    import tempfile

    from src.gateway.audit import AuditAction, AuditLogger

    for value in (
        "prod-database-01.internal.company.com",
        "db01.internal",
        "cache-01.svc.cluster.local",
    ):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "audit.jsonl")
        logger = AuditLogger(log_file=path, auto_load=False)
        logger.log_action(
            AuditAction.TOOL_CALL, user_id="u", tool_name="t",
            params={"host": value}, result="ok", metadata={},
        )
        assert os.path.getsize(path) > 0, value


def test_strict_layer_still_blocks_credential_like_values_after_hostname_rule():
    # 主机名排除不得放宽成漏拦真凭据: 仍须被拦的形态逐条钉住
    import os
    import tempfile

    from src.gateway.audit import AuditAction, AuditLogger

    for value in (
        "AKIAIOSFODNN7EXAMPLEKEY",   # 大写混合 ⟹ 主机名规则要求无大写 ⟹ 不放过
        "a1b2c3d4e5f6a7b8c9d0e1f2",   # 无点 ⟹ 非主机名
        "correct.horse.battery.stapleX",  # 末段含大写 ⟹ 不算域名后缀 ⟹ 不放过
        "x1.y2.z3.a4.b5.c6.d7.e8.f9.g0.h1.i2.j3.k4.l5.m6.n7.o8.p9.q0.r1.s2.t3.u4.v5",  # 末段纯数字非 TLD ⟹ 不放过
    ):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, "audit.jsonl")
        logger = AuditLogger(log_file=path, auto_load=False)
        blocked = False
        try:
            logger.log_action(
                AuditAction.TOOL_CALL, user_id="u", tool_name="t",
                params={"host": value}, result="ok", metadata={},
            )
        except ValueError:
            blocked = True
        assert blocked, ("该值应被强制层拦下, 却被当成主机名放过: " + value)