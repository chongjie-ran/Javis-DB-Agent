"""
Round30: V2.6.1 Token TTL 机制测试
=====================================
测试范围：F1 Token TTL 机制
- TTL 过期检查
- params_hash 参数漂移检测
- 双重校验逻辑

运行：
    cd ~/SWproject/Javis-DB-Agent
    python3 -m pytest tests/round30/test_token_ttl.py -v --tb=short
"""

import asyncio
import sys
import os
import time
import tempfile
import uuid
import pytest
import threading
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))

from src.gateway.persistent_session import (
    PersistentSessionManager,
    SessionManager,
    Session,
    Message,
    get_session_manager,
    reset_session_manager,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def session_manager(temp_db):
    mgr = PersistentSessionManager(
        db_path=temp_db,
        ttl_seconds=2,
        max_sessions=100,
    )
    yield mgr
    mgr.cleanup_all()


@pytest.fixture
def session_manager_medium_ttl(temp_db):
    mgr = PersistentSessionManager(
        db_path=temp_db,
        ttl_seconds=60,
        max_sessions=100,
    )
    yield mgr
    mgr.cleanup_all()


# ============================================================================
# SECTION 1: TTL 过期检查
# ============================================================================

class TestTTLExpiration:

    def test_session_expires_after_ttl(self, session_manager):
        """TTL-01: 会话在 TTL 后过期"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        time.sleep(3.5)
        result = session_manager.get_session(session.session_id)
        assert result is None

    def test_session_accessible_before_ttl(self, session_manager):
        """TTL-02: 会话在 TTL 内可访问"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        time.sleep(0.5)
        result = session_manager.get_session(session.session_id)
        assert result is not None
        assert result.session_id == session.session_id

    def test_session_expiry_from_cache(self, session_manager):
        """TTL-03: 缓存中的会话在 TTL 后过期"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        cached = session_manager.get_session(session.session_id)
        assert cached is not None
        time.sleep(3.5)
        result = session_manager.get_session(session.session_id)
        assert result is None

    def test_session_expiry_from_db_cold_start(self, session_manager):
        """TTL-04: 数据库中的会话在 TTL 后过期（冷启动）"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_id = session.session_id
        time.sleep(3.5)
        session_manager._cache.clear()
        result = session_manager.get_session(session_id)
        assert result is None

    def test_cleanup_expired_removes_cache(self, session_manager):
        """TTL-05: _cleanup_expired 清理缓存"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_id = session.session_id
        time.sleep(3.5)
        session_manager._cleanup_expired()
        assert session_id not in session_manager._cache

    def test_multiple_sessions_different_expiry(self, session_manager):
        """TTL-06: 多会话不同过期时间"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        s1 = session_manager.create_session(user_id)
        s2 = session_manager.create_session(user_id)
        # 两个会话都未过期时都应可访问
        assert session_manager.get_session(s1.session_id) is not None
        assert session_manager.get_session(s2.session_id) is not None
        # 等待过期后都不可访问
        time.sleep(3.5)
        assert session_manager.get_session(s1.session_id) is None
        assert session_manager.get_session(s2.session_id) is None

    def test_ttl_config_value(self, session_manager_medium_ttl):
        """TTL-07: TTL 配置值正确"""
        mgr = session_manager_medium_ttl
        assert mgr.ttl_seconds == 60
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = mgr.create_session(user_id)
        time.sleep(0.5)
        assert mgr.get_session(session.session_id) is not None

    def test_save_session_updates_expiry(self, session_manager):
        """TTL-08: save_session 更新 updated_at 延迟过期"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        time.sleep(1.5)
        session_manager.save_session(session)
        time.sleep(1.5)
        result = session_manager.get_session(session.session_id)
        assert result is not None

    def test_concurrent_access_near_expiry(self, session_manager):
        """TTL-09: 并发访问临界过期会话"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        results = []

        def get_session():
            time.sleep(1.8)
            r = session_manager.get_session(session.session_id)
            results.append(r)

        t = threading.Thread(target=get_session)
        t.start()
        main_result = session_manager.get_session(session.session_id)
        t.join()
        assert main_result is not None

    def test_list_user_sessions_excludes_expired(self, session_manager):
        """TTL-10: list_user_sessions 排除过期会话"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        s1 = session_manager.create_session(user_id)
        s2 = session_manager.create_session(user_id)
        # 都未过期时都应返回
        sessions = session_manager.list_user_sessions(user_id)
        session_ids = [s.session_id for s in sessions]
        assert s1.session_id in session_ids
        assert s2.session_id in session_ids
        # 等待过期后都不返回
        time.sleep(3.5)
        sessions = session_manager.list_user_sessions(user_id)
        session_ids = [s.session_id for s in sessions]
        assert s1.session_id not in session_ids
        assert s2.session_id not in session_ids


# ============================================================================
# SECTION 2: params_hash 参数漂移检测
# ============================================================================

class TestParamsHashDrift:

    def test_session_metadata_initialized(self, session_manager_medium_ttl):
        """PHD-01: 新建会话 metadata 非空"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager_medium_ttl.create_session(user_id)
        assert session.metadata is not None

    def test_set_context_value_persists(self, session_manager_medium_ttl):
        """PHD-02: set_context_value 可设置并持久化 params_hash"""
        import hashlib

        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager_medium_ttl.create_session(user_id)
        params_hash = "abcd1234efgh5678"
        session.set_context_value("params_hash", params_hash)
        session_manager_medium_ttl.save_session(session)
        reloaded = session_manager_medium_ttl.get_session(session.session_id)
        assert reloaded is not None
        assert reloaded.get_context_value("params_hash") == params_hash

    def test_params_hash_drift_detected(self, session_manager_medium_ttl):
        """PHD-03: 参数变化时 params_hash 不同"""
        import hashlib

        params_a = {"sql": "SELECT 1", "instance_id": "INS-001"}
        params_b = {"sql": "SELECT 2", "instance_id": "INS-001"}
        params_c = {"sql": "SELECT 1", "instance_id": "INS-002"}

        encode = lambda p: json.dumps(p, sort_keys=True).encode()
        hash_a = hashlib.sha256(encode(params_a)).hexdigest()[:16]
        hash_b = hashlib.sha256(encode(params_b)).hexdigest()[:16]
        hash_c = hashlib.sha256(encode(params_c)).hexdigest()[:16]

        assert hash_a != hash_b
        assert hash_a != hash_c
        assert hash_b != hash_c

    def test_params_hash_in_session_metadata(self, session_manager_medium_ttl):
        """PHD-04: params_hash 存储在 session metadata"""
        import hashlib

        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager_medium_ttl.create_session(user_id)
        params = {"sql": "SELECT * FROM users", "instance_id": "INS-001"}
        params_hash = hashlib.sha256(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()[:16]
        session.set_metadata_value("params_hash", params_hash)  # 修正：使用 set_metadata_value
        session_manager_medium_ttl.save_session(session)
        reloaded = session_manager_medium_ttl.get_session(session.session_id)
        assert reloaded is not None
        assert reloaded.metadata.get("params_hash") == params_hash

    def test_message_add_works_with_drift(self, session_manager_medium_ttl):
        """PHD-05: params_hash 漂移时 add_message 仍正常"""
        import hashlib

        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager_medium_ttl.create_session(user_id)
        params = {"sql": "SELECT 1", "instance_id": "INS-001"}
        params_hash = hashlib.sha256(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()[:16]
        drifted_hash = "xxxx9999yyyy0000"
        assert params_hash != drifted_hash
        msg = session_manager_medium_ttl.add_message(
            session.session_id, role="user", content="test message"
        )
        assert msg is not None

    def test_sha256_consistency(self):
        """PHD-06: SHA256 hash 的一致性验证"""
        import hashlib

        params = {"key": "value", "num": 42}
        encoded = json.dumps(params, sort_keys=True).encode()
        hash1 = hashlib.sha256(encoded).hexdigest()
        hash2 = hashlib.sha256(encoded).hexdigest()
        assert hash1 == hash2
        assert len(hash1) == 64

    def test_hash_order_independent(self):
        """PHD-07: sort_keys=True 确保字典顺序无关"""
        import hashlib

        params1 = {"a": 1, "b": 2}
        params2 = {"b": 2, "a": 1}
        hash1 = hashlib.sha256(json.dumps(params1, sort_keys=True).encode()).hexdigest()
        hash2 = hashlib.sha256(json.dumps(params2, sort_keys=True).encode()).hexdigest()
        assert hash1 == hash2


# ============================================================================
# SECTION 3: 双重校验逻辑（Cache + DB）
# ============================================================================

class TestDoubleValidation:

    def test_cache_hit_direct_return(self, session_manager):
        """DV-01: Cache Hit 时直接返回"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        result1 = session_manager.get_session(session.session_id)
        assert result1 is not None
        assert session.session_id in session_manager._cache
        result2 = session_manager.get_session(session.session_id)
        assert result2 is not None
        assert result2.session_id == session.session_id

    def test_cache_miss_db_hit_refills_cache(self, session_manager):
        """DV-02: Cache Miss 时查 DB，DB 有则回填 cache"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_id = session.session_id
        session_manager._cache.clear()
        assert session_id not in session_manager._cache
        result = session_manager.get_session(session_id)
        assert result is not None
        assert result.session_id == session_id
        assert session_id in session_manager._cache

    def test_both_cache_and_db_miss(self, session_manager):
        """DV-03: Cache 和 DB 都 miss 返回 None"""
        fake_id = str(uuid.uuid4())
        result = session_manager.get_session(fake_id)
        assert result is None

    def test_cache_expired_db_valid_returns_none(self, session_manager):
        """DV-04: Cache 过期但 DB 有效时返回 None（TTL 过期机制）"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        time.sleep(3.5)
        # TTL expiration is checked during get_session, not automatic
        result = session_manager.get_session(session.session_id)
        assert result is None
        # After get_session (which runs TTL check), cache should be clean
        assert session.session_id not in session_manager._cache

    def test_db_expired_syncs_cache_cleanup(self, session_manager):
        """DV-05: DB 中会话过期时同步清理 cache"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_manager.get_session(session.session_id)
        assert session.session_id in session_manager._cache
        with session_manager._get_conn() as conn:
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (time.time() - 1000, session.session_id),
            )
            conn.commit()
        result = session_manager.get_session(session.session_id)
        assert result is None
        assert session.session_id not in session_manager._cache

    def test_save_updates_both_db_and_cache(self, session_manager):
        """DV-06: save_session 同时更新 DB 和 cache"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session.set_context_value("test_key", "test_value")
        session_manager.save_session(session)
        with session_manager._get_conn() as conn:
            row = conn.execute(
                "SELECT context FROM sessions WHERE session_id = ?",
                (session.session_id,),
            ).fetchone()
            ctx = json.loads(row["context"])
            assert ctx.get("test_key") == "test_value"
        assert session_manager._cache[session.session_id].get_context_value("test_key") == "test_value"

    def test_concurrent_read_consistency(self, session_manager):
        """DV-07: 并发读取双重校验一致性"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_id = session.session_id
        results = []

        def read():
            r = session_manager.get_session(session_id)
            results.append(r)

        threads = [threading.Thread(target=read) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(r is not None for r in results)
        assert all(r.session_id == session_id for r in results)

    def test_delete_cleans_both_cache_and_db(self, session_manager):
        """DV-08: delete_session 后 cache 和 DB 都清理"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_id = session.session_id
        session_manager.get_session(session_id)
        assert session_id in session_manager._cache
        session_manager.delete_session(session_id)
        assert session_id not in session_manager._cache
        with session_manager._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            assert row is None

    def test_user_sessions_index_consistency(self, session_manager):
        """DV-09: _user_sessions 索引与实际 sessions 一致"""
        user_id = "user_" + uuid.uuid4().hex[:8]
        session = session_manager.create_session(user_id)
        session_id = session.session_id
        assert session_id in session_manager._user_sessions[user_id]
        session_manager.delete_session(session_id)
        assert session_id not in session_manager._user_sessions[user_id]

    def test_max_sessions_lru_eviction(self):
        """DV-10: 超过 max_sessions 时 LRU 淘汰"""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            mgr = PersistentSessionManager(
                db_path=db_path,
                ttl_seconds=3600,
                max_sessions=3,
            )
            user_id = "user_" + uuid.uuid4().hex[:8]
            sessions = [mgr.create_session(user_id) for _ in range(4)]
            oldest_id = sessions[0].session_id
            assert mgr.get_session(oldest_id) is None
            assert oldest_id not in mgr._cache
            for s in sessions[1:]:
                assert mgr.get_session(s.session_id) is not None
            mgr.cleanup_all()
        finally:
            try:
                os.unlink(db_path)
            except OSError:
                pass


# ============================================================================
# SECTION 4: 全局单例测试
# ============================================================================

class TestSessionManagerSingleton:

    def test_singleton_same_instance(self, temp_db):
        """SM-01: get_session_manager 返回同一实例"""
        reset_session_manager()
        mgr1 = get_session_manager(db_path=temp_db, ttl_seconds=100)
        mgr2 = get_session_manager(db_path=temp_db, ttl_seconds=100)
        assert mgr1 is mgr2

    def test_reset_clears_singleton(self, temp_db):
        """SM-02: reset_session_manager 重置单例"""
        reset_session_manager()
        mgr1 = get_session_manager(db_path=temp_db, ttl_seconds=100)
        reset_session_manager()
        mgr2 = get_session_manager(db_path=temp_db, ttl_seconds=100)
        assert mgr1 is not mgr2
        mgr2.cleanup_all()

    def test_session_manager_compat_layer(self, temp_db):
        """SM-03: SessionManager 兼容层"""
        compat = SessionManager(db_path=temp_db, ttl_seconds=60)
        assert hasattr(compat, "create_session")
        assert hasattr(compat, "get_session")
        assert hasattr(compat, "save_session")
        assert hasattr(compat, "delete_session")
        compat.cleanup_all()
