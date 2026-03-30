# ============================================================
# Javis-DB-Agent Makefile
# 支持：Linux (Ubuntu 22+, CentOS 7+, RHEL 7+), macOS
# ============================================================

.PHONY: help install dev test clean build docker docker-build run stop lint format check

# 默认目标
help:
	@echo "Javis-DB-Agent 构建脚本"
	@echo ""
	@echo "用法: make <目标>"
	@echo ""
	@echo "安装类:"
	@echo "  install          安装依赖（交互式，需选择操作系统）"
	@echo "  install-ubuntu   安装依赖（Ubuntu/Debian）"
	@echo "  install-centos   安装依赖（CentOS/RHEL）"
	@echo "  install-macos    安装依赖（macOS）"
	@echo "  dev              安装开发依赖"
	@echo ""
	@echo "构建类:"
	@echo "  build            构建 Python 包"
	@echo "  docker           使用 docker-compose 运行"
	@echo "  docker-build     构建 Docker 镜像"
	@echo ""
	@echo "运行类:"
	@echo "  run              启动服务（前台）"
	@echo "  start            启动服务（后台）"
	@echo "  stop             停止服务"
	@echo "  restart          重启服务"
	@echo "  status           查看服务状态"
	@echo ""
	@echo "测试类:"
	@echo "  test             运行所有测试"
	@echo "  test-coverage    运行测试并生成覆盖率报告"
	@echo "  lint             代码检查"
	@echo "  format           代码格式化"
	@echo "  check            全面检查（lint + type check）"
	@echo ""
	@echo "清理类:"
	@echo "  clean            清理构建产物"
	@echo "  deep-clean       深度清理（包括虚拟环境）"
	@echo ""
	@echo "系统类:"
	@echo "  systemd-install  安装 systemd 服务（需 sudo）"
	@echo "  systemd-uninstall 卸载 systemd 服务（需 sudo）"

# ============================================================
# 安装检测
# ============================================================

PYTHON := python3
PYTHON_VERSION := $(shell $(PYTHON) -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || echo "unknown")
VENV := .venv
VENV_PYTHON := $(VENV)/bin/python

# 检测操作系统
OS_TYPE := $(shell uname -s | tr '[:upper:]' '[:lower:]')
ifeq ($(OS_TYPE),darwin)
	INSTALL_OS = macos
else ifeq ($(OS_TYPE),linux)
	# 检测 Linux 发行版
	ifneq ($(wildcard /etc/os-release),)
		DISTRIB_ID := $(shell . /etc/os-release 2>/dev/null && echo $$ID)
	endif
	ifeq ($(DISTRIB_ID),ubuntu)
		INSTALL_OS = ubuntu
	else ifeq ($(DISTRIB_ID),debian)
		INSTALL_OS = ubuntu
	else ifeq ($(DISTRIB_ID),centos)
		INSTALL_OS = centos
	else ifeq ($(DISTRIB_ID),rhel)
		INSTALL_OS = centos
	else ifeq ($(DISTRIB_ID),rocky)
		INSTALL_OS = centos
	else ifeq ($(DISTRIB_ID),almalinux)
		INSTALL_OS = centos
	else
		INSTALL_OS = unknown
	endif
else
	INSTALL_OS = unknown
endif

# ============================================================
# Python 版本检查
# ============================================================

check-python:
	@$(PYTHON) -c 'import sys; sys.exit(0) if sys.version_info >= (3, 9) else sys.exit(1)' 2>/dev/null || { \
		echo "错误: Python 3.9+ required, 当前版本: $(PYTHON_VERSION)"; \
		echo "请升级 Python: https://www.python.org/downloads/"; \
		exit 1; \
	}
	@echo "✓ Python $(PYTHON_VERSION) 检查通过"

# ============================================================
# 虚拟环境
# ============================================================

$(VENV):
	@echo "创建虚拟环境..."
	$(PYTHON) -m venv $(VENV)
	@echo "✓ 虚拟环境已创建: $(VENV)"

