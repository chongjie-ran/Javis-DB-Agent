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
"""
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


@pytest.mark.xfail(
    reason="DEF-2026-1006: seal() 早于脱敏 ⟹ 哈希输入 ≠ 落盘内容 ⟹ 未被篡改的记录被报「疑似篡改」; 修复后应 XPASS, 届时删除本标记",
    strict=False,
)
def test_chain_valid_when_params_contain_sensitive_key():
    """params 含敏感键（脱敏会改值）⟹ 链必须仍有效。"""
    logger = _write_and_reload([{"params": {"api_key": "sk-secret-value-1234"}}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"含敏感键的记录不应被判篡改, 实际: {err} @ {idx}"


@pytest.mark.xfail(
    reason="DEF-2026-1006: 同上（ip_address 脱敏改值）",
    strict=False,
)
def test_chain_valid_when_ip_address_present():
    """ip_address 非空 ⟹ 链必须仍有效（这条是集群健康降级的实际触发路径）。"""
    logger = _write_and_reload([{"ip_address": "10.1.2.3"}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"带 IP 的记录不应被判篡改, 实际: {err} @ {idx}"


@pytest.mark.xfail(
    reason="DEF-2026-1006: 同上（metadata 含 token）",
    strict=False,
)
def test_chain_valid_when_metadata_contains_token():
    """metadata 含 token ⟹ 链必须仍有效。"""
    logger = _write_and_reload([{"metadata": {"token": "abc123"}}])
    ok, err, idx = logger.verify_chain()
    assert ok, f"metadata 含 token 的记录不应被判篡改, 实际: {err} @ {idx}"


@pytest.mark.xfail(
    reason="DEF-2026-1006(P2): 敏感键判定是子串包含 ⟹ author/spinning/secretary 被误脱敏 ⟹ 业务数据损坏; 修复后应 XPASS, 届时删除本标记 (改 strict=True 即可强制拦截)",
    strict=False,
)
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
