"""告警规则Repository - 数据访问层"""
import json
from dataclasses import dataclass, field
from typing import Optional, Any, List
from datetime import datetime


@dataclass
class AlertRule:
    """告警规则数据模型"""
    id: str
    name: str
    condition: str
    severity: str
    entity_type: Optional[str] = None
    resource_type: Optional[str] = None
    observation_point: Optional[str] = None
    recommendation: Optional[str] = None
    enabled: int = 1
    metadata: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if isinstance(self.metadata, str):
            self.metadata = json.loads(self.metadata)


class AlertRuleRepository:
    """告警规则Repository - 提供告警规则的CRUD操作"""

    VALID_SEVERITIES = {"critical", "warning", "info"}

    def __init__(self, db_conn: Any):
        """
        初始化Repository
        
        Args:
            db_conn: 异步数据库连接 (aiosqlite.Connection)
        """
        self.db = db_conn

    async def create(self, data: dict) -> dict:
        """
        创建告警规则
        
        Args:
            data: 告警规则数据
            
        Returns:
            创建的告警规则
        """
        now = datetime.now().isoformat()
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata, ensure_ascii=False)
        
        sql = """
            INSERT INTO alert_rules 
            (id, name, entity_type, resource_type, observation_point, 
             condition, severity, recommendation, enabled, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        await self.db.execute(sql, (
            data["id"],
            data["name"],
            data.get("entity_type"),
            data.get("resource_type"),
            data.get("observation_point"),
            data["condition"],
            data["severity"],
            data.get("recommendation"),
            data.get("enabled", 1),
            metadata,
            now,
            now
        ))
        await self.db.commit()
        
        return await self.get_by_id(data["id"])

    async def get_by_id(self, rule_id: str) -> Optional[dict]:
        """
        通过ID获取告警规则
        
        Args:
            rule_id: 告警规则ID
            
        Returns:
            告警规则或None
        """
        sql = "SELECT * FROM alert_rules WHERE id = ?"
        cursor = await self.db.execute(sql, (rule_id,))
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)

    async def list_all(self, enabled_only: bool = False) -> List[dict]:
        """
        列出所有告警规则
        
        Args:
            enabled_only: 仅返回启用的规则
            
        Returns:
            告警规则列表
        """
        sql = "SELECT * FROM alert_rules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        
        cursor = await self.db.execute(sql)
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def list_by_severity(self, severity: str) -> List[dict]:
        """
        按严重程度筛选告警规则
        
        Args:
            severity: 严重程度 (critical/warning/info)
            
        Returns:
            告警规则列表
        """
        if severity not in self.VALID_SEVERITIES:
            raise ValueError(f"Invalid severity: {severity}")
        
        sql = "SELECT * FROM alert_rules WHERE severity = ? ORDER BY created_at DESC"
        cursor = await self.db.execute(sql, (severity,))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def update(self, rule_id: str, data: dict) -> Optional[dict]:
        """
        更新告警规则
        
        Args:
            rule_id: 告警规则ID
            data: 更新数据
            
        Returns:
            更新后的告警规则或None
        """
        # 获取现有数据
        existing = await self.get_by_id(rule_id)
        if existing is None:
            return None
        
        # 构建更新语句
        update_fields = []
        values = []
        
        for field_name in ["name", "entity_type", "resource_type", "observation_point",
                          "condition", "severity", "recommendation", "enabled"]:
            if field_name in data:
                update_fields.append(f"{field_name} = ?")
                values.append(data[field_name])
        
        if "metadata" in data:
            update_fields.append("metadata = ?")
            metadata = data["metadata"]
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False)
            values.append(metadata)
        
        if not update_fields:
            return existing
        
        # 添加updated_at和id
        values.append(datetime.now().isoformat())
        values.append(rule_id)
        sql = f"UPDATE alert_rules SET {', '.join(update_fields)}, updated_at = ? WHERE id = ?"
        
        await self.db.execute(sql, values)
        await self.db.commit()
        
        return await self.get_by_id(rule_id)

    async def delete(self, rule_id: str) -> bool:
        """
        删除告警规则
        
        Args:
            rule_id: 告警规则ID
            
        Returns:
            是否删除成功
        """
        sql = "DELETE FROM alert_rules WHERE id = ?"
        cursor = await self.db.execute(sql, (rule_id,))
        await self.db.commit()
        
        return cursor.rowcount > 0

    async def search_by_keyword(self, keyword: str) -> List[dict]:
        """
        通过关键词搜索告警规则
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            匹配的告警规则列表
        """
        sql = """
            SELECT * FROM alert_rules 
            WHERE name LIKE ? OR condition LIKE ? OR recommendation LIKE ?
            ORDER BY created_at DESC
        """
        pattern = f"%{keyword}%"
        cursor = await self.db.execute(sql, (pattern, pattern, pattern))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def count(self, enabled_only: bool = False) -> int:
        """
        统计告警规则数量
        
        Args:
            enabled_only: 仅统计启用的规则
            
        Returns:
            数量
        """
        sql = "SELECT COUNT(*) as count FROM alert_rules"
        if enabled_only:
            sql += " WHERE enabled = 1"
        
        cursor = await self.db.execute(sql)
        row = await cursor.fetchone()
        return row["count"] if row else 0

    def _row_to_dict(self, row: Any) -> dict:
        """将数据库行转换为字典"""
        result = dict(row)
        # 解析metadata JSON
        if "metadata" in result and result["metadata"]:
            if isinstance(result["metadata"], str):
                try:
                    result["metadata"] = json.loads(result["metadata"])
                except json.JSONDecodeError:
                    result["metadata"] = {}
        else:
            result["metadata"] = {}
        return result
