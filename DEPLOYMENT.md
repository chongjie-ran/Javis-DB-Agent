# Javis-DB-Agent 部署指南

> 版本：v1.3.1 | 更新日期：2026-03-30

---

## 目录

- [快速部署](#快速部署)
- [环境要求](#环境要求)
- [配置说明](#配置说明)
- [Docker 部署](#docker-部署)
- [Systemd 部署](#systemd-部署)
- [生产环境检查清单](#生产环境检查清单)

---

## 快速部署

### Docker 部署（推荐）

```bash
# 克隆项目
git clone https://github.com/your-org/Javis-DB-Agent.git
cd Javis-DB-Agent

# 复制并编辑配置
cp .env.example .env
# 编辑 .env 配置ollama地址和端口

# 启动
docker compose up -d

# 查看日志
docker compose logs -f
```

### Docker + MySQL 部署（生产环境）

```bash
# 使用 MySQL 作为会话存储后端
docker compose -f docker-compose.mysql.yml up -d
```

---

## 环境要求

| 组件 | 最低版本 | 推荐版本 |
|------|----------|----------|
| Python | 3.10 | 3.11 |
| Ollama | 0.1.26 | 最新 |
| Docker | 20.10 | 24.0+ |
| 内存 | 4 GB | 8 GB+ |
| CPU | 2 核 | 4 核+ |

### Ollama 模型准备

```bash
# 安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 下载模型
ollama pull llama3.2
ollama pull nomic-embed-text

# 验证
ollama list
```

---

## 配置说明

### 核心配置（`.env`）

```bash
# 服务配置
JAVIS_HOST=0.0.0.0          # 绑定地址
JAVIS_PORT=8000             # HTTP 端口

# LLM 配置
OLLAMA_BASE_URL=http://localhost:11434  # Ollama API 地址
OLLAMA_MODEL=llama3.2      # 默认模型

# 日志
LOG_LEVEL=INFO              # DEBUG|INFO|WARNING|ERROR

# 认证
ENABLE_AUTH=false          # 是否启用 API 认证
```

### TLS/SSL 配置（可选）

```bash
# 启用 HTTPS
ZLOUD_HTTPS_ENABLED=true
ZLOUD_SSL_CERT_FILE=/path/to/cert.pem
ZLOUD_SSL_KEY_FILE=/path/to/key.pem

# HSTS（启用 HTTPS 后）
ZLOUD_HSTS_ENABLED=true
ZLOUD_HSTS_MAX_AGE=31536000
```

### 企业微信集成（可选）

```bash
# 启用企业微信通道
WECOM_ENABLED=true
WECOM_CORP_ID=your-corp-id
WECOM_AGENT_ID=1000001
WECOM_CORP_SECRET=your-secret
WECOM_CALLBACK_URL=https://your-domain.com/api/v1/channels/wecom/callback
WECOM_CALLBACK_TOKEN=your-token
```

---

## Docker 部署

### 多平台支持

镜像支持以下平台：
- `linux/amd64` (Intel/AMD x86_64)
- `linux/arm64` (Apple Silicon, ARM64 服务器)

无需额外配置，Docker 自动选择对应平台的镜像。

### 构建镜像

```bash
# 构建（自动选择当前平台）
docker build -t javis-db-agent:v1.3.1 .

# 指定平台构建
docker build --platform linux/amd64 -t javis-db-agent:v1.3.1 .
docker build --platform linux/arm64 -t javis-db-agent:v1.3.1 .
docker build --platform linux/amd64,linux/arm64 -t javis-db-agent:v1.3.1 .
```

### 运行容器

```bash
# 方式1：直接运行
docker run -d \
  --name javis-db-agent \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --env-file .env \
  javis-db-agent:v1.3.1

# 方式2：docker compose（推荐）
docker compose up -d
```

### Docker Compose 配置

`docker-compose.yml` 包含：
- Javis-DB-Agent 服务
- 持久化卷挂载
- 健康检查
- 日志轮转

### 健康检查

```bash
# 检查健康状态
curl http://localhost:8000/health

# 查看 API 文档
open http://localhost:8000/docs
```

---

## Systemd 部署

适用于 Linux 服务器直接部署（绕过 Docker）。

### 安装

```bash
# 以 root 身份运行安装脚本
sudo bash install.sh
```

### 服务管理

```bash
# 启动服务
sudo systemctl start javis-agent

# 停止服务
sudo systemctl stop javis-agent

# 重启服务
sudo systemctl restart javis-agent

# 查看状态
sudo systemctl status javis-agent

# 查看日志
sudo journalctl -u javis-agent -f

# 启用开机自启
sudo systemctl enable javis-agent
```

### 安装脚本功能

`install.sh` 会：
1. 创建系统用户 `javis`
2. 复制服务文件到 `/etc/systemd/system/`
3. 创建数据目录 `/opt/javis/data`
4. 配置日志轮转
5. 安装依赖（pip install -r requirements.txt）

### 手动安装步骤

```bash
# 1. 创建用户
sudo useradd -r -s /bin/false javis

# 2. 创建目录
sudo mkdir -p /opt/javis/{data,logs}
sudo chown javis:javis /opt/javis/{data,logs}

# 3. 复制文件
sudo cp -r . /opt/javis/
sudo chown -R javis:javis /opt/javis/

# 4. 安装依赖
cd /opt/javis
sudo -u javis pip install --user -r requirements.txt

# 5. 复制服务文件
sudo cp javis-agent.service /etc/systemd/system/
sudo systemctl daemon-reload

# 6. 启动
sudo systemctl start javis-agent
sudo systemctl enable javis-agent
```

### 服务文件内容（`javis-agent.service`）

```ini
[Unit]
Description=Javis DB Agent Service
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=javis
WorkingDirectory=/opt/javis
Environment="PATH=/home/javis/.local/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONPATH=/opt/javis"
ExecStart=/home/javis/.local/bin/python3 -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

# 日志
StandardOutput=journal
StandardError=journal
SyslogIdentifier=javis-agent

# 安全加固
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/javis/data /opt/javis/logs

[Install]
WantedBy=multi-user.target
```

---

## 生产环境检查清单

### 安全

- [ ] `ENABLE_AUTH=true` 并配置 API Key
- [ ] HTTPS 证书配置（`ZLOUD_HTTPS_ENABLED=true`）
- [ ] 企业微信回调 Token 足够随机
- [ ] 防火墙限制访问来源
- [ ] 定期更新 Ollama 版本

### 运维

- [ ] 配置日志轮转（已包含在 systemd 服务中）
- [ ] 配置监控告警（企业微信告警推送）
- [ ] 定期备份数据目录 `data/`
- [ ] 磁盘空间监控

### 性能

- [ ] 内存 ≥ 8 GB
- [ ] Ollama 模型已下载到本地
- [ ] 数据库（MySQL）连接池配置
- [ ] 考虑 GPU 加速（NVIDIA CUDA 或 Apple Metal）

---

## 常见问题

### Q: 容器启动失败，显示端口被占用

```bash
# 检查端口占用
lsof -i :8000

# 修改 .env 中的端口
JAVIS_PORT=8001
```

### Q: Ollama 连接失败

```bash
# 确认 Ollama 正在运行
curl http://localhost:11434/api/tags

# 检查 .env 中地址是否正确
OLLAMA_BASE_URL=http://localhost:11434
```

### Q: 企业微信消息无法接收

```bash
# 确认外网可访问回调地址
curl -I https://your-domain.com/api/v1/channels/wecom/callback

# 检查 Token 配置
WECOM_CALLBACK_TOKEN=your-random-token-here
```

### Q: 如何升级？

```bash
# Docker 部署
docker pull javis-db-agent:v1.3.1
docker compose down
docker compose up -d

# 直接部署
cd /opt/javis
git pull
pip install --user -r requirements.txt
systemctl restart javis-agent
```
