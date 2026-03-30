"""
环境检查脚本
检查测试所需的数据库是否可用
"""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

import pymysql
import psycopg2


def check_mysql(host: str = None, port: int = None, user: str = None, password: str = None) -> bool:
    """检查MySQL连接"""
    host = host or os.getenv("TEST_MYSQL_HOST", "localhost")
    port = int(port or os.getenv("TEST_MYSQL_PORT", "3306"))
    user = user or os.getenv("TEST_MYSQL_USER", "root")
    password = password or os.getenv("TEST_MYSQL_PASSWORD", "")

    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            connect_timeout=5,
        )
        conn.close()
        return True
    except Exception as e:
        print(f"    MySQL连接失败: {e}")
        return False


def check_postgresql(host: str = None, port: int = None, user: str = None, password: str = None, dbname: str = None) -> bool:
    """检查PostgreSQL连接"""
    host = host or os.getenv("TEST_PG_HOST", "localhost")
    port = int(port or os.getenv("TEST_PG_PORT", "5432"))
    user = user or os.getenv("TEST_PG_USER", "javis_test")
    password = password or os.getenv("TEST_PG_PASSWORD", "javis_test123")
    dbname = dbname or os.getenv("TEST_PG_DB", "javis_test_db")

    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname=dbname,
            connect_timeout=5,
        )
        conn.close()
        return True
    except Exception as e:
        print(f"    PostgreSQL连接失败: {e}")
        return False


def get_mysql_config() -> dict:
    """获取MySQL配置"""
    return {
        "host": os.getenv("TEST_MYSQL_HOST", "localhost"),
        "port": int(os.getenv("TEST_MYSQL_PORT", "3306")),
        "user": os.getenv("TEST_MYSQL_USER", "root"),
        "password": os.getenv("TEST_MYSQL_PASSWORD", ""),
    }


def get_pg_config() -> dict:
    """获取PostgreSQL配置"""
    return {
        "host": os.getenv("TEST_PG_HOST", "localhost"),
        "port": int(os.getenv("TEST_PG_PORT", "5432")),
        "user": os.getenv("TEST_PG_USER", "javis_test"),
        "password": os.getenv("TEST_PG_PASSWORD", "javis_test123"),
        "dbname": os.getenv("TEST_PG_DB", "javis_test_db"),
    }


def main():
    """主检查流程"""
    print("=" * 50)
    print("V1.5 测试环境检查")
    print("=" * 50)

    mysql_ok = check_mysql()
    pg_ok = check_postgresql()

    print(f"\nMySQL:       {'✅ 可用' if mysql_ok else '❌ 不可用'}")
    if mysql_ok:
        cfg = get_mysql_config()
        print(f"  - Host: {cfg['host']}:{cfg['port']}, User: {cfg['user']}")

    print(f"PostgreSQL:  {'✅ 可用' if pg_ok else '❌ 不可用'}")
    if pg_ok:
        cfg = get_pg_config()
        print(f"  - Host: {cfg['host']}:{cfg['port']}, User: {cfg['user']}")

    print("\n" + "=" * 50)
    if mysql_ok or pg_ok:
        print("✅ 可以运行真实环境测试")
        return 0
    else:
        print("❌ 无可用数据库环境，无法运行真实测试")
        return 1


if __name__ == "__main__":
    sys.exit(main())
