#!/bin/bash
#===============================================================================
# Javis-DB-Agent 一键部署脚本
# 版本: V2.3
# 日期: 2026-03-31
#===============================================================================

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查操作系统
check_os() {
    log_info "检查操作系统..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macOS"
        log_info "检测到 macOS"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt-get &> /dev/null; then
            OS="Ubuntu/Debian"
            log_info "检测到 Ubuntu/Debian"
        elif command -v yum &> /dev/null; then
            OS="CentOS/RHEL"
            log_info "检测到 CentOS/RHEL"
        else
            OS="Linux"
            log_info "检测到 Linux"
        fi
    else
        log_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi
}

# 检查Python版本
check_python() {
    log_info "检查Python版本..."
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 -c 'import sys; print(sys.version_info[1])')
        if [[ $PYTHON_VERSION -ge 10 ]]; then
            log_info "Python版本: $(python3 --version)"
        else
            log_error "Python版本过低，需要3.10+"
            log_info "请访问 https://www.python.org/downloads/ 安装新版本"
            exit 1
        fi
    else
        log_error "未找到Python3"
        install_python
    fi
}

# 安装Python
install_python() {
    log_warn "正在安装Python..."
    
    if [[ "$OS" == "macOS" ]]; then
        if command -v brew &> /dev/null; then
            brew install python@3.11
        else
            log_error "请先安装Homebrew: https://brew.sh"
            exit 1
        fi
    elif [[ "$OS" == "Ubuntu/Debian" ]]; then
        sudo apt update
        sudo apt install -y python3.11 python3.11-venv python3-pip
    elif [[ "$OS" == "CentOS/RHEL" ]]; then
        sudo yum install -y python311 python311-pip
    fi
}

# 创建虚拟环境
create_venv() {
    log_info "创建虚拟环境..."
    
    if [[ -d ".venv" ]]; then
        log_warn "虚拟环境已存在，跳过创建"
    else
        python3 -m venv .venv
        log_info "虚拟环境创建成功"
    fi
    
    # 激活虚拟环境
    source .venv/bin/activate
}

# 安装依赖
install_dependencies() {
    log_info "安装项目依赖..."
    
    source .venv/bin/activate
    
    # 升级pip
    pip install --upgrade pip
    
    # 安装依赖
    pip install -r requirements.txt
    
    log_info "依赖安装完成"
}

# 安装Ollama
install_ollama() {
    log_info "检查Ollama..."
    
    if command -v ollama &> /dev/null; then
        log_info "Ollama已安装: $(ollama --version)"
    else
        log_warn "Ollama未安装（可选，用于LLM推理）"
        log_info "安装命令: curl -fsSL https://ollama.com/install.sh | sh"
    fi
}

# 安装PostgreSQL客户端
install_postgres() {
    log_info "检查PostgreSQL..."
    
    if command -v psql &> /dev/null; then
        log_info "PostgreSQL已安装: $(psql --version)"
    else
        log_warn "PostgreSQL客户端未安装（可选）"
        
        if [[ "$OS" == "macOS" ]]; then
            brew install postgresql@15
        elif [[ "$OS" == "Ubuntu/Debian" ]]; then
            sudo apt install -y postgresql-client
        fi
    fi
}

# 配置环境变量
configure_env() {
    log_info "配置环境变量..."
    
    if [[ -f ".env" ]]; then
        log_warn ".env已存在，跳过创建"
    else
        cat > .env << EOF
# Javis-DB-Agent 配置

# 数据库配置
JAVIS_PG_HOST=localhost
JAVIS_PG_PORT=5432
JAVIS_PG_USER=postgres
JAVIS_PG_PASSWORD=
JAVIS_PG_DATABASE=javis_db

# Ollama配置
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=glm4

# API模式（mock/real）
JAVIS_API_MODE=mock
EOF
        log_info ".env配置完成"
    fi
}

# 初始化数据库
init_database() {
    log_info "初始化数据库..."
    
    # 检查PostgreSQL连接
    if command -v psql &> /dev/null; then
        if PGPASSWORD="" psql -h localhost -U postgres -c "SELECT 1" &> /dev/null; then
            log_info "PostgreSQL连接正常"
            
            # 创建数据库（如果不存在）
            PGPASSWORD="" psql -h localhost -U postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'javis_db'" | grep -q 1 || \
                PGPASSWORD="" psql -h localhost -U postgres -c "CREATE DATABASE javis_db"
            
            log_info "数据库初始化完成"
        else
            log_warn "无法连接到PostgreSQL，请确保PostgreSQL服务运行中"
        fi
    else
        log_warn "PostgreSQL客户端未安装，跳过数据库初始化"
    fi
}

# 运行测试
run_tests() {
    log_info "运行测试..."
    
    source .venv/bin/activate
    
    if python -m pytest tests/v2.0/test_security_layer.py -v --tb=short -q &> /dev/null; then
        log_info "核心测试通过"
    else
        log_warn "部分测试失败，请检查配置"
    fi
}

# 启动服务
start_service() {
    log_info "启动服务..."
    
    log_info ""
    log_info "=============================================="
    log_info "  Javis-DB-Agent 安装完成！"
    log_info "=============================================="
    log_info ""
    log_info "启动命令："
    log_info "  source .venv/bin/activate"
    log_info "  python -m uvicorn src.main:app --host 0.0.0.0 --port 8000"
    log_info ""
    log_info "访问地址："
    log_info "  Dashboard: http://localhost:8000/dashboard/"
    log_info "  API Docs:  http://localhost:8000/docs"
    log_info ""
    log_info "Mock API（开发测试）："
    log_info "  python -m uvicorn mock_javis_api.server:app --host 0.0.0.0 --port 18080"
    log_info ""
    log_info "=============================================="
    log_info ""
}

# 主函数
main() {
    echo ""
    log_info "=============================================="
    log_info "  Javis-DB-Agent 一键部署脚本 V2.3"
    log_info "=============================================="
    echo ""
    
    # 检查
    check_os
    check_python
    
    # 安装
    create_venv
    install_dependencies
    install_ollama
    install_postgres
    
    # 配置
    configure_env
    init_database
    
    # 测试
    # run_tests
    
    # 完成
    start_service
}

# 执行主函数
main "$@"
