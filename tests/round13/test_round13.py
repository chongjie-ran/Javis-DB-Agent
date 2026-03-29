"""Round 13 Tests - P0: Dashboard监控面板 + 审计日志查看器 + 用户认证系统"""
import os
import sys
import pytest
import tempfile
import time

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


@pytest.fixture(autouse=True)
def reset_auth_singleton():
    """每个测试前重置全局auth单例和auth数据文件，确保测试隔离"""
    import shutil
    from pathlib import Path
    from src.api import auth as auth_module

    # 保存原始单例
    original = auth_module._auth_manager
    auth_module._auth_manager = None

    # 备份并删除auth数据文件
    project_data = Path(__file__).resolve().parents[2] / "data"
    users_file = project_data / "users.json"
    tokens_file = project_data / "tokens.json"

    users_backup = None
    tokens_backup = None
    if users_file.exists():
        users_backup = users_file.read_bytes()
        users_file.unlink()
    if tokens_file.exists():
        tokens_backup = tokens_file.read_bytes()
        tokens_file.unlink()

    yield

    # 恢复
    auth_module._auth_manager = original
    # 恢复备份
    if users_backup is not None:
        users_file.write_bytes(users_backup)
    if tokens_backup is not None:
        tokens_file.write_bytes(tokens_backup)


# ===== P0-3: Auth Tests =====

class TestAuthModule:
    """P0-3: 用户认证系统测试"""

    def test_password_hash_and_verify(self):
        """密码哈希和验证"""
        from src.api.auth import hash_password, verify_password

        pw = "test_password_123"
        hashed, salt = hash_password(pw)

        assert hashed != pw
        assert salt is not None
        assert len(salt) > 0
        assert verify_password(pw, hashed, salt) is True
        assert verify_password("wrong_password", hashed, salt) is False

    def test_password_hash_different_salts(self):
        """不同盐值产生不同哈希"""
        from src.api.auth import hash_password

        pw = "test123"
        h1, s1 = hash_password(pw)
        h2, s2 = hash_password(pw)

        assert h1 != h2  # 不同盐值
        assert s1 != s2  # 盐值不同

    def test_user_creation(self):
        """用户创建和序列化"""
        from src.api.auth import User

        user = User(
            user_id="u123",
            username="testuser",
            password_hash="abc123",
            password_salt="saltxyz",
            role="user",
            created_at=time.time(),
        )

        d = user.to_dict()
        assert d["user_id"] == "u123"
        assert d["username"] == "testuser"
        assert d["role"] == "user"

        user2 = User.from_dict(d)
        assert user2.user_id == user.user_id
        assert user2.username == user.username

    def test_auth_manager_register(self):
        """用户注册"""
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.api.auth import AuthManager

            auth = AuthManager(
                users_file=Path(tmpdir) / "users.json",
                secret_file=Path(tmpdir) / "secret.key"
            )
            user = auth.register_user("alice", "alice123", role="user")

            assert user.username == "alice"
            assert user.role == "user"
            assert user.password_hash != "alice123"

            # 重复注册应报错
            with pytest.raises(ValueError, match="用户名已存在"):
                auth.register_user("alice", "another_pass")

    def test_auth_manager_authenticate(self):
        """用户认证"""
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.api.auth import AuthManager

            auth = AuthManager(
                users_file=Path(tmpdir) / "users.json",
                secret_file=Path(tmpdir) / "secret.key"
            )
            auth.register_user("bob", "bobpass", role="user")

            # 正确密码
            user = auth.authenticate("bob", "bobpass")
            assert user is not None
            assert user.username == "bob"

            # 错误密码
            assert auth.authenticate("bob", "wrongpass") is None

            # 不存在用户
            assert auth.authenticate("nobody", "pass") is None

    def test_jwt_token_creation_and_verify(self):
        """JWT Token创建和验证"""
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.api.auth import AuthManager

            auth = AuthManager(
                users_file=Path(tmpdir) / "users.json",
                secret_file=Path(tmpdir) / "secret.key"
            )
            auth.register_user("charlie", "charlie123", role="admin")

            user = auth.authenticate("charlie", "charlie123")
            token = auth.create_token(user, expires_in=3600)

            assert token is not None
            assert len(token) > 50  # JWT token长度

            # 验证token
            payload = auth.verify_token(token)
            assert payload is not None
            assert payload["username"] == "charlie"
            assert payload["role"] == "admin"

    def test_token_revocation(self):
        """Token撤销（登出）"""
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            from src.api.auth import AuthManager

            auth = AuthManager(
                users_file=Path(tmpdir) / "users.json",
                secret_file=Path(tmpdir) / "secret.key"
            )
            auth.register_user("dave", "dave123", role="user")
            user = auth.authenticate("dave", "dave123")
            token = auth.create_token(user)

            assert auth.verify_token(token) is not None

            auth.revoke_token(token)
            assert auth.verify_token(token) is None  # 已撤销


