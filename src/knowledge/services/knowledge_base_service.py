"""知识库服务层 - 统一的CRUD接口"""
import json
from typing import Optional, Any, List, Dict
from dataclasses import dataclass
from enum import Enum


class ContentType(str, Enum):
    """知识库内容类型枚举"""
    ALERT_RULE = "alert_rule"
    SOP = "sop"
    CASE = "case"


@dataclass
class SearchResult:
    """搜索结果"""
    content_type: str
    content_id: str
    title: str
    content: str
    score: float
    metadata: dict


class KnowledgeBaseService:
    """
    知识库服务 - 提供统一的CRUD接口
    
    支持:
    - 告警规则 (alert_rules)
    - SOP标准操作程序 (sops)
    - 故障案例 (cases)
    """
    
    def __init__(self, db_conn: Any):
        """
        初始化服务
        
        Args:
            db_conn: 异步数据库连接
        """
        self.db = db_conn
        self._alert_rule_repo = None
        self._sop_repo = None
        self._case_repo = None
    
    @property
    def alert_rules(self):
        """告警规则仓库"""
        if self._alert_rule_repo is None:
            from src.knowledge.db.repositories.alert_rule_repo import AlertRuleRepository
            self._alert_rule_repo = AlertRuleRepository(self.db)
        return self._alert_rule_repo
    
    @property
    def sops(self):
        """SOP仓库"""
        if self._sop_repo is None:
            from src.knowledge.db.repositories.sop_repo import SOPRepository
            self._sop_repo = SOPRepository(self.db)
        return self._sop_repo
    
    @property
    def cases(self):
        """案例仓库"""
        if self._case_repo is None:
            from src.knowledge.db.repositories.case_repo import CaseRepository
            self._case_repo = CaseRepository(self.db)
        return self._case_repo
    
    # ==================== 告警规则 CRUD ====================
    
    async def create_alert_rule(self, data: dict) -> dict:
        """创建告警规则"""
        return await self.alert_rules.create(data)
    
    async def get_alert_rule(self, rule_id: str) -> Optional[dict]:
        """获取告警规则"""
        return await self.alert_rules.get_by_id(rule_id)
    
    async def list_alert_rules(self, enabled_only: bool = False) -> List[dict]:
        """列出告警规则"""
        return await self.alert_rules.list_all(enabled_only=enabled_only)
    
    async def list_alert_rules_by_severity(self, severity: str) -> List[dict]:
        """按严重程度筛选告警规则"""
        return await self.alert_rules.list_by_severity(severity)
    
    async def update_alert_rule(self, rule_id: str, data: dict) -> Optional[dict]:
        """更新告警规则"""
        return await self.alert_rules.update(rule_id, data)
    
    async def delete_alert_rule(self, rule_id: str) -> bool:
        """删除告警规则"""
        return await self.alert_rules.delete(rule_id)
    
    async def search_alert_rules(self, keyword: str) -> List[dict]:
        """搜索告警规则"""
        return await self.alert_rules.search_by_keyword(keyword)
    
    # ==================== SOP CRUD ====================
    
    async def create_sop(self, data: dict) -> dict:
        """创建SOP"""
        return await self.sops.create(data)
    
    async def get_sop(self, sop_id: str) -> Optional[dict]:
        """获取SOP"""
        return await self.sops.get_by_id(sop_id)
    
    async def list_sops(self, enabled_only: bool = False) -> List[dict]:
        """列出SOP"""
        return await self.sops.list_all(enabled_only=enabled_only)
    
    async def list_sops_by_alert_rule(self, alert_rule_id: str) -> List[dict]:
        """获取告警规则关联的SOP"""
        return await self.sops.list_by_alert_rule(alert_rule_id)
    
    async def update_sop(self, sop_id: str, data: dict) -> Optional[dict]:
        """更新SOP"""
        return await self.sops.update(sop_id, data)
    
    async def delete_sop(self, sop_id: str) -> bool:
        """删除SOP"""
        return await self.sops.delete(sop_id)
    
    async def search_sops(self, keyword: str) -> List[dict]:
        """搜索SOP"""
        return await self.sops.search_by_keyword(keyword)
    
    # ==================== 案例 CRUD ====================
    
    async def create_case(self, data: dict) -> dict:
        """创建案例"""
        return await self.cases.create(data)
    
    async def get_case(self, case_id: str) -> Optional[dict]:
        """获取案例"""
        return await self.cases.get_by_id(case_id)
    
    async def list_cases(self) -> List[dict]:
        """列出所有案例"""
        return await self.cases.list_all()
    
    async def list_cases_by_alert_rule(self, alert_rule_id: str) -> List[dict]:
        """获取告警规则关联的案例"""
        return await self.cases.list_by_alert_rule(alert_rule_id)
    
    async def update_case(self, case_id: str, data: dict) -> Optional[dict]:
        """更新案例"""
        return await self.cases.update(case_id, data)
    
    async def delete_case(self, case_id: str) -> bool:
        """删除案例"""
        return await self.cases.delete(case_id)
    
    async def search_cases(self, keyword: str) -> List[dict]:
        """搜索案例"""
        return await self.cases.search_by_keyword(keyword)
    
    # ==================== 统一搜索接口 ====================
    
    async def unified_search(self, keyword: str, content_types: Optional[List[str]] = None) -> List[SearchResult]:
        """
        统一搜索接口
        
        在所有知识库内容中搜索关键词
        
        Args:
            keyword: 搜索关键词
            content_types: 限定内容类型，如 ["alert_rule", "sop", "case"]
            
        Returns:
            搜索结果列表
        """
        results = []
        types_to_search = content_types or [ct.value for ct in ContentType]
        
        # 搜索告警规则
        if ContentType.ALERT_RULE.value in types_to_search:
            alert_rules = await self.alert_rules.search_by_keyword(keyword)
            for rule in alert_rules:
                results.append(SearchResult(
                    content_type=ContentType.ALERT_RULE.value,
                    content_id=rule["id"],
                    title=rule["name"],
                    content=rule.get("condition", "") + " " + rule.get("recommendation", ""),
                    score=1.0,  # 简单匹配
                    metadata=rule.get("metadata", {})
                ))
        
        # 搜索SOP
        if ContentType.SOP.value in types_to_search:
            sops = await self.sops.search_by_keyword(keyword)
            for sop in sops:
                steps_str = json.dumps(sop.get("steps", []), ensure_ascii=False)
                results.append(SearchResult(
                    content_type=ContentType.SOP.value,
                    content_id=sop["id"],
                    title=sop["title"],
                    content=steps_str,
                    score=1.0,
                    metadata=sop.get("metadata", {})
                ))
        
        # 搜索案例
        if ContentType.CASE.value in types_to_search:
            cases = await self.cases.search_by_keyword(keyword)
            for case in cases:
                content = (case.get("root_cause", "") + " " + case.get("solution", ""))
                results.append(SearchResult(
                    content_type=ContentType.CASE.value,
                    content_id=case["id"],
                    title=case["title"],
                    content=content,
                    score=1.0,
                    metadata=case.get("metadata", {})
                ))
        
        return results
    
    # ==================== 统计接口 ====================
    
    async def get_stats(self) -> dict:
        """获取知识库统计信息"""
        alert_count = await self.alert_rules.count()
        sops_count = len(await self.sops.list_all())
        cases_count = len(await self.cases.list_all())
        
        # 统计严重程度分布
        severity_stats = {}
        for severity in ["critical", "warning", "info"]:
            rules = await self.alert_rules.list_by_severity(severity)
            severity_stats[severity] = len(rules)
        
        return {
            "total_alert_rules": alert_count,
            "total_sops": sops_count,
            "total_cases": cases_count,
            "alert_rules_by_severity": severity_stats
        }
