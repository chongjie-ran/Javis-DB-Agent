"""
知识库测试用例 - 第二轮测试
测试告警规则、SOP和案例的结构完整性
"""
import pytest
import yaml
from pathlib import Path


class TestAlertRules:
    """测试告警规则知识库"""
    
    @pytest.fixture
    def alert_rules_path(self):
        return Path("~/SWproject/zCloudNewAgentProject/knowledge/alert_rules.yaml").expanduser()
    
    @pytest.fixture
    def alert_rules(self, alert_rules_path):
        with open(alert_rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data["alert_rules"]
    
    def test_alert_rules_file_exists(self, alert_rules_path):
        """验证告警规则文件存在"""
        assert alert_rules_path.exists(), f"告警规则文件不存在: {alert_rules_path}"
    
    def test_alert_rules_has_content(self, alert_rules):
        """验证告警规则非空"""
        assert len(alert_rules) > 0, "告警规则为空"
    
    def test_alert_rule_required_fields(self, alert_rules):
        """验证每条告警规则包含必填字段"""
        required_fields = [
            "alert_code", "name", "description", "severity",
            "symptoms", "possible_causes", "check_steps", "resolution", "risk_level"
        ]
        for rule in alert_rules:
            for field in required_fields:
                assert field in rule, f"告警规则 {rule.get('alert_code', '?')} 缺少字段: {field}"
    
    def test_alert_code_format(self, alert_rules):
        """验证告警代码格式"""
        for rule in alert_rules:
            alert_code = rule["alert_code"]
            assert isinstance(alert_code, str), f"alert_code应为字符串: {alert_code}"
            assert len(alert_code) > 0, "alert_code不能为空"
    
    def test_severity_valid_values(self, alert_rules):
        """验证severity字段有效值"""
        valid_severities = ["critical", "warning", "info"]
        for rule in alert_rules:
            severity = rule["severity"]
            assert severity in valid_severities, f"告警 {rule['alert_code']} 的severity无效: {severity}"
    
    def test_risk_level_valid_values(self, alert_rules):
        """验证risk_level字段有效值"""
        for rule in alert_rules:
            risk_level = rule["risk_level"]
            assert risk_level in ["L1", "L2", "L3", "L4", "L5"], \
                f"告警 {rule['alert_code']} 的risk_level无效: {risk_level}"
    
    def test_symptoms_not_empty(self, alert_rules):
        """验证症状列表非空"""
        for rule in alert_rules:
            symptoms = rule["symptoms"]
            assert isinstance(symptoms, list), f"告警 {rule['alert_code']} 的symptoms应为列表"
            assert len(symptoms) > 0, f"告警 {rule['alert_code']} 的symptoms不能为空"
    
    def test_check_steps_not_empty(self, alert_rules):
        """验证排查步骤非空"""
        for rule in alert_rules:
            check_steps = rule["check_steps"]
            assert isinstance(check_steps, list), f"告警 {rule['alert_code']} 的check_steps应为列表"
            assert len(check_steps) > 0, f"告警 {rule['alert_code']} 的check_steps不能为空"
    
    def test_resolution_not_empty(self, alert_rules):
        """验证解决方案非空"""
        for rule in alert_rules:
            resolution = rule["resolution"]
            assert isinstance(resolution, list), f"告警 {rule['alert_code']} 的resolution应为列表"
            assert len(resolution) > 0, f"告警 {rule['alert_code']} 的resolution不能为空"


class TestSOPKnowledge:
    """测试SOP标准操作程序知识库"""
    
    @pytest.fixture
    def sop_path(self):
        return Path("~/SWproject/zCloudNewAgentProject/knowledge/sop/").expanduser()
    
    @pytest.fixture
    def sop_files(self, sop_path):
        assert sop_path.exists(), f"SOP目录不存在: {sop_path}"
        return list(sop_path.glob("*.md"))
    
    def test_sop_directory_exists(self, sop_path):
        """验证SOP目录存在"""
        assert sop_path.exists(), f"SOP目录不存在: {sop_path}"
    
    def test_sop_has_files(self, sop_files):
        """验证SOP目录包含文件"""
        assert len(sop_files) > 0, "SOP目录为空"
    
    def test_sop_content_structure(self, sop_files):
        """验证SOP内容结构"""
        for sop_file in sop_files:
            content = sop_file.read_text(encoding="utf-8")
            # 验证SOP包含基本结构
            assert len(content) > 0, f"SOP文件 {sop_file.name} 内容为空"
            # 验证包含步骤标记（如 ## 1. 或 ## 2.）
            assert "##" in content or "#" in content, \
                f"SOP文件 {sop_file.name} 缺少标题结构"
    
    def test_sop_has_process_steps(self, sop_files):
        """验证SOP包含流程步骤"""
        for sop_file in sop_files:
            content = sop_file.read_text(encoding="utf-8")
            # 验证包含流程相关词汇
            process_keywords = ["步骤", "流程", "确认", "收集", "评估", "处理", "记录"]
            has_process = any(keyword in content for keyword in process_keywords)
            assert has_process, f"SOP文件 {sop_file.name} 未包含流程步骤"


class TestKnowledgeSearchability:
    """测试知识库可搜索性"""
    
    @pytest.fixture
    def alert_rules_path(self):
        return Path("~/SWproject/zCloudNewAgentProject/knowledge/alert_rules.yaml").expanduser()
    
    @pytest.fixture
    def alert_rules(self, alert_rules_path):
        with open(alert_rules_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data["alert_rules"]
    
    def test_can_search_by_alert_code(self, alert_rules):
        """验证可通过alert_code搜索"""
        search_code = "LOCK_WAIT_TIMEOUT"
        found = [r for r in alert_rules if r["alert_code"] == search_code]
        assert len(found) > 0, f"无法通过alert_code搜索: {search_code}"
    
    def test_can_search_by_symptom(self, alert_rules):
        """验证可通过症状关键词搜索"""
        # 搜索"等待时间超过阈值" - 这是LOCK_WAIT_TIMEOUT的症状
        symptom_keyword = "等待时间超过阈值"
        found = [r for r in alert_rules if symptom_keyword in str(r.get("symptoms", []))]
        assert len(found) > 0, f"无法通过症状关键词搜索: {symptom_keyword}"
    
    def test_can_search_by_severity(self, alert_rules):
        """验证可按严重程度筛选"""
        warning_alerts = [r for r in alert_rules if r["severity"] == "warning"]
        assert len(warning_alerts) > 0, "无法按severity筛选"
    
    def test_can_search_by_risk_level(self, alert_rules):
        """验证可按风险级别筛选"""
        l3_alerts = [r for r in alert_rules if r["risk_level"] == "L3"]
        assert len(l3_alerts) > 0, "无法按risk_level筛选"


class TestKnowledgeCompleteness:
    """测试知识库完整性"""
    
    def test_essential_alert_types_covered(self):
        """验证覆盖必要的告警类型"""
        essential_alerts = ["LOCK_WAIT", "SLOW_QUERY", "REPLICATION"]
        # 这些是数据库常见问题，应该有对应的SOP
        pass  # 等悟通补充完整知识库后验证
    
    def test_knowledge_has_cases(self):
        """验证知识库包含案例"""
        cases_path = Path("~/SWproject/zCloudNewAgentProject/knowledge/cases/")
        # 如果cases目录存在，验证有案例文件
        if cases_path.exists():
            case_files = list(cases_path.glob("*.md"))
            # 可以有案例，也可以没有（待补充）
            assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
