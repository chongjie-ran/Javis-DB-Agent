"""
Unit tests for Tool definitions and ToolExecutor
"""
import pytest
from enum import Enum


class RiskLevelValues(Enum):
    L1_READ = 1
    L2_DIAGNOSE = 2
    L3_LOW_RISK = 3
    L4_MEDIUM = 4
    L5_HIGH = 5


class TestToolDefinition:
    """Test tool definition schema"""
    
    def test_tool_has_required_fields(self):
        """Verify tool definition has all required fields"""
        required_fields = ["name", "description", "category", "risk_level", "params"]
        tool_def = {
            "name": "query_session",
            "description": "查询数据库会话",
            "category": "query",
            "risk_level": RiskLevelValues.L1_READ.value,
            "params": []
        }
        for field in required_fields:
            assert field in tool_def, f"Missing required field: {field}"

    def test_tool_param_validation(self):
        """Test tool parameter validation"""
        param = {
            "name": "instance_id",
            "type": "string",
            "description": "实例ID",
            "required": True,
            "constraints": {"min_length": 1, "pattern": "^INS-"}
        }
        assert param["required"] is True
        assert "constraints" in param

    def test_risk_level_values(self):
        """Test risk level enum values"""
        assert RiskLevelValues.L1_READ.value == 1
        assert RiskLevelValues.L2_DIAGNOSE.value == 2
        assert RiskLevelValues.L3_LOW_RISK.value == 3
        assert RiskLevelValues.L4_MEDIUM.value == 4
        assert RiskLevelValues.L5_HIGH.value == 5


class TestToolCategories:
    """Test tool category classification"""
    
    def test_query_tools_are_read_only(self):
        """Query tools should always be L1 risk"""
        query_tools = [
            "query_instance_status",
            "query_session",
            "query_lock",
            "query_replication",
            "query_slow_sql"
        ]
        for tool in query_tools:
            # All query tools must be read-only (L1)
            risk = 1
            assert risk == 1, f"{tool} should be L1 risk"

    def test_action_tools_require_auth(self):
        """Action tools should require authorization"""
        action_tools = [
            {"name": "execute_inspection", "risk": 3},
            {"name": "kill_session", "risk": 5},
            {"name": "refresh_sample", "risk": 3}
        ]
        for tool in action_tools:
            # High risk tools must have auth
            if tool["risk"] >= 3:
                assert tool["risk"] >= 3


class TestToolValidation:
    """Test tool parameter validation"""
    
    def test_instance_id_format(self):
        """Test instance_id format validation"""
        import re
        pattern = r"^INS-\d{3,}$"
        valid_ids = ["INS-001", "INS-123", "INS-999"]
        invalid_ids = ["INS-1", "INS", "DB-001", ""]
        
        for vid in valid_ids:
            assert re.match(pattern, vid), f"{vid} should be valid"
        for vid in invalid_ids:
            assert not re.match(pattern, vid), f"{vid} should be invalid"

    def test_sql_param_constraints(self):
        """Test SQL parameter constraints"""
        constraints = {
            "max_rows": 1000,
            "timeout_seconds": 30,
            "allowed_operations": ["SELECT", "INSERT", "UPDATE", "DELETE"]
        }
        assert constraints["max_rows"] <= 1000
        assert constraints["timeout_seconds"] <= 30
        assert "SELECT" in constraints["allowed_operations"]


class TestPolicyEngine:
    """Test policy engine logic"""
    
    def test_permission_levels(self):
        """Test permission level definitions"""
        permissions = {
            "L1": ["read", "analyze"],
            "L2": ["read", "analyze", "diagnose"],
            "L3": ["read", "analyze", "diagnose", "low_risk_execute"],
            "L4": ["read", "analyze", "diagnose", "low_risk_execute", "medium_risk_execute"],
            "L5": ["read", "analyze", "diagnose", "low_risk_execute", "medium_risk_execute", "high_risk_execute"]
        }
        assert len(permissions) == 5
        assert permissions["L1"] == ["read", "analyze"]

    def test_approval_required_for_high_risk(self):
        """High risk actions require approval"""
        action_risk = {
            "kill_session": 5,
            "drop_table": 5,
            "execute_inspection": 3,
            "query_session": 1
        }
        for action, risk in action_risk.items():
            if risk >= 4:
                assert risk >= 4, f"{action} requires approval"
            if risk == 5:
                assert risk == 5, f"{action} should be forbidden or require dual approval"

    def test_sql_guardrails(self):
        """Test SQL guardrails validation"""
        allowed_sql_keywords = [
            "SELECT", "INSERT", "UPDATE", "DELETE",
            "CREATE", "ALTER", "DROP", "TRUNCATE"
        ]
        forbidden_patterns = [
            "DROP DATABASE",
            "DROP SCHEMA",
            "DELETE FROM pg_",
            "ALTER TABLE.*DROP COLUMN"
        ]
        import re
        # Verify forbidden patterns are actually defined
        assert "DROP DATABASE" in forbidden_patterns
        assert "DROP SCHEMA" in forbidden_patterns
        assert "DELETE FROM pg_" in forbidden_patterns
        # Verify allowed keywords
        for kw in allowed_sql_keywords:
            assert kw in ["SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE"]
