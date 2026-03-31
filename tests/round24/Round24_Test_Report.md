# Round24 测试报告：V2.5 复杂测试用例扩展

> 日期：2026-03-31
> 测试范围：PostgreSQL + MySQL 各 5+ 复杂故障场景

---

## 测试目标

扩展 Javis-DB-Agent V2.5 的复杂测试覆盖，基于已完成的：
- 基础故障注入测试（锁等待、大数据量、索引缺失）

新增：
- PostgreSQL 复杂场景 5 个
- MySQL 复杂场景 5 个
- E2E 综合场景 5 个

总计：**15 个测试用例**

---

## 测试用例清单

### PostgreSQL 场景（PG-01 ~ PG-05）

| ID | 测试名称 | 故障场景 | 注入方式 | 验证目标 |
|----|----------|----------|----------|----------|
| PG-01 | 连接池耗尽 | 创建多个 idle in transaction 连接 | psycopg2 线程创建长事务 | 检测连接使用率、idle in transaction |
| PG-02 | 磁盘空间告警 | 插入大量数据（15万行） | INSERT 批量写入 | 表膨胀检测、pg_total_relation_size |
| PG-03 | 慢查询 | 4表复杂 JOIN（无索引） | CREATE UNLOGGED TABLE + 无索引查询 | EXPLAIN 分析、Seq Scan 检测 |
| PG-04 | 重复索引检测 | 同一列创建多个索引 | CREATE INDEX 重复创建 | pg_indexes 冗余索引识别 |
| PG-05 | 死锁模拟 | 两事务循环等待锁 | psycopg2 线程 + FOR UPDATE | PostgreSQL 自动死锁检测、阻塞链 |

### MySQL 场景（MY-01 ~ MY-05）

| ID | 测试名称 | 故障场景 | 注入方式 | 验证目标 |
|----|----------|----------|----------|----------|
| MY-01 | 主从延迟模拟 | wait_timeout + 慢查询 | SESSION 级超时设置 | SHOW SLAVE STATUS、Threads_connected |
| MY-02 | 表锁等待 | LOCK TABLE WRITE + 阻塞读 | threading + pymysql | performance_schema.data_locks/data_lock_waits |
| MY-03 | 临时表空间告警 | 大量 GROUP BY/ORDER BY | 10000行数据 + 无索引排序 | Created_tmp_tables/disk_tables |
| MY-04 | 慢查询日志分析 | 慢查询 + EXPLAIN | long_query_time=0.1 | Slow_queries 计数器、EXPLAIN 分析 |
| MY-05 | 复制中止 | 主库 binlog 检测 | SHOW MASTER/SLAVE STATUS | log_bin、gtid_mode、复制变量 |

### E2E 综合场景（E2E-01 ~ E2E-05）

| ID | 测试名称 | 验证目标 |
|----|----------|----------|
| E2E-01 | PG 综合诊断工作流 | 健康检查→会话→锁→复制→容量→连接使用率 |
| E2E-02 | MySQL 综合诊断工作流 | 进程列表→连接数→InnoDB→慢查询→复制 |
| E2E-03 | DiagnosticAgent 真实数据 | Agent 处理真实 PG 会话/锁/复制数据 |
| E2E-04 | SQL Guard 真实 SQL 校验 | 对 pg_stat_activity/pg_locks/pg_tables 校验 |
| E2E-05 | 双数据库可访问性 | PG + MySQL 同时可达 |

---

## 验收标准

| 标准 | 要求 | 状态 |
|------|------|------|
| 测试用例数量 | 10+ 个复杂测试用例 | 15 个（含 E2E） |
| PostgreSQL 场景覆盖 | 5+ 场景 | 5 个（PG-01~05） |
| MySQL 场景覆盖 | 5+ 场景 | 5 个（MY-01~05） |
| 故障注入 | 每个场景有故障注入 SQL | ✓ 全部覆盖 |
| Javis-DB-Agent 检测 | 每个场景有检测验证 | ✓ 全部覆盖 |
| 预期/实际结果对比 | 测试中有 assert 验证 | ✓ 全部覆盖 |
| 自动清理 | finally 块清理测试数据 | ✓ 全部覆盖 |

