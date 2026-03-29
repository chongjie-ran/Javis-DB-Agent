"""Case Repository - 数据访问层"""
import json
from typing import Optional, Any, List
from datetime import datetime


class CaseRepository:
    """Case Repository - 提供故障案例的CRUD操作"""

    def __init__(self, db_conn: Any):
        """初始化Repository"""
        self.db = db_conn

    async def create(self, data: dict) -> dict:
        """创建案例"""
        now = datetime.now().isoformat()
        
        # 处理JSON字段
        symptoms = data.get("symptoms", [])
        if isinstance(symptoms, list):
            symptoms = json.dumps(symptoms, ensure_ascii=False)
        
        metadata = data.get("metadata", {})
        if isinstance(metadata, dict):
            metadata = json.dumps(metadata, ensure_ascii=False)
        
        sql = """
            INSERT INTO cases 
            (id, title, alert_rule_id, symptoms, root_cause, solution, outcome, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        await self.db.execute(sql, (
            data["id"],
            data["title"],
            data.get("alert_rule_id"),
            symptoms,
            data.get("root_cause"),
            data.get("solution"),
            data.get("outcome"),
            metadata,
            now,
            now
        ))
        await self.db.commit()
        
        return await self.get_by_id(data["id"])

    async def get_by_id(self, case_id: str) -> Optional[dict]:
        """通过ID获取案例"""
        sql = "SELECT * FROM cases WHERE id = ?"
        cursor = await self.db.execute(sql, (case_id,))
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return self._row_to_dict(row)

    async def list_all(self) -> List[dict]:
        """列出所有案例"""
        sql = "SELECT * FROM cases ORDER BY created_at DESC"
        cursor = await self.db.execute(sql)
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def list_by_alert_rule(self, alert_rule_id: str) -> List[dict]:
        """通过告警规则ID获取关联的案例"""
        sql = "SELECT * FROM cases WHERE alert_rule_id = ? ORDER BY created_at DESC"
        cursor = await self.db.execute(sql, (alert_rule_id,))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    async def update(self, case_id: str, data: dict) -> Optional[dict]:
        """更新案例"""
        existing = await self.get_by_id(case_id)
        if existing is None:
            return None
        
        update_fields = []
        values = []
        
        for field_name in ["title", "alert_rule_id", "root_cause", "solution", "outcome"]:
            if field_name in data:
                update_fields.append(f"{field_name} = ?")
                values.append(data[field_name])
        
        if "symptoms" in data:
            update_fields.append("symptoms = ?")
            symptoms = data["symptoms"]
            if isinstance(symptoms, list):
                symptoms = json.dumps(symptoms, ensure_ascii=False)
            values.append(symptoms)
        
        if "metadata" in data:
            update_fields.append("metadata = ?")
            metadata = data["metadata"]
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata, ensure_ascii=False)
            values.append(metadata)
        
        if not update_fields:
            return existing
        
        values.append(datetime.now().isoformat())
        values.append(case_id)
        sql = f"UPDATE cases SET {', '.join(update_fields)}, updated_at = ? WHERE id = ?"
        
        await self.db.execute(sql, values)
        await self.db.commit()
        
        return await self.get_by_id(case_id)

    async def delete(self, case_id: str) -> bool:
        """删除案例"""
        sql = "DELETE FROM cases WHERE id = ?"
        cursor = await self.db.execute(sql, (case_id,))
        await self.db.commit()
        
        return cursor.rowcount > 0

    async def search_by_keyword(self, keyword: str) -> List[dict]:
        """通过关键词搜索案例"""
        sql = """
            SELECT * FROM cases 
            WHERE title LIKE ? OR root_cause LIKE ? OR solution LIKE ?
            ORDER BY created_at DESC
        """
        pattern = f"%{keyword}%"
        cursor = await self.db.execute(sql, (pattern, pattern, pattern))
        rows = await cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: Any) -> dict:
        """将数据库行转换为字典"""
        result = dict(row)
        
        # 解析symptoms JSON
        if "symptoms" in result and result["symptoms"]:
            if isinstance(result["symptoms"], str):
                try:
                    result["symptoms"] = json.loads(result["symptoms"])
                except json.JSONDecodeError:
                    result["symptoms"] = []
        else:
            result["symptoms"] = []
        
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
