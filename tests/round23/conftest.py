"""
Round23 测试配置 - MySQL/PostgreSQL 环境检测
===============================================
"""
import pytest
import pymysql
import asyncio
import asyncpg


def is_mysql_available():
    """检测MySQL是否可用"""
    try:
        conn = pymysql.connect(
            host='127.0.0.1', 
            port=3306, 
            user='root', 
            password='root',
            connect_timeout=2
        )
        conn.close()
        return True
    except Exception:
        return False


def is_postgres_available():
    """检测PostgreSQL是否可用"""
    try:
        import asyncio
        async def _check():
            try:
                conn = await asyncpg.connect(
                    host='localhost',
                    port=5432,
                    user='chongjieran',
                    database='postgres',
                    timeout=2
                )
                await conn.close()
                return True
            except:
                return False
        return asyncio.get_event_loop().run_until_complete(_check())
    except Exception:
        return False


MYSQL_AVAILABLE = is_mysql_available()
POSTGRES_AVAILABLE = is_postgres_available()
