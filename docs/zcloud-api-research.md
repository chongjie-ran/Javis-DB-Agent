# zCloud API 研究文档

> 版本：v1.0 | 日期：2026-03-28 | 作者：悟通

---

## 一、zCloud 平台概述

zCloud 是一个数据库云管平台，支持多种数据库类型（MySQL、PostgreSQL、Oracle等）的运维管理、监控告警和自动化运维。

---

## 二、API 架构

### 2.1 基本信息

| 项目 | 值 |
|------|-----|
| 协议 | REST over HTTPS |
| 数据格式 | JSON |
| 认证方式 | OAuth2.0 / API Key |
| API版本 | v1 (当前) |
| 基础路径 | `/api/v1` |

### 2.2 核心 API 模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 实例管理 | `/api/v1/instances` | 数据库实例的CRUD |
| 告警管理 | `/api/v1/alerts` | 告警查询、确认、解决 |
| 会话管理 | `/api/v1/sessions` | 数据库会话查询 |
| 锁管理 | `/api/v1/locks` | 锁等待分析 |
| SQL监控 | `/api/v1/sqls` | 慢SQL、TOP SQL |
| 复制管理 | `/api/v1/replication` | 主从复制状态 |
| 参数管理 | `/api/v1/parameters` | 数据库参数 |
| 容量管理 | `/api/v1/capacity` | 表空间、存储容量 |
| 巡检管理 | `/api/v1/inspection` | 健康巡检 |
| 工单管理 | `/api/v1/workorders` | 运维工单 |

---

## 三、认证机制

### 3.1 OAuth2.0 认证流程

```
+--------+                               +---------------+
|        |--(A)- Authorization Request ->|   Resource    |
|        |                               |     Owner     |
|        |<-(B)-- Authorization Grant ---|               |
|        |                               +---------------+
|        |
|        |                               +---------------+
|        |--(C)-- Authorization Grant -->| Authorization |
| Client |                               |     Server    |
|        |<-(D)----- Access Token -------|               |
|        |                               +---------------+
|        |
|        |                               +---------------+
|        |--(E)----- Access Token ------>|    Resource   |
|        |                               |     Server    |
|        |<-(F)--- Protected Resource ---|               |
+--------+                               +---------------+
```

#### 授权码模式流程

1. **Authorization Request**: 用户访问 `/oauth/authorize?client_id=xxx&redirect_uri=xxx&response_type=code&scope=xxx`
2. **Authorization Grant**: 用户授权后，返回 `code=xxx`
3. **Token Request**: 客户端用 `code` 换取 token
   ```
   POST /oauth/token
   Content-Type: application/x-www-form-urlencoded
   
   grant_type=authorization_code&code=xxx&client_id=xxx&client_secret=xxx&redirect_uri=xxx
   ```
4. **Access Token Response**:
   ```json
   {
     "access_token": "eyJhbGciOiJSUzI1NiIs...",
     "token_type": "Bearer",
     "expires_in": 3600,
     "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2...",
     "scope": "read write"
   }
   ```

### 3.2 Token 刷新机制

```python
# Token 刷新请求
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=xxx&client_id=xxx&client_secret=xxx
```

响应：
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "new_refresh_token_here"
}
```

### 3.3 API Key 认证

对于机器到机器的场景，可以使用 API Key：

```
Authorization: ApiKey <your-api-key>
```

或通过 Header：
```
X-API-Key: <your-api-key>
```

### 3.4 认证框架设计（预留）

```python
class AuthProvider(ABC):
    """认证提供者抽象接口"""
    
    @abstractmethod
    def get_access_token(self) -> str:
        """获取访问令牌"""
        pass
    
    @abstractmethod
    def refresh_token(self) -> bool:
        """刷新令牌"""
        pass
    
    @abstractmethod
    def is_token_valid(self) -> bool:
        """检查令牌是否有效"""
        pass


class OAuth2Provider(AuthProvider):
    """OAuth2.0认证提供者"""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_url: str,
        scope: str = "read write"
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.scope = scope
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_expires_at: float = 0
    
    def get_access_token(self) -> str:
        """获取访问令牌（自动刷新）"""
        if not self.is_token_valid():
            self.refresh_token()
        return self._access_token


class APIKeyProvider(AuthProvider):
    """API Key认证提供者"""
    
    def __init__(self, api_key: str):
        self._api_key = api_key
    
    def get_access_token(self) -> str:
        return self._api_key
    
    def refresh_token(self) -> bool:
        # API Key 不需要刷新
        return True
    
    def is_token_valid(self) -> bool:
        return True
