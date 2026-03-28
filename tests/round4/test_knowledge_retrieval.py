"""
第四轮测试：知识库检索准确性测试

本模块测试知识库系统的准确性：
1. SOP检索准确性
2. 案例库匹配准确性
3. 告警规则覆盖度
"""
import pytest
import os
import re
from typing import List, Dict, Any

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "src"))


# ============================================================================
# 测试配置
# ============================================================================

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "../..")
KNOWLEDGE_DIR = os.path.join(PROJECT_ROOT, "knowledge")
SOP_DIR = os.path.join(KNOWLEDGE_DIR, "sop")
CASES_DIR = os.path.join(KNOWLEDGE_DIR, "cases")
RULES_FILE = os.path.join(KNOWLEDGE_DIR, "alert_rules.yaml")


# ============================================================================
# 知识库检索模拟
# ============================================================================

class KnowledgeRetriever:
    """知识检索器（简化版，用于测试）"""
    
    def __init__(self):
        self.sop_cache = {}
        self.cases_cache = {}
        self.rules_cache = None
        self._load_knowledge()
    
    def _load_knowledge(self):
        """加载知识库"""
        # 加载SOP
        if os.path.exists(SOP_DIR):
            for f in os.listdir(SOP_DIR):
                if f.endswith(".md"):
                    path = os.path.join(SOP_DIR, f)
                    with open(path, "r", encoding="utf-8") as fp:
                        self.sop_cache[f.replace(".md", "")] = fp.read()
        
        # 加载案例
        if os.path.exists(CASES_DIR):
            for f in os.listdir(CASES_DIR):
                if f.endswith(".md"):
                    path = os.path.join(CASES_DIR, f)
                    with open(path, "r", encoding="utf-8") as fp:
                        self.cases_cache[f.replace(".md", "")] = fp.read()
        
        # 加载告警规则
        if os.path.exists(RULES_FILE):
            import yaml
            with open(RULES_FILE, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                self.rules_cache = {"rules": data.get("alert_rules", [])}
    
    def search_sop(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """搜索SOP"""
        results = []
        for name, content in self.sop_cache.items():
            score = 0
            matched_keywords = []
            for kw in keywords:
                if kw.lower() in content.lower():
                    score += 1
                    matched_keywords.append(kw)
                if kw.lower() in name.lower():
                    score += 2  # 标题匹配权重更高
                    matched_keywords.append(kw)
            
            if score > 0:
                results.append({
                    "name": name,
                    "score": score,
                    "matched": list(set(matched_keywords)),
                    "content_preview": content[:200],
                })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
    
    def search_cases(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """搜索案例"""
        results = []
        for name, content in self.cases_cache.items():
            score = 0
            matched_keywords = []
            for kw in keywords:
                if kw.lower() in content.lower():
                    score += 1
                    matched_keywords.append(kw)
            
            if score > 0:
                # 提取日期
                date_match = re.match(r"(\d{4}-\d{2}-\d{2})", name)
                date = date_match.group(1) if date_match else None
                
                # 提取故障类型
                fault_type = None
                for kw in keywords:
                    if kw in content:
                        fault_type = kw
                        break
                
                results.append({
                    "name": name,
                    "date": date,
                    "fault_type": fault_type,
                    "score": score,
                    "matched": list(set(matched_keywords)),
                })
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
    
    def match_alert_rules(self, alert_type: str) -> List[Dict[str, Any]]:
        """匹配告警规则"""
        if not self.rules_cache or "rules" not in self.rules_cache:
            return []
        
        matched = []
        for rule in self.rules_cache["rules"]:
            # alert_type是实际字段名
            if rule.get("alert_type") == alert_type:
                matched.append(rule)
        
        return matched


# ============================================================================
# 夹具
# ============================================================================

@pytest.fixture
def retriever():
    """知识检索器"""
    return KnowledgeRetriever()


# ============================================================================
# SOP检索准确性测试
# ============================================================================

class TestSOPRetrievalAccuracy:
    """SOP检索准确性测试"""
    
    def test_sop_directory_exists(self):
        """测试SOP目录存在"""
        assert os.path.exists(SOP_DIR), f"SOP目录不存在: {SOP_DIR}"
    
    def test_sop_files_not_empty(self, retriever):
        """测试SOP文件非空"""
        assert len(retriever.sop_cache) > 0, "SOP目录为空"
    
    def test_sop_search_by_keyword_lock_wait(self, retriever):
        """
        测试锁等待SOP检索
        
        验证：搜索"锁等待"能找到相关SOP
        """
        results = retriever.search_sop(["锁等待"])
        
        assert len(results) > 0, "未找到锁等待相关SOP"
        assert any("lock" in r["name"].lower() or "锁" in r["name"] for r in results), \
            "结果名称不匹配"
    
    def test_sop_search_by_keyword_replication(self, retriever):
        """
        测试主从延迟SOP检索
        
        验证：搜索"主从延迟"能找到相关SOP
        """
        results = retriever.search_sop(["主从延迟", "replication"])
        
        assert len(results) > 0, "未找到主从延迟相关SOP"
    
    def test_sop_search_by_keyword_slow_sql(self, retriever):
        """
        测试慢SQL SOP检索
        
        验证：搜索"慢SQL"能找到相关SOP
        """
        results = retriever.search_sop(["慢SQL", "slow"])
        
        assert len(results) > 0, "未找到慢SQL相关SOP"
    
    def test_sop_search_multi_keywords(self, retriever):
        """
        测试多关键词SOP检索
        
        验证：多个关键词能提高检索准确性
        """
        single_results = retriever.search_sop(["lock"])
        multi_results = retriever.search_sop(["lock", "wait", "排查"])
        
        # 多关键词结果应该更精确（排在前面）
        if len(single_results) > 0 and len(multi_results) > 0:
            assert multi_results[0]["score"] >= single_results[0]["score"], \
                "多关键词应提高匹配分数"
    
    def test_sop_content_completeness(self, retriever):
        """
        测试SOP内容完整性
        
        验证：SOP包含必要的结构化信息
        """
        for name, content in retriever.sop_cache.items():
            # 验证包含基本要素
            assert len(content) > 100, f"SOP内容过短: {name}"
            
            # 理想情况应包含的要素（软检查）
            has_structure = any(marker in content for marker in [
                "##", "###", "1.", "2.", "流程", "步骤", "排查"
            ])
            
            if not has_structure:
                print(f"警告: SOP {name} 可能缺少结构化标记")
    
    def test_sop_title_extraction(self, retriever):
        """
        测试SOP标题提取
        
        验证：能从SOP文件名和内容中提取标题
        """
        for name in retriever.sop_cache.keys():
            # 验证文件名格式
            assert len(name) > 0, "SOP名称为空"
            assert ".md" not in name, "名称不应包含扩展名"


# ============================================================================
# 案例库匹配准确性测试
# ============================================================================

class TestCaseLibraryAccuracy:
    """案例库匹配准确性测试"""
    
    def test_cases_directory_exists(self):
        """测试案例目录存在"""
        assert os.path.exists(CASES_DIR), f"案例目录不存在: {CASES_DIR}"
    
    def test_cases_not_empty(self, retriever):
        """测试案例非空"""
        assert len(retriever.cases_cache) > 0, "案例目录为空"
    
    def test_case_date_format(self, retriever):
        """
        测试案例日期格式
        
        验证：案例文件名包含正确格式的日期
        """
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}-")
        
        for name in retriever.cases_cache.keys():
            assert date_pattern.match(name), f"案例命名格式错误: {name}"
    
    def test_case_search_by_fault_type(self, retriever):
        """
        测试按故障类型搜索案例
        
        验证：能根据故障类型找到相关案例
        """
        results = retriever.search_cases(["锁等待"])
        
        assert len(results) > 0, "未找到锁等待相关案例"
    
    def test_case_relevance_ranking(self, retriever):
        """
        测试案例相关性排序
        
        验证：匹配度高的案例排在前面
        """
        # 搜索"锁等待故障"
        results = retriever.search_cases(["锁等待", "故障"])
        
        if len(results) >= 2:
            # 验证排序正确
            assert results[0]["score"] >= results[1]["score"], \
                "结果未按相关性排序"
    
    def test_case_metadata_extraction(self, retriever):
        """
        测试案例元数据提取
        
        验证：能正确提取日期和故障类型
        """
        for name, result_list in [
            ("2026-01-15-锁等待故障", retriever.search_cases(["锁等待"]))
        ]:
            if result_list:
                result = result_list[0]
                assert result.get("date") is not None, "未提取到日期"
                assert result.get("fault_type") is not None, "未提取到故障类型"


# ============================================================================
# 告警规则覆盖度测试
# ============================================================================

class TestAlertRulesCoverage:
    """告警规则覆盖度测试"""
    
    def test_rules_file_exists(self):
        """测试规则文件存在"""
        assert os.path.exists(RULES_FILE), f"告警规则文件不存在: {RULES_FILE}"
    
    def test_rules_yaml_valid(self, retriever):
        """测试规则YAML格式有效"""
        assert retriever.rules_cache is not None, "规则加载失败"
        assert "rules" in retriever.rules_cache, "缺少rules字段"
    
    def test_rules_not_empty(self, retriever):
        """测试规则列表非空"""
        assert len(retriever.rules_cache["rules"]) > 0, "规则列表为空"
    
    def test_required_alert_types_covered(self, retriever):
        """
        测试关键告警类型覆盖
        
        验证：常见告警类型都有对应规则
        """
        required_types = [
            "CPU_HIGH",
            "MEMORY_HIGH",
            "DISK_FULL",
            "LOCK_WAIT_TIMEOUT",
            "SLOW_QUERY_DETECTED",
        ]
        
        existing_types = [r.get("alert_type") for r in retriever.rules_cache["rules"]]
        
        for alert_type in required_types:
            assert alert_type in existing_types, f"缺少告警规则: {alert_type}"
    
    def test_rule_structure_completeness(self, retriever):
        """
        测试规则结构完整性
        
        验证：每个规则包含必要字段
        """
        required_fields = ["alert_type", "name", "severity"]
        
        for rule in retriever.rules_cache["rules"]:
            for field in required_fields:
                assert field in rule, f"规则缺少字段: {field}"
    
    def test_severity_values_valid(self, retriever):
        """
        测试告警级别值有效
        
        验证：severity字段使用标准值
        """
        valid_severities = ["critical", "high", "warning", "info"]
        
        for rule in retriever.rules_cache["rules"]:
            severity = rule.get("severity", "").lower()
            assert severity in valid_severities, \
                f"无效的severity值: {severity}"
    
    def test_alert_type_matching(self, retriever):
        """
        测试告警类型匹配功能
        
        验证：能根据告警类型找到对应规则
        """
        matched = retriever.match_alert_rules("CPU_HIGH")
        
        assert len(matched) > 0, "CPU_HIGH规则匹配失败"
        assert matched[0]["alert_type"] == "CPU_HIGH", "匹配到错误的告警类型"


# ============================================================================
# 知识库检索集成测试
# ============================================================================

class TestKnowledgeRetrievalIntegration:
    """知识库检索集成测试"""
    
    def test_full_retrieval_workflow(self, retriever):
        """
        测试完整检索工作流
        
        场景：收到LOCK_WAIT_TIMEOUT告警，检索相关知识和规则
        """
        alert_type = "LOCK_WAIT_TIMEOUT"
        
        # 1. 检索SOP
        sops = retriever.search_sop(["锁等待", "LOCK_WAIT"])
        assert len(sops) > 0, "未找到相关SOP"
        
        # 2. 检索案例
        cases = retriever.search_cases(["锁等待"])
        assert len(cases) > 0, "未找到相关案例"
        
        # 3. 匹配规则
        rules = retriever.match_alert_rules(alert_type)
        assert len(rules) > 0, "未匹配到告警规则"
        
        # 4. 验证结果关联性
        top_sop = sops[0]["name"].lower()
        assert "lock" in top_sop or "锁" in top_sop, "SOP结果不相关"
    
    def test_multi_alert_knowledge_retrieval(self, retriever):
        """
        测试多告警场景的知识检索
        
        场景：同时发生多个告警，检索综合知识
        """
        alert_types = ["CPU_HIGH", "SLOW_QUERY_DETECTED", "LOCK_WAIT_TIMEOUT"]
        
        all_knowledge = []
        for alert_type in alert_types:
            rules = retriever.match_alert_rules(alert_type)
            if rules:
                all_knowledge.extend(rules)
        
        assert len(all_knowledge) >= len(set(alert_types)), \
            "部分告警未匹配到规则"
    
    def test_knowledge_confidence_scoring(self, retriever):
        """
        测试知识匹配置信度
        
        验证：高相关知识得分更高
        """
        # 直接搜索 - 精确关键词（标题匹配）
        direct_results = retriever.search_sop(["慢SQL"])
        
        # 间接搜索 - 部分匹配的关键词
        indirect_results = retriever.search_sop(["SQL", "查询"])
        
        if len(direct_results) > 0 and len(indirect_results) > 0:
            # 直接搜索（标题包含）的分数应该不低于间接搜索
            # 因为标题匹配有+2的权重
            assert direct_results[0]["score"] >= indirect_results[0]["score"], \
                f"直接匹配分数应更高: direct={direct_results[0]['score']}, indirect={indirect_results[0]['score']}"


# ============================================================================
# 知识库质量评估
# ============================================================================

class TestKnowledgeQualityMetrics:
    """知识库质量评估测试"""
    
    def test_sop_coverage_score(self, retriever):
        """
        测试SOP覆盖率
        
        评估标准：
        - 10个以上SOP: 优秀
        - 5-10个SOP: 良好
        - 3-5个SOP: 一般
        - 3个以下: 不足
        """
        sop_count = len(retriever.sop_cache)
        
        print(f"\n=== SOP覆盖率 ===")
        print(f"SOP数量: {sop_count}")
        
        if sop_count >= 10:
            print("评级: 优秀 ✓")
        elif sop_count >= 5:
            print("评级: 良好 ✓")
        elif sop_count >= 3:
            print("评级: 一般 △")
        else:
            print("评级: 不足 ✗")
        
        assert sop_count >= 3, f"SOP数量不足: {sop_count}"
    
    def test_case_coverage_score(self, retriever):
        """
        测试案例覆盖率
        
        评估标准：
        - 10个以上案例: 优秀
        - 5-10个案例: 良好
        - 3-5个案例: 一般
        - 3个以下: 不足
        """
        case_count = len(retriever.cases_cache)
        
        print(f"\n=== 案例覆盖率 ===")
        print(f"案例数量: {case_count}")
        
        if case_count >= 10:
            print("评级: 优秀 ✓")
        elif case_count >= 5:
            print("评级: 良好 ✓")
        elif case_count >= 3:
            print("评级: 一般 △")
        else:
            print("评级: 不足 ✗")
        
        assert case_count >= 3, f"案例数量不足: {case_count}"
    
    def test_rules_coverage_score(self, retriever):
        """
        测试告警规则覆盖率
        
        评估常见告警类型的规则覆盖
        """
        # 使用yaml中实际存在的alert_code
        common_alerts = [
            "CPU_HIGH",
            "MEMORY_HIGH",
            "DISK_FULL",
            "CONNECTION_HIGH",
            "LOCK_WAIT_TIMEOUT",
            "SLOW_QUERY_DETECTED",
            "REPLICATION_LAG",
            "INSTANCE_DOWN",
            "INSTANCE_SLOW",
            "DEADLOCK_DETECTED",
            "BACKUP_FAILED",
            "FAILED_LOGIN",
        ]
        
        covered = 0
        for alert_type in common_alerts:
            if retriever.match_alert_rules(alert_type):
                covered += 1
        
        coverage = covered / len(common_alerts) * 100
        
        print(f"\n=== 告警规则覆盖率 ===")
        print(f"覆盖/总数: {covered}/{len(common_alerts)}")
        print(f"覆盖率: {coverage:.0f}%")
        
        if coverage >= 80:
            print("评级: 优秀 ✓")
        elif coverage >= 60:
            print("评级: 良好 ✓")
        elif coverage >= 40:
            print("评级: 一般 △")
        else:
            print("评级: 不足 ✗")
        
        assert coverage >= 40, f"告警规则覆盖率不足: {coverage:.0f}%"
    
    def test_knowledge_completeness_report(self, retriever):
        """
        生成知识库完整性报告
        """
        print(f"\n{'='*50}")
        print("知识库完整性报告")
        print(f"{'='*50}")
        print(f"SOP数量: {len(retriever.sop_cache)}")
        print(f"案例数量: {len(retriever.cases_cache)}")
        print(f"告警规则: {len(retriever.rules_cache['rules'])}")
        
        # 计算总覆盖率
        common_alerts = 12
        covered = sum(1 for at in [
            "CPU_HIGH", "MEMORY_HIGH", "DISK_FULL",
            "CONNECTION_HIGH", "LOCK_WAIT_TIMEOUT",
            "SLOW_QUERY_DETECTED", "REPLICATION_LAG",
            "INSTANCE_DOWN", "INSTANCE_SLOW",
            "DEADLOCK_DETECTED", "BACKUP_FAILED", "FAILED_LOGIN"
        ] if retriever.match_alert_rules(at))
        
        print(f"告警覆盖: {covered}/{common_alerts} ({covered/common_alerts*100:.0f}%)")
        print(f"{'='*50}")


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