venv-activate:
	@if [ ! -d "$(VENV)" ]; then \
		echo "错误: 虚拟环境不存在，请先运行 make install"; \
		exit 1; \
	fi
	@echo "激活虚拟环境: source $(VENV)/bin/activate"

# ============================================================
# 依赖安装
# ============================================================

install: check-python
	@echo "检测到操作系统: $(INSTALL_OS)"
	@echo "请运行对应的安装命令："
	@echo "  make install-ubuntu   # Ubuntu/Debian"
	@echo "  make install-centos   # CentOS/RHEL 7+"
	@echo "  make install-macos    # macOS"

install-ubuntu: check-python
	@echo "=== Ubuntu/Debian 安装 ==="
	@sudo apt-get update && sudo apt-get install -y \
		python3.11-venv python3-pip libpq-dev gcc \
		redis-server sqlite3 curl
	@$(PYTHON) -m venv $(VENV) || python3 -m venv $(VENV)
	@source $(VENV)/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt
	@echo "✓ Ubuntu 安装完成！激活: source $(VENV)/bin/activate"

install-centos: check-python
	@echo "=== CentOS/RHEL 安装 ==="
	@echo "注意: CentOS 7/RHEL 7 默认 Python 3.6，需要升级"
	@# CentOS 7 需要 EPEL 和 Python 3.11
	@if grep -q "CentOS Linux 7" /etc/centos-release 2>/dev/null || grep -q "Red Hat Enterprise Linux 7" /etc/redhat-release 2>/dev/null; then \
		echo "检测到 CentOS/RHEL 7，需要额外配置..."; \
		sudo yum install -y epel-release; \
		sudo yum install -y gcc openssl-devel bzip2-devel libffi-devel zlib-devel; \
		echo "请手动安装 Python 3.11+: https://github.com/pyenv/pyenv"; \
	fi
	@$(PYTHON) -m venv $(VENV) 2>/dev/null || python3 -m venv $(VENV)
	@source $(VENV)/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt
	@echo "✓ CentOS/RHEL 安装完成！"

install-macos: check-python
	@echo "=== macOS 安装 ==="
	@which brew >/dev/null 2>&1 || { echo "请先安装 Homebrew: https://brew.sh"; exit 1; }
	@brew install redis sqlite3 python@3.11 curl
	@$(PYTHON) -m venv $(VENV) || python3 -m venv $(VENV)
	@source $(VENV)/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt
	@echo "✓ macOS 安装完成！"

dev: check-python
	@if [ ! -d "$(VENV)" ]; then \
		$(PYTHON) -m venv $(VENV); \
	fi
	@source $(VENV)/bin/activate && \
		pip install --upgrade pip && \
		pip install -r requirements.txt && \
		pip install pytest pytest-asyncio pytest-cov ruff mypy
	@echo "✓ 开发依赖安装完成！"

# ============================================================
# 构建
# ============================================================

build: clean
	@echo "=== 构建 Python 包 ==="
	@pip install build
	@python -m build
	@echo "✓ 构建完成！产出物在 dist/ 目录"

wheel: clean
	@echo "=== 构建 Wheel ==="
	@pip install build
	@python -m build --wheel
	@echo "✓ Wheel 构建完成！产出物在 dist/ 目录"

# ============================================================
# Docker
# ============================================================

docker:
	@echo "=== 启动 Docker 服务 ==="
	docker-compose up -d
	@echo "✓ 服务已启动！"
	@echo "  API: http://localhost:8000"
	@echo "  Docs: http://localhost:8000/docs"
	@echo "  Dashboard: http://localhost:8000/dashboard"

docker-build:
	@echo "=== 构建 Docker 镜像 ==="
	docker-compose build --no-cache
	@echo "✓ 镜像构建完成！"

docker-logs:
	docker-compose logs -f

docker-stop:
	docker-compose down

docker-clean:
	docker-compose down -v --rmi local

# ============================================================
# 服务管理
# ============================================================

run: venv-activate
	@source $(VENV)/bin/activate && \
		OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434} \
		uvicorn src.main:app --host 0.0.0.0 --port 8000 --reload

