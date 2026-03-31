"""Round24: V2.5 复杂测试用例扩展
=====================================
覆盖 PostgreSQL 和 MySQL 各 5+ 复杂故障场景：
  PostgreSQL: 连接池耗尽、磁盘空间告警、慢查询、重复索引检测、死锁模拟
  MySQL:     主从延迟模拟、表锁等待、临时表空间告警、慢查询日志分析、复制中止

前置条件：
  - PostgreSQL: localhost:5432, user=chongjieran, database=postgres
  - MySQL:      localhost:3306, user=root, password=root
"""
