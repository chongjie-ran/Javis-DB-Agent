"""知识库数据库模块"""
import aiosqlite
import os
from pathlib import Path
from typing import Optional

KNOWLEDGE_DB_PATH = os.environ.get("KNOWLEDGE_DB_PATH", "data/knowledge.db")


async def get_knowledge_db() -> aiosqlite.Connection:
    """获取知识库数据库连接"""
    db_path = Path(KNOWLEDGE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    return conn


async def init_knowledge_db():
    """初始化知识库数据库"""
    conn = await get_knowledge_db()
    try:
        # 执行迁移
        migrations_dir = Path(__file__).parent / "migrations"
        for migration_file in sorted(migrations_dir.glob("V*.sql")):
            sql = migration_file.read_text()
            await conn.executescript(sql)
        await conn.commit()
    finally:
        await conn.close()


async def close_knowledge_db(conn: aiosqlite.Connection):
    """关闭数据库连接"""
    await conn.close()