class TestAuthRoutes:
    """P0-3: 认证API路由测试"""

    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        from fastapi.testclient import TestClient
        from src.main import app
        return TestClient(app)

    def test_login_success(self, client):
        """登录成功"""
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert data["username"] == "admin"
        assert data["role"] == "admin"

    def test_login_wrong_password(self, client):
        """登录密码错误"""
        resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "wrongpassword"
        })
        assert resp.status_code == 401

    def test_login_unknown_user(self, client):
        """登录不存在的用户"""
        resp = client.post("/api/v1/auth/login", json={
            "username": "nonexistent",
            "password": "anypass"
        })
        assert resp.status_code == 401

    def test_logout(self, client):
        """登出"""
        # 先登录
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_resp.json()["token"]

        # 登出
        resp = client.post("/api/v1/auth/logout", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        assert resp.json()["message"] == "登出成功"

    def test_get_me_authenticated(self, client):
        """获取当前用户（已认证）"""
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_resp.json()["token"]

        resp = client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "admin"
        assert data["role"] == "admin"

    def test_get_me_no_token(self, client):
        """无Token访问应报错"""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 422  # Missing required header

    def test_get_me_bad_token(self, client):
        """无效Token访问应报错"""
        resp = client.get("/api/v1/auth/me", headers={
            "Authorization": "Bearer invalid_token_xyz"
        })
        assert resp.status_code == 401

    def test_register_new_user(self, client):
        """注册新用户"""
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_resp.json()["token"]

        resp = client.post("/api/v1/auth/register",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "newuser_round13", "password": "newpass123", "role": "user"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["message"] == "注册成功"
        assert data["data"]["username"] == "newuser_round13"

    def test_register_duplicate(self, client):
        """重复注册应失败"""
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_resp.json()["token"]

        resp = client.post("/api/v1/auth/register",
            headers={"Authorization": f"Bearer {token}"},
            json={"username": "admin", "password": "pass123", "role": "user"}
        )
        assert resp.status_code == 400

    def test_list_users_admin(self, client):
        """列出所有用户（admin）"""
        login_resp = client.post("/api/v1/auth/login", json={
            "username": "admin",
            "password": "admin123"
        })
        token = login_resp.json()["token"]

        resp = client.get("/api/v1/auth/users", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data["data"]
        assert any(u["username"] == "admin" for u in data["data"]["users"])


# ===== P0-1: Monitoring Tests =====

class TestMonitoringRoutes:
    """P0-1: Dashboard监控面板测试"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.main import app
        return TestClient(app)

    def test_get_monitoring_cards(self, client):
        """获取监控卡片数据"""
        resp = client.get("/api/v1/monitoring/cards")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        d = data["data"]
        assert "instance_total" in d
        assert "alert_count" in d
        assert "health_score" in d
        assert "health_trend" in d
        assert "last_updated" in d
        # Mock数据兜底，确保总有数
        assert isinstance(d["health_score"], (int, float))
        assert 0 <= d["health_score"] <= 100

    def test_get_alert_list(self, client):
        """获取告警列表"""
        resp = client.get("/api/v1/monitoring/alerts?status=active")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data
        assert "page" in data
        assert isinstance(data["alerts"], list)

    def test_alert_list_with_filters(self, client):
        """告警列表筛选"""
        resp = client.get("/api/v1/monitoring/alerts?status=active&severity=critical&page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    def test_get_health_score(self, client):
        """获取健康评分详情"""
        resp = client.get("/api/v1/monitoring/health-score")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        d = data["data"]
        assert "score" in d
        assert "level" in d  # healthy/degraded/unhealthy
        assert "factors" in d
        assert "trend" in d


# ===== P0-2: Audit Log Viewer Tests =====

class TestAuditRoutes:
    """P0-2: 审计日志查看器测试"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.main import app
        return TestClient(app)

    def test_list_audit_logs(self, client):
        """获取审计日志列表"""
        resp = client.get("/api/v1/audit/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data
        assert "total" in data
        assert "page" in data

    def test_list_audit_logs_with_filters(self, client):
        """带筛选条件查询审计日志"""
        resp = client.get("/api/v1/audit/logs?user_id=admin&action=session.create&page=1&page_size=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_list_audit_logs_pagination(self, client):
        """审计日志分页"""
        resp = client.get("/api/v1/audit/logs?page=2&page_size=10")
        assert resp.status_code == 200
        assert resp.json()["page"] == 2

    def test_verify_chain(self, client):
        """哈希链验证"""
        resp = client.get("/api/v1/audit/chain/verify")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_valid" in data
        assert "total_records" in data
        assert "genesis_hash" in data
        assert "checked_at" in data
        # is_valid应该是bool
        assert isinstance(data["is_valid"], bool)

    def test_detect_suspicious(self, client):
        """篡改检测"""
        resp = client.get("/api/v1/audit/chain/suspicious?hours=24")
        assert resp.status_code == 200
        data = resp.json()
        # 响应结构: {"code": 0, "message": "success", "data": {"suspicious_records": [...], ...}}
        assert "data" in data
        inner = data["data"]
        assert "suspicious_records" in inner
        assert isinstance(inner["suspicious_records"], list)

    def test_audit_stats(self, client):
        """审计统计"""
        resp = client.get("/api/v1/audit/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        d = data["data"]
        assert "total_records" in d
        assert "action_counts" in d

    def test_list_action_types(self, client):
        """列出动作类型"""
        resp = client.get("/api/v1/audit/actions")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "actions" in data["data"]
        actions = data["data"]["actions"]
        assert len(actions) > 0
        assert all("value" in a and "name" in a for a in actions)


# ===== P0-1+2: Integration Tests =====

class TestDashboardEnhanced:
    """Dashboard增强功能集成测试"""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from src.main import app
        return TestClient(app)

    def test_dashboard_html_loads(self, client):
        """Dashboard页面能正常加载"""
        resp = client.get("/dashboard/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    def test_api_health_still_works(self, client):
        """原有API健康检查仍然正常"""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