```

---

## 四、API 接口详情

### 4.1 告警管理 API

#### 4.1.1 查询告警列表

```
GET /api/v1/alerts
```

**Query 参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| instance_id | string | 否 | 实例ID |
| severity | string | 否 | critical/warning/info |
| status | string | 否 | firing/resolved |
| limit | int | 否 | 返回数量，默认50 |

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": [
    {
      "alert_id": "ALT-20260328-001",
      "alert_code": "CPU_HIGH",
      "alert_name": "CPU使用率过高",
      "severity": "warning",
      "instance_id": "INS-001",
      "instance_name": "PROD-ORDER-DB",
      "message": "CPU使用率达到85.5%，超过阈值80%",
      "metric_value": 85.5,
      "threshold": 80.0,
      "unit": "%",
      "occurred_at": 1743158400.123,
      "status": "firing",
      "acknowledged": false,
      "custom_fields": {
        "host_ip": "192.168.1.100",
        "region": "华东-上海",
        "cluster": "prod-cluster-01",
        "environment": "production"
      },
      "annotations": {
        "first_occurrence": "2026-03-28T09:00:00Z",
        "last_evaluation": "2026-03-28T10:00:00Z",
        "acknowledged_by": null,
        "acknowledged_at": null,
        "resolved_at": null,
        "incident_id": "INC-20260328-001"
      },
      "nested_alerts": []
    }
  ],
  "total": 1,
  "timestamp": 1743158400.456
}
```

#### 4.1.2 获取告警详情

```
GET /api/v1/alerts/{alert_id}
```

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "alert_id": "ALT-20260328-001",
    "alert_code": "CPU_HIGH",
    "alert_name": "CPU使用率过高",
    "severity": "warning",
    "instance_id": "INS-001",
    "instance_name": "PROD-ORDER-DB",
    "message": "CPU使用率达到85.5%，超过阈值80%",
    "metric_value": 85.5,
    "threshold": 80.0,
    "unit": "%",
    "occurred_at": 1743158400.123,
    "status": "firing",
    "acknowledged": false,
    "duration_seconds": 3600,
    "custom_fields": {
      "host_ip": "192.168.1.100",
      "region": "华东-上海",
      "cluster": "prod-cluster-01",
      "environment": "production",
      "business_line": "订单系统",
      "on_call": "张三"
    },
    "annotations": {
      "first_occurrence": "2026-03-28T09:00:00Z",
      "last_evaluation": "2026-03-28T10:00:00Z",
      "acknowledged_by": null,
      "acknowledged_at": null,
      "resolved_at": null,
      "incident_id": "INC-20260328-001",
      "runbook_url": "https://wiki.example.com/runbooks/cpu-high",
      "dashboard_url": "https://grafana.example.com/d/cpu"
    },
    "nested_alerts": [
      {
        "alert_id": "ALT-20260328-002",
        "alert_code": "LOAD_HIGH",
        "alert_name": "系统负载过高",
        "severity": "info",
        "occurred_at": 1743158500.123
      }
    ],
    "related_instances": [
      {
        "instance_id": "INS-002",
        "instance_name": "PROD-USER-DB",
        "relationship": "same_cluster"
      }
    ]
  }
}
```

#### 4.1.3 确认告警

```
POST /api/v1/alerts/{alert_id}/acknowledge
```

**请求体**：
```json
{
  "acknowledged_by": "operator@example.com",
  "comment": "正在处理中"
}
```

#### 4.1.4 解决告警

```
POST /api/v1/alerts/{alert_id}/resolve
```

**请求体**：
```json
{
  "resolved_by": "operator@example.com",
  "resolution": "已扩容CPU",
  "resolution_type": "fixed"
}
```

### 4.2 实例管理 API

#### 4.2.1 获取实例详情

```
GET /api/v1/instances/{instance_id}
```

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "instance_id": "INS-001",
    "instance_name": "PROD-ORDER-DB",
    "db_type": "postgresql",
    "version": "PostgreSQL 14.5",
    "status": "running",
    "role": "primary",
    "host": "192.168.1.10",
    "port": 5432,
    "region": "华东-上海",
    "cluster": "prod-cluster-01",
    "metrics": {
      "cpu_percent": 45.2,
      "memory_percent": 68.5,
      "disk_percent": 55.0,
      "connections": 156,
      "max_connections": 500,
      "buffer_cache_hit_ratio": 98.5,
      "transaction_per_second": 1250
    },
    "uptime_seconds": 864000,
    "created_at": "2025-01-01T00:00:00Z",
    "tags": ["production", "order-system", "core"],
    "backup_enabled": true,
    "ha_enabled": true
  }
}
```

### 4.3 会话管理 API

#### 4.3.1 查询会话列表