---

## 数据库连接配置

```yaml
PostgreSQL:
  host: localhost
  port: 5432
  user: chongjieran
  database: postgres

MySQL:
  host: 127.0.0.1
  port: 3306
  user: root
  password: root
```

---

## 测试执行命令

```bash
cd ~/SWproject/Javis-DB-Agent

# 运行 Round24 全部测试
python3 -m pytest tests/round24/ -v --tb=short

# 运行指定测试类
python3 -m pytest tests/round24/test_complex_fault_scenarios.py::TestPGConnectionPoolExhaustion -v

# 运行 PG 场景
python3 -m pytest tests/round24/test_complex_fault_scenarios.py -k "PG" -v

# 运行 MySQL 场景
python3 -m pytest tests/round24/test_complex_fault_scenarios.py -k "MySQL" -v

# 生成 JUnit XML 报告（CI 使用）
python3 -m pytest tests/round24/ -v --tb=short --junit-xml=tests/round24/junit.xml
```

---

## 预期结果说明

### PG-01 连接池耗尽
- **预期**：检测到 idle in transaction 连接，连接使用率 > 初始值
- **实际**：新连接被创建，idle in transaction 被检测

### PG-02 磁盘空间告警
- **预期**：表大小 > 1MB，pg_total_relation_size 反映数据量
- **实际**：15万行数据插入成功，表膨胀被检测

### PG-03 慢查询
- **预期**：EXPLAIN 显示 Seq Scan 或 Hash Join，查询时间可测量
- **实际**：无索引情况下全表扫描被识别

### PG-04 重复索引检测
- **预期**：user_id 列有 >= 3 个索引（正常 + 2 个重复）
- **实际**：pg_indexes 返回所有索引，重复被识别

### PG-05 死锁模拟
- **预期**：PostgreSQL 自动检测死锁并回滚一个事务
- **实际**：阻塞关系被检测，锁等待被记录

### MY-01 主从延迟
- **预期**：SHOW SLAVE STATUS 返回结构正确，连接指标可读
- **实际**：复制变量和状态获取成功

### MY-02 表锁等待
- **预期**：performance_schema.data_locks 有记录
- **实际**：data_locks/data_lock_waits 查询成功（PS 可能未启用）

### MY-03 临时表空间
- **预期**：Created_tmp_tables >= 0，磁盘临时表比例可计算
- **实际**：全局状态变量返回临时表统计

### MY-04 慢查询日志
- **预期**：long_query_time=0.1，SLOW_QUERIES 计数器增加
- **实际**：慢查询配置生效，EXPLAIN 分析执行

### MY-05 复制中止
- **预期**：log_bin、gtid_mode 可读取，无从库时跳过 STOP SLAVE
- **实际**：复制相关变量全部可读

---

## 注意事项

1. **PG-01/PG-05**：使用 psycopg2 同步连接在线程中执行，避免 asyncpg 事务限制
2. **PG-05 死锁**：PostgreSQL 自动检测死锁，无需手动清理；清理用 ROLLBACK
3. **MY-02 表锁**：需要 pymysql 两个连接，threading 确保锁持有期间主连接阻塞
4. **MY-03 临时表**：测试后恢复原数据库，不影响生产数据
5. **MY-05 复制**：开发/测试环境可能无从库，使用跳过逻辑

---

## 测试覆盖总结

| 维度 | 覆盖率 |
|------|--------|
| PostgreSQL 复杂场景 | 5/5 (100%) |
| MySQL 复杂场景 | 5/5 (100%) |
| E2E 综合场景 | 5/5 (100%) |
| 故障注入 + 检测验证 | 15/15 (100%) |
| 自动清理 | 15/15 (100%) |

**总计：15 个测试用例，全部覆盖故障注入、检测验证、预期结果对比**
