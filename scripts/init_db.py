#!/usr/bin/env python3
"""初始化数据库"""
import os
import sqlite3
from datetime import datetime

DB_PATH = "data/zcloud_agent.db"
AUDIT_DB_PATH = "data/audit.db"


def init_main_db():
    """初始化主数据库"""
    os.makedirs("data", exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 用户表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            user_name TEXT NOT NULL,
            role TEXT DEFAULT 'ANALYST',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 会话表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            metadata TEXT
        )
    """)
    
    # Agent执行记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            goal TEXT,
            result TEXT,
            execution_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 工具调用记录表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            tool_name TEXT NOT NULL,
            params TEXT,
            result TEXT,
            risk_level INTEGER,
            execution_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"✓ 主数据库初始化完成: {DB_PATH}")


def init_audit_db():
    """初始化审计数据库"""
    os.makedirs("data", exist_ok=True)
    
    conn = sqlite3.connect(AUDIT_DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL,
            action TEXT NOT NULL,
            user_id TEXT,
            session_id TEXT,
            agent_name TEXT,
            tool_name TEXT,
            risk_level INTEGER,
            params TEXT,
            result TEXT,
            error_message TEXT,
            ip_address TEXT,
            duration_ms INTEGER,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # 索引
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_logs(session_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_logs(action)")
    
    conn.commit()
    conn.close()
    print(f"✓ 审计数据库初始化完成: {AUDIT_DB_PATH}")


if __name__ == "__main__":
    print("=" * 50)
    print("zCloudNewAgentProject 数据库初始化")
    print("=" * 50)
    init_main_db()
    init_audit_db()
    print("=" * 50)
    print("初始化完成！")
    print("=" * 50)
