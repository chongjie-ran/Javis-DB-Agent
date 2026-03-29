"""P0-2测试: 审计日志哈希链防篡改"""
import pytest
import json
import tempfile
import os
from src.gateway.audit import (
    AuditLog, AuditLogger, AuditAction,
    GENESIS_HASH,
)


class TestAuditLogHash:
    """AuditLog哈希链测试"""

    def test_genesis_hash_is_64_zeros(self):
        assert GENESIS_HASH == "0" * 64
        assert len(GENESIS_HASH) == 64

    def test_first_record_uses_genesis_hash(self):
        log = AuditLog(
            action=AuditAction.SESSION_CREATE,
            user_id="user1",
            session_id="sess1",
        )
        log.seal(GENESIS_HASH)
        assert log.prev_hash == GENESIS_HASH
        assert len(log.hash) == 64
        assert log.hash != GENESIS_HASH

    def test_hash_changes_with_content(self):
        log1 = AuditLog(action=AuditAction.SESSION_CREATE, user_id="user1", session_id="sess1")
        log2 = AuditLog(action=AuditAction.SESSION_CREATE, user_id="user2", session_id="sess1")
        log1.seal(GENESIS_HASH)
        log2.seal(GENESIS_HASH)
        assert log1.hash != log2.hash

    def test_verify_correct_record(self):
        log = AuditLog(action=AuditAction.TOOL_CALL, user_id="user1", tool_name="kill_session")
        log.seal(GENESIS_HASH)
        assert log.verify(GENESIS_HASH) is True

    def test_verify_tampered_record_fails(self):
        log = AuditLog(action=AuditAction.TOOL_CALL, user_id="user1", tool_name="kill_session")
        log.seal(GENESIS_HASH)
        # 篡改内容
        log.user_id = "hacker"
        assert log.verify(GENESIS_HASH) is False

    def test_verify_wrong_prev_hash_fails(self):
        log = AuditLog(action=AuditAction.TOOL_CALL, user_id="user1", tool_name="kill_session")
        log.seal(GENESIS_HASH)
        wrong_prev = "a" * 64
        assert log.verify(wrong_prev) is False

    def test_hash_chain_second_record(self):
        log1 = AuditLog(action=AuditAction.SESSION_CREATE, user_id="user1", session_id="sess1")
        log1.seal(GENESIS_HASH)

        log2 = AuditLog(action=AuditAction.TOOL_CALL, user_id="user1", tool_name="query", session_id="sess1")
        log2.seal(log1.hash)

        assert log2.prev_hash == log1.hash
        assert log2.verify(log1.hash) is True


class TestAuditLoggerHashChain:
    """AuditLogger哈希链集成测试"""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._log_file = os.path.join(self._tmpdir, "audit.jsonl")
        # 创建独立的logger，使用临时文件
        self._logger = AuditLogger()
        self._logger._log_file = self._log_file
        self._logger._ensure_storage()
        # 清除全局单例避免污染
        import src.gateway.audit as audit_mod
        audit_mod._audit_logger = None

    def teardown_method(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        import src.gateway.audit as audit_mod
        audit_mod._audit_logger = None

    def _make_logger(self) -> AuditLogger:
        """创建使用临时文件的独立logger（不自动加载默认文件）"""
        logger = AuditLogger(log_file=self._log_file, auto_load=False)
        logger._ensure_storage()
        return logger

    def test_log_seals_hash_chain(self):
        logger = self._make_logger()
        log1 = logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        log2 = logger.log_action(AuditAction.TOOL_CALL, user_id="u1", tool_name="query", session_id="s1")

        assert log1.prev_hash == GENESIS_HASH
        assert log2.prev_hash == log1.hash
        assert log2.verify(log1.hash) is True

    def test_verify_chain_valid(self):
        logger = self._make_logger()
        logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        logger.log_action(AuditAction.TOOL_CALL, user_id="u1", tool_name="q1", session_id="s1")
        logger.log_action(AuditAction.TOOL_RESULT, user_id="u1", tool_name="q1", session_id="s1")

        is_valid, err, idx = logger.verify_chain()
        assert is_valid is True
        assert err is None
        assert idx is None

    def test_verify_chain_detects_tampering(self):
        logger = self._make_logger()
        logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        logger.log_action(AuditAction.TOOL_CALL, user_id="u1", tool_name="q1", session_id="s1")
        logger.log_action(AuditAction.TOOL_RESULT, user_id="u1", tool_name="q1", session_id="s1")

        # 篡改第二条记录
        logger._logs[1].user_id = "hacker"
        # 重新计算哈希（模拟篡改后保存）
        logger._logs[1].hash = logger._logs[1]._compute_hash(GENESIS_HASH)

        is_valid, err, idx = logger.verify_chain()
        assert is_valid is False
        assert idx == 1

    def test_detect_tampering_reports_broken_link(self):
        logger = self._make_logger()
        logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        logger.log_action(AuditAction.TOOL_CALL, user_id="u1", tool_name="q1", session_id="s1")

        # 篡改prev_hash
        logger._logs[1].prev_hash = "b" * 64
        logger._logs[1].hash = logger._logs[1]._compute_hash("b" * 64)

        suspicious = logger.detect_tampering()
        assert len(suspicious) >= 1

    def test_persistence_reloads_with_hashes(self):
        logger = self._make_logger()
        log1 = logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        log2 = logger.log_action(AuditAction.TOOL_CALL, user_id="u1", tool_name="q1", session_id="s1")

        # 重新创建logger（模拟重启），使用相同文件
        logger2 = AuditLogger(log_file=self._log_file, auto_load=False)
        logger2._ensure_storage()
        logger2._load()

        assert len(logger2._logs) == 2
        assert logger2._logs[0].hash == log1.hash
        assert logger2._logs[1].hash == log2.hash
        # 重新验证链
        is_valid, _, _ = logger2.verify_chain()
        assert is_valid is True

    def test_get_stats(self):
        logger = self._make_logger()
        logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        logger.log_action(AuditAction.SESSION_CLOSE, user_id="u1", session_id="s1")
        stats = logger.get_stats()
        assert stats["total_records"] == 2
        assert stats["genesis_hash"] == GENESIS_HASH
        assert stats["chain_valid"] is True

    def test_query_logs(self):
        logger = self._make_logger()
        logger.log_action(AuditAction.SESSION_CREATE, user_id="u1", session_id="s1")
        logger.log_action(AuditAction.SESSION_CREATE, user_id="u2", session_id="s2")
        logger.log_action(AuditAction.TOOL_CALL, user_id="u1", tool_name="q1", session_id="s1")

        results = logger.query(user_id="u1")
        assert len(results) == 2

        results = logger.query(action=AuditAction.TOOL_CALL)
        assert len(results) == 1