```
GET /api/v1/sessions?instance_id=INS-001&limit=20
```

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "instance_id": "INS-001",
    "sessions": [
      {
        "sid": 1001,
        "serial": 2001,
        "username": "app_user_0",
        "status": "ACTIVE",
        "program": "python-0.exe",
        "machine": "app-server-1",
        "sql_id": "sql_aaaaaaaa",
        "wait_event": "db file sequential read",
        "seconds_in_wait": 45,
        "logon_time": 1743154800.123,
        "client_ip": "192.168.1.100"
      }
    ],
    "total": 156,
    "active_count": 142,
    "timestamp": 1743158400.456
  }
}
```

### 4.4 锁管理 API

#### 4.4.1 查询锁等待

```
GET /api/v1/locks?instance_id=INS-001
```

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "instance_id": "INS-001",
    "locks": [
      {
        "wait_sid": 1001,
        "wait_serial": 2001,
        "wait_sql_id": "sql_aaaaaaaa",
        "wait_username": "app_user_0",
        "lock_type": "transaction",
        "mode_held": "Exclusive",
        "mode_requested": "Share",
        "lock_id1": "12345",
        "lock_id2": "67890",
        "lock_table": "orders",
        "blocker_sid": 1002,
        "blocker_serial": 2002,
        "blocker_sql_id": "sql_bbbbbbbb",
        "blocker_username": "app_user_1",
        "wait_seconds": 120,
        "chain_length": 2
      }
    ],
    "total_blocked": 5,
    "deadlock_count": 0,
    "timestamp": 1743158400.456
  }
}
```

### 4.5 SQL 监控 API

#### 4.5.1 查询慢SQL

```
GET /api/v1/sqls/slow?instance_id=INS-001&limit=10
```

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "instance_id": "INS-001",
    "slow_sqls": [
      {
        "sql_id": "sql_aaaaaaaa",
        "sql_text": "SELECT * FROM orders WHERE status = 'pending' AND created_at > SYSDATE - 7",
        "executions": 1000,
        "elapsed_time_sec": 30.5,
        "avg_elapsed_sec": 0.0305,
        "disk_reads": 50000,
        "buffer_gets": 100000,
        "rows_processed": 10000,
        "first_load_time": 1743072000.123,
        "last_active_time": 1743154800.456
      }
    ],
    "count": 10,
    "order_by": "elapsed_time",
    "timestamp": 1743158400.789
  }
}
```

#### 4.5.2 查询SQL执行计划

```
GET /api/v1/sqls/{sql_id}/plan?instance_id=INS-001
```

**响应示例**：
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "sql_id": "sql_aaaaaaaa",
    "instance_id": "INS-001",
    "plan": [
      {
        "id": 0,
        "operation": "SELECT",
        "options": null,
        "object_name": null,
        "optimizer": "ALL_ROWS",
        "cost": 100,
        "cardinality": 1000,
        "bytes": 50000
      },
      {
        "id": 1,
        "operation": "TABLE ACCESS FULL",
        "options": null,
        "object_name": "ORDERS",
        "optimizer": "ALL_ROWS",
        "cost": 100,
        "cardinality": 1000,
        "bytes": 50000,
        "filter": "STATUS='pending'",
        "access_predicate": "CREATED_AT>SYSDATE-7"
      }
    ],
    "timestamp": 1743158400.123
  }
}
```

---

## 五、QPS 限制

### 5.1 限制规格

| API 类型 | QPS 限制 | 说明 |
|----------|----------|------|
| 查询类 API | 100 QPS | 实例、告警、会话查询 |
| 写操作 API | 20 QPS | 确认告警、创建工单 |
| 批量操作 API | 5 QPS | 批量确认、批量处理 |

### 5.2 限流响应

当超过 QPS 限制时，返回 HTTP 429：

```json
{
  "code": 42901,
  "message": "Rate limit exceeded",
  "error": "Too many requests",
  "retry_after": 1,
  "limit": 100,
  "remaining": 0,
  "reset_at": 1743158401.0
}
```

### 5.3 QPS 限制模拟器

