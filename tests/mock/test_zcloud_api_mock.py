"""
API Mock测试框架 - 第二轮测试
用于模拟zCloud平台API接口
"""
import pytest
from unittest.mock import AsyncMock, Mock, MagicMock
from typing import Dict, Any, Optional
import json


class MockZCloudAPIResponse:
    """Mock zCloud API响应封装"""
    
    def __init__(self, status_code: int = 200, data: Any = None, error: Optional[str] = None):
        self.status_code = status_code
        self.data = data
        self.error = error
    
    def json(self):
        if self.error:
            return {"error": self.error}
        return self.data
    
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}: {self.error or 'Unknown error'}")


class MockZCloudInstanceAPI:
    """Mock zCloud实例API"""
    
    def __init__(self):
        self._instances = {
            "INS-TEST-001": {
                "instance_id": "INS-TEST-001",
                "instance_name": "test_db_primary",
                "host": "192.168.1.100",
                "port": 5432,
                "version": "PostgreSQL 16.3",
                "uptime_seconds": 864000,
                "state": "running",
                "metrics": {
                    "cpu_usage_percent": 45.5,
                    "memory_usage_percent": 62.3,
                    "disk_usage_percent": 78.1,
                    "connections": 85,
                    "max_connections": 200
                }
            }
        }
    
    async def get_instance_status(self, instance_id: str) -> Dict[str, Any]:
        """获取实例状态"""
        if instance_id not in self._instances:
            raise Exception(f"实例不存在: {instance_id}")
        return self._instances[instance_id]
    
    async def list_instances(self) -> list:
        """列出所有实例"""
        return list(self._instances.values())
    
    async def restart_instance(self, instance_id: str) -> Dict[str, Any]:
        """重启实例"""
        if instance_id not in self._instances:
            raise Exception(f"实例不存在: {instance_id}")
        return {"status": "restarting", "instance_id": instance_id}


class MockZCloudSessionAPI:
    """Mock zCloud会话API"""
    
    def __init__(self):
        self._sessions = {
            "INS-TEST-001": [
                {
                    "pid": 1234,
                    "state": "active",
                    "duration_seconds": 300,
                    "query": "SELECT * FROM orders WHERE status = 'pending'",
                    "wait_event_type": "Lock",
                    "wait_event": "lock_tuple",
                    "backend_type": "client backend",
                    "application_name": "app_server_1"
                },
                {
                    "pid": 5678,
                    "state": "idle in transaction",
                    "duration_seconds": 600,
                    "query": "BEGIN; UPDATE accounts SET balance = balance - 100;",
                    "wait_event_type": None,
                    "backend_type": "client backend",
                    "application_name": "batch_job"
                }
            ]
        }
    
    async def get_sessions(self, instance_id: str, limit: int = 10) -> Dict[str, Any]:
        """获取会话列表"""
        sessions = self._sessions.get(instance_id, [])
        return {
            "instance_id": instance_id,
            "sessions": sessions[:limit],
            "total_count": len(sessions)
        }
    
    async def kill_session(self, instance_id: str, pid: int) -> Dict[str, Any]:
        """终止会话"""
        sessions = self._sessions.get(instance_id, [])
        pid_exists = any(s["pid"] == pid for s in sessions)
        if not pid_exists:
            raise Exception(f"会话不存在: PID {pid}")
        return {"status": "killed", "instance_id": instance_id, "pid": pid}


class MockZCloudLockAPI:
    """Mock zCloud锁API"""
    
    def __init__(self):
        self._locks = {
            "INS-TEST-001": [
                {
                    "lock_type": "relation",
                    "mode": "ShareRowExclusiveLock",
                    "granted": True,
                    "pid": 5678,
                    "query": "UPDATE accounts SET balance = balance - 100",
                    "relation": "accounts"
                },
                {
                    "lock_type": "tuple",
                    "mode": "ForUpdate",
                    "granted": False,
                    "pid": 1234,
                    "query": "SELECT * FROM orders WHERE status = 'pending'",
                    "relation": "orders"
                }
            ]
        }
    
    async def get_locks(self, instance_id: str) -> Dict[str, Any]:
        """获取锁信息"""
        locks = self._locks.get(instance_id, [])
        return {
            "instance_id": instance_id,
            "locks": locks,
            "lock_wait_chain": self._build_wait_chain(locks)
        }
    
    def _build_wait_chain(self, locks: list) -> list:
        """构建锁等待链"""
        chain = []
        for lock in locks:
            if not lock["granted"]:
                blocking = next((l for l in locks if l["granted"] and l["pid"] != lock["pid"]), None)
                if blocking:
                    chain.append({
                        "blocked_pid": lock["pid"],
                        "blocked_query": lock["query"],
                        "blocking_pid": blocking["pid"],
                        "blocking_query": blocking["query"]
                    })
        return chain


