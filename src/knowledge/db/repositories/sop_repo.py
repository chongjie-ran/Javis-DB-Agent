"""SOP Repository - 数据访问层"""
import json
from typing import Optional, Any, List
from datetime import datetime


class SOPRepository:
    """SOP Repository - 提供标准操作程序的CRUD操作"""

    def __init__(self, db_conn: Any):
        """初始化Repository"""
        self.db = db_conn

    async def create(self, data: dict) -> dict:
        """创建SOP"""
        now = datetime.now().isoformat()
        steps = data.get("steps", [])
        if isinstance(steps, list):
            steps = json.dumps(steps, ensure_ascii=False)
        
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata, ensure_ascii=False)
        
        sql = """
            INSERT INTO sops 
            (id, title, alert_rule_id, steps, enabled, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        await self.db.execute(sql, (
            data["id"],
            data["title"],
            data.get("alert_rule_id"),
            steps,
            data.get("enabled", 1),
            metadata,
            now,
            now
        ))
        await self.db.commit()
        
        return await self.get_by_id(data["id"])

    async def get_by_id(self, sop_id: str) -> Optional[dict]:
        """通过ID获取SOP"""
        sql = "SELECT * FROM sops WHERE id = ?"
        cursor = await self.db.execute(sql, (sop_id,))
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)

    async def list_all(self, enabled_only: bool = False) -> List[dict]:
        """列出所有SOP"""
        sql = "SELECT * FROM sops"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        
        cursor = await self.db.execute(sql)
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def list_by_alert_rule(self, alert_rule_id: str) -> List[dict]:
        """通过告警规则ID获取关联的SOP"""
        sql = "SELECT * FROM sops WHERE alert_rule_id = ? ORDER BY created_at DESC"
        cursor = await self.db.execute(sql, (alert_rule_id,))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def update(self, sop_id: str, data: dict) -> Optional[dict]:
        """更新SOP"""
        existing = await self.get_by_id(sop_id)
        if existing is None:
            return None
        
        update_fields = []
        values = []
        
        for field_name in ["title", "alert_rule_id", "enabled"]:
            if field_name in data:
                update_fields.append(f"{field_name} = ?")
                values.append(data[field_name])
        
        if "steps" in data:
            update_fields.append("steps = ?")
            steps = data["steps"]
            if isinstance(steps, list):
                steps = json.dumps(steps, ensure_ascii=False)
            values.append(steps)
        
        if "metadata" in data:
            update_fields.append("metadata = ?")
            metadata = data["metadata"]
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False)
            values.append(metadata)
        
        if not update_fields:
            return existing
        
        values.append(datetime.now().isoformat())
        values.append(sop_id)
        sql = f"UPDATE sops SET {', '.join(update_fields)}, updated_at = ? WHERE id = ?"
        
        await self.db.execute(sql, values)
        await self.db.commit()
        
        return await self.get_by_id(sop_id)

    async def delete(self, sop_id: str) -> bool:
        """删除SOP"""
        sql = "DELETE FROM sops WHERE id = ?"
        cursor = await self.db.execute(sql, (sop_id,))
        await self.db.commit()
        
        return cursor.rowcount > 0

    async def search_by_keyword(self, keyword: str) -> List[dict]:
        """通过关键词搜索SOP"""
        sql = """
            SELECT * FROM sops 
            WHERE title LIKE ? OR steps LIKE ?
            ORDER BY created_at DESC
        """
        pattern = f"%{keyword}%"
        cursor = await self.db.execute(sql, (pattern, pattern))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: Any) -> dict:
        """将数据库行转换为字典"""
        result = dict(row)
        
        # 解析steps JSON
        if "steps" in result and result["steps"]:
            if isinstance(result["steps"], str):
                try:
                    result["steps"] = json.loads(result["steps"])
                except json.JSONDecodeError:
                    result["steps"] = []
        else:
            result["steps"] = []
        
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
