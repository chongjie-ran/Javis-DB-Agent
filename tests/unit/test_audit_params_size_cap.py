"""P1 回归: 审计日志 params 体积上限 (DEF-2026-1005)

背景 (2026-10-25 真显实测, 见 cross-agent/to-SC-20261025-0900-tester-audit-jsonl-rootcause-22gib.md)
--------------------------------------------------------------------------
src/gateway/audit.py 的写入端没有任何 params 长度上限:

    # :78-80  _sanitize_audit_record() 只做敏感字段脱敏, 不截断
    # :209   _persist() 直接 json.dumps(sanitized) 落盘

后果: 一次 tool.call 就能往不可变的哈希链审计文件里写 100 MiB。
实测爆炸点:
    tests/v1.5/validation/test_cases_dfx.py:539
        huge_sql = "SELECT " + "a" * (100 * 1024 * 1024)   # 100 MiB
        await perf_agent.explain_plan(sql=huge_sql, db_type="mysql")

    → 226 条记录 × 100.0 MiB = 22.08 GiB
      (Javis-DB-Agent 15.63 GiB + zhenli 6.45 GiB)
    → 这两个文件里 99.5% 的字节是字符 'a' 填充

本测试把该缺陷固化成可重复判定的用例:
  - 期望行为: 落盘的单条记录有体积上限 (超大值被截断并留痕原长度)
  - 当前行为: 无上限 ⟹ 用例失败 (xfail), 修复后应转为 XPASS 并移除 xfail 标记

注意: 测试只用 2 MiB 载荷 (不用 100 MiB), 避免自己制造磁盘炸弹。
"""
import json
import os
import tempfile

import pytest

from src.gateway.audit import AuditAction, AuditLogger

# 期望的单条记录落盘上限 (含 JSON 结构开销)
MAX_RECORD_BYTES = 64 * 1024
# 单个参数值的期望上限
MAX_VALUE_BYTES = 4 * 1024


def _write_one(tmpdir, params):
    """写一条审计记录, 返回落盘的那一行 (bytes)。"""
    log_file = os.path.join(tmpdir, "audit.jsonl")
    logger = AuditLogger(log_file=log_file, auto_load=False)
    logger.log_action(
        AuditAction.TOOL_CALL,
        user_id="tester",
        tool_name="explain_sql_plan",
        params=params,
    )
    with open(log_file, "rb") as f:
        lines = [ln for ln in f.read().split(b"\n") if ln]
    assert len(lines) == 1, f"期望 1 行, 实际 {len(lines)}"
    return lines[0]


class TestAuditParamsSizeCap:
    """审计写入端 params 体积上限"""

    def test_normal_params_written_verbatim(self):
        """正常大小的 params 必须原样落盘 (防止过度截断引入新问题)。"""
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_one(tmp, {"sql": "SELECT * FROM orders WHERE status = 1"})
            rec = json.loads(raw.decode("utf-8"))
            assert rec["params"]["sql"] == "SELECT * FROM orders WHERE status = 1"
            assert len(raw) < MAX_RECORD_BYTES

    def test_oversized_param_is_capped(self):
        """超大 param 落盘后必须被截断到上限, 且原始长度留痕。"""
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_one(tmp, {"sql": "SELECT " + "a" * (2 * 1024 * 1024)})
            assert len(raw) <= MAX_RECORD_BYTES, (
                f"落盘记录 {len(raw)} B 超过上限 {MAX_RECORD_BYTES} B —— 审计写入端缺少 params 体积上限"
            )

    def test_oversized_value_marked(self):
        """被截断的值必须留痕 (原长度/摘要), 否则事后无法解释审计记录为何变小。"""
        import hashlib

        payload = "SELECT " + "a" * (2 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_one(tmp, {"sql": payload})
            rec = json.loads(raw.decode("utf-8"))
            value = rec["params"]["sql"]
            assert len(value) <= MAX_VALUE_BYTES, "被截断的值仍然过大"
            # 留痕: 原长度 + 原内容摘要
            blob = json.dumps(rec["params"], ensure_ascii=False)
            assert str(len(payload)) in blob or "truncat" in blob.lower() or "sha256" in blob.lower()

    def test_truncation_records_original_length_and_digest(self):
        """截断必须留痕：原长度 + 原内容 sha256（机器可读字段 metadata._audit_cap）。

        SC 验收要求第 3 条：只截断不记录原长度 = 把「这条 SQL 有 100 MiB」这个
        事实抹掉，审计会变成盲的。因此这里对留痕做硬断言，不接受"有 truncat
        字样就算过"。
        """
        import hashlib

        payload = "SELECT " + "a" * (2 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as tmp:
            raw = _write_one(tmp, {"sql": payload})
            rec = json.loads(raw.decode("utf-8"))

            # 值内嵌的人可读留痕：必须含原长度
            assert f"original_bytes={len(payload)}" in rec["params"]["sql"], (
                "截断值里没有留痕原长度"
            )
            # 机器可读留痕：原长度 + 原内容 sha256
            cap = rec["metadata"]["_audit_cap"]["values"]["params.sql"]
            assert cap["original_bytes"] == len(payload)
            assert cap["sha256"] == hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def test_repeated_calls_do_not_grow_file_unboundedly(self):
        """连续 100 次带 1 MiB 参数的调用, 落盘体积必须保持有界。"""
        with tempfile.TemporaryDirectory() as tmp:
            log_file = os.path.join(tmp, "audit.jsonl")
            logger = AuditLogger(log_file=log_file, auto_load=False)
            for _ in range(100):
                logger.log_action(
                    AuditAction.TOOL_CALL,
                    user_id="tester",
                    tool_name="explain_sql_plan",
                    params={"sql": "SELECT " + "a" * (1024 * 1024)},
                )
            size = os.path.getsize(log_file)
            assert size <= 10 * 1024 * 1024, f"100 次调用后落盘 {size} B, 超出有界预期"