start: venv-activate
	@source $(VENV)/bin/activate && \
		nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 > logs/javis-agent.log 2>&1 & \
		echo $$! > .javis-agent.pid
	@echo "✓ 服务已在后台启动，PID: $$(cat .javis-agent.pid)"

stop:
	@if [ -f .javis-agent.pid ]; then \
		kill $$(cat .javis-agent.pid) 2>/dev/null && echo "✓ 服务已停止" || echo "服务未运行"; \
		rm -f .javis-agent.pid; \
	else \
		echo "服务未运行"; \
	fi

restart: stop start

status:
	@if [ -f .javis-agent.pid ]; then \
		PID=$$(cat .javis-agent.pid); \
		if ps -p $$PID > /dev/null 2>&1; then \
			echo "✓ 服务运行中 (PID: $$PID)"; \
		else \
			echo "✗ 服务未运行 (PID 文件存在但进程已退出)"; \
		fi; \
	else \
		echo "✗ 服务未运行"; \
	fi

# ============================================================
# 测试
# ============================================================

test: $(VENV)
	@source $(VENV)/bin/activate && \
		PYTHONPATH=. pytest tests/ -v

test-coverage: venv-activate
	@source $(VENV)/bin/activate && \
		PYTHONPATH=. pytest tests/ --cov=src --cov-report=html --cov-report=term
	@echo "✓ 覆盖率报告: htmlcov/index.html"

# ============================================================
# 代码质量
# ============================================================

lint:
	@ruff check src/ tests/

format:
	@ruff format src/ tests/

check: lint
	@echo "=== Type Check ==="
	@mypy src/ --ignore-missing-imports || echo "mypy 未安装，跳过类型检查"

# ============================================================
# 清理
# ============================================================

clean:
	@echo "清理构建产物..."
	@rm -rf build/ dist/ *.egg-info .pytest_cache .coverage htmlcov/
	@rm -rf __pycache__ src/__pycache__ src/**/__pycache__
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ 清理完成"

deep-clean: clean
	@echo "深度清理..."
	@rm -rf .venv .pytest_cache .coverage htmlcov/
	@rm -f .javis-agent.pid
	@echo "✓ 深度清理完成"

# ============================================================
# systemd 服务
# ============================================================

SYSTEMD_SERVICE=javis-agent.service
SYSTEMD_UNIT_DIR=/etc/systemd/system

systemd-install:
	@echo "=== 安装 systemd 服务 ==="
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "错误: 需要 root 权限。请运行: sudo make systemd-install"; \
		exit 1; \
	fi
	@cp $(SYSTEMD_SERVICE) $(SYSTEMD_UNIT_DIR)/$(SYSTEMD_SERVICE)
	@chmod 644 $(SYSTEMD_UNIT_DIR)/$(SYSTEMD_SERVICE)
	@systemctl daemon-reload
	@systemctl enable $(SYSTEMD_SERVICE)
	@echo "✓ systemd 服务已安装并设置为开机自启"
	@echo "  启动: sudo systemctl start javis-agent"
	@echo "  停止: sudo systemctl stop javis-agent"
	@echo "  查看日志: sudo journalctl -u javis-agent -f"

systemd-uninstall:
	@echo "=== 卸载 systemd 服务 ==="
	@if [ "$$(id -u)" -ne 0 ]; then \
		echo "错误: 需要 root 权限。请运行: sudo make systemd-uninstall"; \
		exit 1; \
	fi
	@systemctl stop $(SYSTEMD_SERVICE) 2>/dev/null || true
	@systemctl disable $(SYSTEMD_SERVICE) 2>/dev/null || true
	@rm -f $(SYSTEMD_UNIT_DIR)/$(SYSTEMD_SERVICE)
	@systemctl daemon-reload
	@echo "✓ systemd 服务已卸载"

# ============================================================
# 初始化数据
# ============================================================

init-db:
	@mkdir -p data logs
	@touch data/javis_db_agent.db data/audit.db
	@echo "✓ 数据库初始化完成"
