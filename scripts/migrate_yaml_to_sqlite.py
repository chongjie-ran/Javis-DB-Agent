#!/usr/bin/env python3
"""
YAML知识库迁移脚本

将现有的YAML知识库迁移到SQLite数据库

使用方法:
    python scripts/migrate_yaml_to_sqlite.py [--force]

参数:
    --force: 强制重新创建表（会清空数据）
"""
import asyncio
import argparse
import json
import os
import sys
from pathlib import Path
import yaml
import aiosqlite

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge.db.database import get_knowledge_db, close_knowledge_db


class KnowledgeMigration:
    """知识库迁移器"""
    
    PROJECT_ROOT = Path(__file__).parent.parent
    KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
    
    def __init__(self, db_path: str = "data/knowledge.db"):
        self.db_path = db_path
        self.conn = None
        
    async def init_db(self, force: bool = False):
        """初始化数据库"""
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        
        self.conn = await get_knowledge_db()
        self.conn.row_factory = aiosqlite.Row
        
        # 执行迁移脚本
        migrations_dir = Path(__file__).parent.parent / "src" / "knowledge" / "db" / "migrations"
        
        for migration_file in sorted(migrations_dir.glob("V*.sql")):
            print(f"执行迁移: {migration_file.name}")
            sql = migration_file.read_text()
            await self.conn.executescript(sql)
        
        await self.conn.commit()
        print("数据库初始化完成")
    
    async def migrate_alert_rules(self) -> int:
        """迁移告警规则"""
        yaml_path = self.KNOWLEDGE_DIR / "alert_rules.yaml"
        if not yaml_path.exists():
            print(f"告警规则文件不存在: {yaml_path}")
            return 0
        
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        
        alert_rules = data.get("alert_rules", [])
        if not alert_rules:
            print("告警规则为空")
            return 0
        
        count = 0
        for rule in alert_rules:
            alert_code = rule.get("alert_code", "")
            if not alert_code:
                continue
            
            # 生成唯一ID
            rule_id = f"alert-{alert_code}"
            
            # 构建SOP数据
            check_steps = rule.get("check_steps", [])
            resolution = rule.get("resolution", [])
            def format_list(items):
                if isinstance(items, list):
                    return "\n".join(str(item) for item in items)
                return str(items) if items else ""
            
            combined_condition = "\n".join([
                f"症状: {', '.join(str(s) for s in rule.get('symptoms', []))}",
                f"可能原因: {', '.join(str(c) for c in rule.get('possible_causes', []))}",
                f"排查步骤: {format_list(check_steps)}",
                f"解决方案: {format_list(resolution)}"
            ])
            
            # 转换severity
            severity_map = {"critical": "critical", "warning": "warning", "info": "info"}
            severity = severity_map.get(rule.get("severity", "info"), "info")
            
            metadata = {
                "alert_code": alert_code,
                "risk_level": rule.get("risk_level", "L3"),
                "description": rule.get("description", ""),
                "symptoms": rule.get("symptoms", []),
                "possible_causes": rule.get("possible_causes", [])
            }
            
            try:
                await self.conn.execute("""
                    INSERT OR REPLACE INTO alert_rules 
                    (id, name, entity_type, resource_type, observation_point, 
                     condition, severity, recommendation, enabled, metadata,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (
                    rule_id,
                    rule.get("name", ""),
                    "database",
                    "session",
                    alert_code.lower(),
                    combined_condition,
                    severity,
                    "\n".join(resolution) if isinstance(resolution, list) else resolution,
                    1,
                    json.dumps(metadata, ensure_ascii=False)
                ))
                count += 1
            except Exception as e:
                print(f"迁移告警规则失败 {rule_id}: {e}")
        
        await self.conn.commit()
        print(f"迁移了 {count} 条告警规则")
        return count
    
    async def migrate_sops(self) -> int:
        """迁移SOP文件"""
        sop_dir = self.KNOWLEDGE_DIR / "sop"
        if not sop_dir.exists():
            print(f"SOP目录不存在: {sop_dir}")
            return 0
        
        count = 0
        for sop_file in sorted(sop_dir.glob("*.md")):
            try:
                content = sop_file.read_text(encoding="utf-8")
                title = sop_file.stem  # 文件名作为标题
                
                # 解析步骤
                steps = self._parse_sop_steps(content)
                
                # 生成唯一ID
                sop_id = f"sop-{title}"
                
                # 尝试找到关联的告警规则
                alert_rule_id = await self._find_linked_alert_rule(title, content)
                
                metadata = {
                    "source_file": str(sop_file.name),
                    "filename": sop_file.name
                }
                
                await self.conn.execute("""
                    INSERT OR REPLACE INTO sops 
                    (id, title, alert_rule_id, steps, enabled, metadata,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (
                    sop_id,
                    title,
                    alert_rule_id,
                    json.dumps(steps, ensure_ascii=False),
                    1,
                    json.dumps(metadata, ensure_ascii=False)
                ))
                count += 1
            except Exception as e:
                print(f"迁移SOP失败 {sop_file.name}: {e}")
        
        await self.conn.commit()
        print(f"迁移了 {count} 个SOP")
        return count
    
    async def migrate_cases(self) -> int:
        """迁移案例文件"""
        cases_dir = self.KNOWLEDGE_DIR / "cases"
        if not cases_dir.exists():
            print(f"案例目录不存在: {cases_dir}")
            return 0
        
        count = 0
        for case_file in sorted(cases_dir.glob("*.md")):
            try:
                content = case_file.read_text(encoding="utf-8")
                title = case_file.stem
                
                # 解析案例内容
                case_data = self._parse_case_content(title, content)
                
                # 生成唯一ID
                case_id = f"case-{title}"
                
                # 尝试找到关联的告警规则
                alert_rule_id = await self._find_linked_alert_rule(title, content)
                
                metadata = {
                    "source_file": str(case_file.name),
                    "filename": case_file.name,
                    "version": case_data.get("version"),
                    "status": case_data.get("status")
                }
                
                await self.conn.execute("""
                    INSERT OR REPLACE INTO cases 
                    (id, title, alert_rule_id, symptoms, root_cause, solution, outcome, metadata,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
                """, (
                    case_id,
                    title,
                    alert_rule_id,
                    json.dumps(case_data.get("symptoms", []), ensure_ascii=False),
                    case_data.get("root_cause", ""),
                    case_data.get("solution", ""),
                    case_data.get("outcome", ""),
                    json.dumps(metadata, ensure_ascii=False)
                ))
                count += 1
            except Exception as e:
                print(f"迁移案例失败 {case_file.name}: {e}")
        
        await self.conn.commit()
        print(f"迁移了 {count} 个案例")
        return count
    
    def _parse_sop_steps(self, content: str) -> list:
        """解析SOP步骤"""
        steps = []
        lines = content.split("\n")
        
        for line in lines:
            line = line.strip()
            # 匹配 ## 1. 或 ## 2. 等标题格式
            if line.startswith("##"):
                # 提取步骤标题
                step_text = line.lstrip("#").strip()
                step_text = step_text.lstrip("0123456789. ").strip()
                if step_text:
                    steps.append({"title": step_text, "done": False})
            elif line.startswith("-") or line.startswith("*"):
                # 列表项
                step_text = line.lstrip("-*").strip()
                if step_text:
                    steps.append({"action": step_text, "done": False})
        
        return steps if steps else [{"content": content[:500], "done": False}]
    
    def _parse_case_content(self, title: str, content: str) -> dict:
        """解析案例内容"""
        result = {
            "symptoms": [],
            "root_cause": "",
            "solution": "",
            "outcome": ""
        }
        
        # 提取根因
        if "## 3. 根因" in content or "## 根因" in content:
            section = self._extract_section(content, ["## 3. 根因", "## 根因"])
            result["root_cause"] = section
        
        # 提取解决方案
        if "## 4. 经验" in content or "## 解决方案" in content:
            section = self._extract_section(content, ["## 4. 经验教训", "## 解决方案"])
            result["solution"] = section
        
        # 提取结果
        if "| 根因 |" in content:
            # 尝试从表格中提取
            for line in content.split("\n"):
                if "Kill" in line or "处置" in line:
                    result["outcome"] += line.strip() + "\n"
        
        return result
    
    def _extract_section(self, content: str, markers: list) -> str:
        """提取内容章节"""
        lines = content.split("\n")
        section_lines = []
        capturing = False
        
        for line in lines:
            # 检查是否是章节标题
            for marker in markers:
                if marker in line:
                    capturing = True
                    continue
            
            if capturing:
                # 检查是否到达下一个## 章节
                if line.startswith("## ") and not any(m in line for m in markers):
                    break
                section_lines.append(line)
        
        return "\n".join(section_lines).strip()
    
    async def _find_linked_alert_rule(self, title: str, content: str) -> str:
        """查找关联的告警规则"""
        # 简单关键词匹配
        keywords_map = {
            "lock_wait": "alert-LOCK_WAIT_TIMEOUT",
            "锁等待": "alert-LOCK_WAIT_TIMEOUT",
            "死锁": "alert-DEADLOCK_DETECTED",
            "slow_query": "alert-SLOW_QUERY_DETECTED",
            "慢SQL": "alert-SLOW_QUERY_DETECTED",
            "replication": "alert-REPLICATION_LAG",
            "主从": "alert-REPLICATION_LAG",
            "connection": "alert-CONNECTION_HIGH",
            "连接": "alert-CONNECTION_HIGH",
        }
        
        title_lower = title.lower()
        content_lower = content.lower()
        
        for keyword, alert_id in keywords_map.items():
            if keyword in title_lower or keyword in content_lower:
                return alert_id
        
        return None
    
    async def get_migration_stats(self) -> dict:
        """获取迁移统计"""
        stats = {
            "alert_rules": 0,
            "sops": 0,
            "cases": 0
        }
        
        cursor = await self.conn.execute("SELECT COUNT(*) FROM alert_rules")
        row = await cursor.fetchone()
        stats["alert_rules"] = row[0] if row else 0
        
        cursor = await self.conn.execute("SELECT COUNT(*) FROM sops")
        row = await cursor.fetchone()
        stats["sops"] = row[0] if row else 0
        
        cursor = await self.conn.execute("SELECT COUNT(*) FROM cases")
        row = await cursor.fetchone()
        stats["cases"] = row[0] if row else 0
        
        return stats
    
    async def close(self):
        """关闭连接"""
        if self.conn:
            await close_knowledge_db(self.conn)


async def main():
    parser = argparse.ArgumentParser(description="YAML知识库迁移到SQLite")
    parser.add_argument("--force", action="store_true", help="强制重新创建表")
    parser.add_argument("--db-path", default="data/knowledge.db", help="数据库路径")
    args = parser.parse_args()
    
    migrator = KnowledgeMigration(args.db_path)
    
    print("=" * 50)
    print("YAML知识库迁移工具")
    print("=" * 50)
    
    # 初始化数据库
    await migrator.init_db(force=args.force)
    
    # 执行迁移
    print("\n开始迁移...")
    print("-" * 50)
    
    alert_count = await migrator.migrate_alert_rules()
    sop_count = await migrator.migrate_sops()
    case_count = await migrator.migrate_cases()
    
    # 显示统计
    print("\n" + "-" * 50)
    print("迁移完成!")
    print("-" * 50)
    
    stats = await migrator.get_migration_stats()
    print(f"告警规则: {stats['alert_rules']} 条")
    print(f"SOP: {stats['sops']} 个")
    print(f"案例: {stats['cases']} 个")
    print(f"总计: {sum(stats.values())} 条")
    
    await migrator.close()


if __name__ == "__main__":
    asyncio.run(main())
