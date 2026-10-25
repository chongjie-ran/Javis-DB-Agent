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
