# 第四轮迭代 - 悟通任务清单

## 项目信息
- 项目路径: `/Users/chongjieran/SWproject/Javis-DB-Agent/`
- 任务类型: Javis-DB-Agent API研究 + Mock数据升级 + 认证框架

## 任务说明

第四轮迭代中，你（悟通）负责以下工作：

### Day 1-2: Javis-DB-Agent API文档研究

1. **研究Javis API认证机制**
   - 分析OAuth2.0认证流程
   - Token刷新机制
   - API Key vs OAuth对比

2. **分析真实告警数据格式**
   - 字段结构
   - 嵌套关系
   - 自定义字段

3. **了解API限制**
   - QPS限制
   - 错误码体系

4. **输出文档**
   - `docs/javis-db-api-research.md`
   - `docs/javis-db-auth-design.md`

### Day 3: Mock数据升级

1. **升级告警Mock数据格式**
   - 添加custom_fields嵌套
   - 添加annotations
   - 添加nested_alerts

2. **实现QPS限制模拟器**
   - `src/mock_api/qps_limiter.py`

### Day 4-5: 认证模块框架

1. **设计认证模块接口**
   - OAuth2.0预留位置
   - Token管理接口

2. **实现真实/Mock切换开关**
   - `src/mock_api/javis_client.py` 支持切换

## 执行命令

```bash
cd /Users/chongjieran/SWproject/Javis-DB-Agent

# 运行现有测试确认环境正常
python3 -m pytest tests/ -v --tb=short

# 开始Day 1任务：研究API文档
# ... 完成研究后写文档到 docs/ 目录
```

## 成功标准

| 标准 | 目标 |
|------|------|
| API研究文档 | 包含完整认证机制、接口清单 |
| Mock数据格式 | 接近真实zCloud 60%相似度 |
| 认证框架 | 预留OAuth2.0接口，可切换 |

## 已知限制

- 无真实Javis环境，依赖文档研究
- Mock API需要兼容现有189个测试
- 认证框架仅为预留位置，不实现完整OAuth

---

*道衍授权执行 - 2026-03-28 19:12*