```python
import time
from threading import Lock
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QPSLimiter:
    """QPS 限制模拟器"""
    
    max_qps: float = 100.0
    window_seconds: float = 1.0
    _requests: list[float] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)
    
    def __post_init__(self):
        self._requests = []
        self._lock = Lock()
    
    def should_limit(self) -> bool:
        """判断是否应该限流"""
        with self._lock:
            now = time.time()
            # 清理过期请求
            cutoff = now - self.window_seconds
            self._requests = [r for r in self._requests if r > cutoff]
            
            if len(self._requests) >= self.max_qps:
                return True
            
            self._requests.append(now)
            return False
    
    def get_remaining(self) -> int:
        """获取剩余请求次数"""
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            active = [r for r in self._requests if r > cutoff]
            return max(0, int(self.max_qps - len(active)))
    
    def get_reset_time(self) -> float:
        """获取限流重置时间戳"""
        with self._lock:
            if not self._requests:
                return time.time()
            return min(self._requests) + self.window_seconds
    
    def wait_if_needed(self) -> float:
        """如果需要限流则等待，返回等待秒数"""
        wait_time = 0.0
        with self._lock:
            now = time.time()
            cutoff = now - self.window_seconds
            self._requests = [r for r in self._requests if r > cutoff]
            
            if len(self._requests) >= self.max_qps:
                # 计算需要等待的时间
                oldest = min(self._requests)
                wait_time = oldest + self.window_seconds - now
                if wait_time > 0:
                    pass  # 锁内不sleep，外面处理
            else:
                self._requests.append(now)
        
        if wait_time > 0:
            time.sleep(wait_time)
        return wait_time


class MultiTierQPSLimiter:
    """多层级QPS限制器"""
    
    def __init__(
        self,
        query_qps: float = 100.0,
        write_qps: float = 20.0,
        batch_qps: float = 5.0
    ):
        self.query_limiter = QPSLimiter(max_qps=query_qps)
        self.write_limiter = QPSLimiter(max_qps=write_qps)
        self.batch_limiter = QPSLimiter(max_qps=batch_qps)
    
    def check_limit(self, api_type: str) -> tuple[bool, Optional[str]]:
        """
        检查是否限流
        返回: (是否通过, 错误类型)
        """
        limiter_map = {
            "query": (self.query_limiter, "query_limit"),
            "write": (self.write_limiter, "write_limit"),
            "batch": (self.batch_limiter, "batch_limit"),
        }
        
        limiter, error_type = limiter_map.get(api_type, (self.query_limiter, "query_limit"))
        
        if limiter.should_limit():
            return False, error_type
        return True, None
```

---

## 六、错误码体系

### 6.1 错误码定义

| 错误码 | HTTP Status | 说明 |
|--------|-------------|------|
| 0 | 200 | 成功 |
| 40001 | 400 | 参数错误 |
| 40101 | 401 | 未认证 |
| 40102 | 401 | 令牌过期 |
| 40103 | 401 | 令牌无效 |
| 40301 | 403 | 无权限 |
| 40401 | 404 | 资源不存在 |
| 40901 | 409 | 资源冲突 |
| 42901 | 429 | QPS超限 |
| 50001 | 500 | 服务器内部错误 |
| 50301 | 503 | 服务不可用 |

### 6.2 错误响应格式

```json
{
  "code": 42901,
  "message": "Rate limit exceeded",
  "error": {
    "code": 42901,
    "message": "Rate limit exceeded",
    "retry_after": 1,
    "limit": 100,
    "remaining": 0
  },
  "request_id": "req_abc123",
  "timestamp": 1743158400.123
}
```

---

## 七、与 Mock API 的差异

### 7.1 当前 Mock API 的不足

1. **告警格式过于简单**：缺少 `custom_fields`、`annotations`、`nested_alerts` 等嵌套结构
2. **无认证机制**：所有接口都是公开的
3. **无 QPS 限制**：不模拟限流场景
4. **数据不够真实**：字段值和结构与真实 API 有差异

### 7.2 升级计划

1. ✅ 升级告警数据格式（添加嵌套字段）
2. ✅ 实现 QPS 限制模拟器
3. ✅ 添加认证框架预留位置
4. ✅ 增加更多真实场景数据

---

## 八、后续对接计划

### 8.1 真实 API 对接步骤

1. 获取 zCloud 平台的 OAuth2.0 凭证（client_id, client_secret）
2. 配置 token URL 和 scope
3. 实现 token 自动刷新逻辑
4. 替换 Mock 客户端为真实客户端
5. 逐步灰度切换

### 8.2 Mock/Real 切换开关

```python
class ZCloudClientFactory:
    """客户端工厂，支持 Mock/Real 切换"""
    
    @staticmethod
    def create(
        use_mock: bool = True,
        mock_host: str = "localhost:18080",
        real_base_url: str = None,
        auth_provider: AuthProvider = None
    ) -> ZCloudClientProtocol:
        if use_mock:
            return MockZCloudClient(base_url=f"http://{mock_host}/api/v1")
        else:
            return RealZCloudClient(
                base_url=real_base_url,
                auth_provider=auth_provider
            )
```

---

*文档版本：v1.0 | 最后更新：2026-03-28*