class MockZCloudAlertAPI:
    """Mock zCloud告警API"""
    
    def __init__(self):
        self._alerts = {
            "ALT-20260328-001": {
                "alert_id": "ALT-20260328-001",
                "alert_code": "ALT_LOCK_WAIT",
                "name": "锁等待超时",
                "severity": "warning",
                "instance_id": "INS-TEST-001",
                "triggered_at": "2026-03-28T10:00:00Z",
                "status": "firing",
                "labels": {"severity": "warning", "category": "lock"},
                "annotations": {
                    "summary": "实例 INS-TEST-001 发生锁等待超时",
                    "description": "等待时间超过30秒，涉及2个会话"
                },
                "metrics": {
                    "wait_time_ms": 35000,
                    "blocked_sessions": 2,
                    "lock_count": 3
                }
            }
        }
    
    async def get_alert_detail(self, alert_id: str) -> Dict[str, Any]:
        """获取告警详情"""
        if alert_id not in self._alerts:
            raise Exception(f"告警不存在: {alert_id}")
        return self._alerts[alert_id]
    
    async def list_alerts(self, instance_id: str = None, status: str = None) -> list:
        """列出告警"""
        alerts = list(self._alerts.values())
        if instance_id:
            alerts = [a for a in alerts if a["instance_id"] == instance_id]
        if status:
            alerts = [a for a in alerts if a["status"] == status]
        return alerts
    
    async def update_alert_status(self, alert_id: str, status: str) -> Dict[str, Any]:
        """更新告警状态"""
        if alert_id not in self._alerts:
            raise Exception(f"告警不存在: {alert_id}")
        self._alerts[alert_id]["status"] = status
        return self._alerts[alert_id]


class MockZCloudInspectionAPI:
    """Mock zCloud巡检API"""
    
    def __init__(self):
        self._inspections = {}
    
    async def trigger_inspection(self, instance_id: str, inspection_type: str = "full") -> Dict[str, Any]:
        """触发巡检"""
        inspection_id = f"INS-{instance_id}-{len(self._inspections)}"
        self._inspections[inspection_id] = {
            "inspection_id": inspection_id,
            "instance_id": instance_id,
            "inspection_type": inspection_type,
            "status": "running",
            "started_at": "2026-03-28T10:00:00Z"
        }
        return self._inspections[inspection_id]
    
    async def get_inspection_result(self, inspection_id: str) -> Dict[str, Any]:
        """获取巡检结果"""
        if inspection_id not in self._inspections:
            raise Exception(f"巡检不存在: {inspection_id}")
        return self._inspections[inspection_id]


class MockZCloudAPIClient:
    """Mock zCloud API客户端（聚合所有Mock API）"""
    
    def __init__(self):
        self.instances = MockZCloudInstanceAPI()
        self.sessions = MockZCloudSessionAPI()
        self.locks = MockZCloudLockAPI()
        self.alerts = MockZCloudAlertAPI()
        self.inspections = MockZCloudInspectionAPI()
    
    async def health_check(self) -> bool:
        """健康检查"""
        return True


@pytest.fixture
def mock_zcloud_client():
    """Mock zCloud API客户端fixture"""
    return MockZCloudAPIClient()


class TestMockZCloudAPI:
    """Mock zCloud API测试"""
    
    @pytest.mark.asyncio
    async def test_get_instance_status(self, mock_zcloud_client):
        """测试获取实例状态"""
        result = await mock_zcloud_client.instances.get_instance_status("INS-TEST-001")
        
        assert result is not None
        assert result["instance_id"] == "INS-TEST-001"
        assert result["state"] == "running"
        assert "metrics" in result
    
    @pytest.mark.asyncio
    async def test_get_sessions(self, mock_zcloud_client):
        """测试获取会话列表"""
        result = await mock_zcloud_client.sessions.get_sessions("INS-TEST-001")
        
        assert "sessions" in result
        assert len(result["sessions"]) > 0
        assert result["total_count"] > 0
    
    @pytest.mark.asyncio
    async def test_get_locks(self, mock_zcloud_client):
        """测试获取锁信息"""
        result = await mock_zcloud_client.locks.get_locks("INS-TEST-001")
        
        assert "locks" in result
        assert "lock_wait_chain" in result
    
    @pytest.mark.asyncio
    async def test_get_alert_detail(self, mock_zcloud_client):
        """测试获取告警详情"""
        result = await mock_zcloud_client.alerts.get_alert_detail("ALT-20260328-001")
        
        assert result["alert_id"] == "ALT-20260328-001"
        assert result["alert_code"] == "ALT_LOCK_WAIT"
    
    @pytest.mark.asyncio
    async def test_trigger_inspection(self, mock_zcloud_client):
        """测试触发巡检"""
        result = await mock_zcloud_client.inspections.trigger_inspection(
            "INS-TEST-001",
            "full"
        )
        
        assert "inspection_id" in result
        assert result["instance_id"] == "INS-TEST-001"
        assert result["status"] == "running"
    
    @pytest.mark.asyncio
    async def test_kill_session(self, mock_zcloud_client):
        """测试终止会话"""
        result = await mock_zcloud_client.sessions.kill_session("INS-TEST-001", 5678)
        
        assert result["status"] == "killed"
        assert result["pid"] == 5678
    
    @pytest.mark.asyncio
    async def test_health_check(self, mock_zcloud_client):
        """测试健康检查"""
        result = await mock_zcloud_client.health_check()
        assert result is True


class TestMockAPIErrorHandling:
    """Mock API错误处理测试"""
    
    @pytest.mark.asyncio
    async def test_instance_not_found(self):
        """测试实例不存在错误"""
        client = MockZCloudAPIClient()
        
        with pytest.raises(Exception) as exc_info:
            await client.instances.get_instance_status("INS-INVALID")
        
        assert "实例不存在" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_alert_not_found(self):
        """测试告警不存在错误"""
        client = MockZCloudAPIClient()
        
        with pytest.raises(Exception) as exc_info:
            await client.alerts.get_alert_detail("ALT-INVALID")
        
        assert "告警不存在" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_kill_nonexistent_session(self):
        """测试终止不存在的会话"""
        client = MockZCloudAPIClient()
        
        with pytest.raises(Exception) as exc_info:
            await client.sessions.kill_session("INS-TEST-001", 99999)
        
        assert "会话不存在" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
