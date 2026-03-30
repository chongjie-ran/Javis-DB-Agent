#!/usr/bin/env bash
# ============================================================
# Javis-DB-Agent 跨平台安装脚本
# 支持: Ubuntu 22+, CentOS 7+, RHEL 7+, macOS
# Python 要求: 3.9+
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检测操作系统
detect_os() {
    OS_TYPE=$(uname -s | tr '[:upper:]' '[:lower:]')
    DISTRIB_ID=""
    DISTRIB_VERSION=""

    if [ "$OS_TYPE" = "linux" ]; then
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRIB_ID=$ID
            DISTRIB_VERSION=$VERSION_ID
        elif [ -f /etc/centos-release ]; then
            DISTRIB_ID="centos"
            DISTRIB_VERSION=$(cat /etc/centos-release | grep -oE '[0-9]+\.[0-9]+' | head -1)
        elif [ -f /etc/redhat-release ]; then
            DISTRIB_ID="rhel"
            DISTRIB_VERSION=$(cat /etc/redhat-release | grep -oE '[0-9]+\.[0-9]+' | head -1)
        fi
    fi

    echo "$OS_TYPE|$DISTRIB_ID|$DISTRIB_VERSION"
}

# Python 版本检查
check_python() {
    local python_cmd=${1:-python3}
    local python_version

    if ! command -v $python_cmd &> /dev/null; then
        log_error "Python 未安装，请先安装 Python 3.9+"
        return 1
    fi

    python_version=$($python_cmd -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')
    local major=$(echo $python_version | cut -d. -f1)
    local minor=$(echo $python_version | cut -d. -f2)

    if [ "$major" -lt 3 ] || ([ "$major" -eq 3 ] && [ "$minor" -lt 9 ]); then
        log_error "Python $python_version 不满足要求，需要 Python 3.9+"
        return 1
    fi

    log_ok "Python $python_version 检查通过"
    return 0
}

# 检测可用的 Python 版本 (Ubuntu/Debian)
detect_python_ubuntu() {
    local python_pkg=""
    
    # 优先检测已安装的 Python 3.11
    if command -v python3.11 &> /dev/null; then
        python_pkg="python3.11-venv"
    # 检测 Python 3.10
    elif command -v python3.10 &> /dev/null; then
        python_pkg="python3.10-venv"
    # 检测 Python 3.9
    elif command -v python3.9 &> /dev/null; then
        python_pkg="python3.9-venv"
    # 回退到默认 python3
    else
        python_pkg="python3-venv"
    fi
    
    echo "$python_pkg"
}

# 安装系统依赖 (Ubuntu/Debian)
install_ubuntu_deps() {
    log_info "安装 Ubuntu/Debian 系统依赖..."
    sudo apt-get update
    
    # 动态检测 Python venv 包
    local python_venv_pkg=$(detect_python_ubuntu)
    log_info "检测到 Python venv 包: $python_venv_pkg"
    
    sudo apt-get install -y \
        "$python_venv_pkg" \
        python3-pip \
        libpq-dev \
        gcc \
        redis-server \
        sqlite3 \
        curl \
        git \
        build-essential
    log_ok "Ubuntu/Debian 系统依赖安装完成"
}

# 安装系统依赖 (CentOS/RHEL 7)
install_centos7_deps() {
    log_warn "检测到 CentOS/RHEL 7，默认 Python 版本为 3.6"
    log_info "安装 EPEL 和基础依赖..."

    sudo yum install -y epel-release
    sudo yum install -y \
        gcc \
        openssl-devel \
        bzip2-devel \
        libffi-devel \
        zlib-devel \
        readline-devel \
        sqlite-devel \
        redis \
        curl \
        git \
        make

    log_info "需要手动安装 Python 3.11+"
    log_info "推荐使用 pyenv:"
    log_info "  1. git clone https://github.com/pyenv/pyenv.git ~/.pyenv"
    log_info "  2. echo 'export PYENV_ROOT=\"\$HOME/.pyenv\"' >> ~/.bashrc"
    log_info "  3. echo 'export PATH=\"\$PYENV_ROOT/bin:\$PATH\"' >> ~/.bashrc"
    log_info "  4. pyenv install 3.11.0"
    log_info "  5. pyenv global 3.11.0"

    return 1  # 需要手动步骤
}

# 安装系统依赖 (CentOS/RHEL 8+)
install_centos8_deps() {
    log_info "安装 CentOS/RHEL 8+ 系统依赖..."
    sudo dnf install -y \
        python3.11 \
        python3-pip \
        gcc \
        redis \
        sqlite \
        curl \
        git \
        make
    log_ok "CentOS/RHEL 8+ 系统依赖安装完成"
}

# 安装系统依赖 (macOS)
install_macos_deps() {
    log_info "安装 macOS 依赖..."

    if ! command -v brew &> /dev/null; then
        log_error "Homebrew 未安装，请先安装: https://brew.sh"
        return 1
    fi

    brew install \
        redis \
        sqlite3 \
        python@3.11 \
        curl \
        git

    log_ok "macOS 系统依赖安装完成"
}

# 创建虚拟环境
create_venv() {
    local python_cmd=${1:-python3}
    local venv_dir=".venv"

    if [ -d "$venv_dir" ]; then
        log_warn "虚拟环境已存在: $venv_dir"
        read -p "是否重新创建? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$venv_dir"
        else
            log_info "使用现有虚拟环境"
            return 0
        fi
    fi

    log_info "创建虚拟环境..."
    $python_cmd -m venv "$venv_dir"
    log_ok "虚拟环境创建完成: $venv_dir"
}

# 安装 Python 依赖
install_python_deps() {
    local venv_python="${VENV_DIR:-.venv}/bin/python"

    if [ ! -f "$venv_python" ]; then
        log_error "虚拟环境未找到，请先运行安装"
        return 1
    fi

    log_info "安装 Python 依赖..."
    source "${VENV_DIR:-.venv}/bin/activate"

    pip install --upgrade pip
    pip install -r requirements.txt

    log_ok "Python 依赖安装完成"
}

# 配置 Ollama
setup_ollama() {
    log_info "配置 Ollama..."

    if ! command -v ollama &> /dev/null; then
        log_warn "Ollama 未安装，跳过配置"
        log_info "安装 Ollama: https://ollama.com/download"
        return 0
    fi

    log_info "检查 Ollama 服务..."
    if ! curl -s http://localhost:11434/api/version &> /dev/null; then
        log_info "启动 Ollama 服务..."
        brew services start ollama 2>/dev/null || sudo systemctl start ollama 2>/dev/null || ollama serve &
        sleep 2
    fi

    log_info "下载默认模型 (glm4)..."
    ollama pull glm4:latest 2>/dev/null || log_warn "模型下载失败，请手动运行: ollama pull glm4"

    log_ok "Ollama 配置完成"
}

# 初始化数据库
init_database() {
    log_info "初始化数据库..."

    mkdir -p data logs

    source "${VENV_DIR:-.venv}/bin/activate"

    python -c "
import sqlite3
import os

db_path = 'data/javis_db_agent.db'
if not os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.close()
    print(f'Created: {db_path}')

audit_path = 'data/audit.db'
if not os.path.exists(audit_path):
    conn = sqlite3.connect(audit_path)
    conn.close()
    print(f'Created: {audit_path}')

print('Database initialization complete')
"

    log_ok "数据库初始化完成"
}

# 配置 systemd 服务
install_systemd() {
    # 仅限 Linux
    local os_type=$(uname -s | tr '[:upper:]' '[:lower:]')
    if [ "$os_type" = "darwin" ]; then
        log_error "systemd 服务仅支持 Linux，不支持 macOS"
        return 1
    fi
    
    log_info "配置 systemd 服务..."

    local service_file="javis-agent.service"
    local unit_dir="/etc/systemd/system"

    if [ ! -f "$service_file" ]; then
        log_error "服务文件不存在: $service_file"
        return 1
    fi

    sudo cp "$service_file" "$unit_dir/"
    sudo chmod 644 "$unit_dir/$service_file"
    sudo systemctl daemon-reload
    sudo systemctl enable javis-agent.service

    log_ok "systemd 服务已安装并设置为开机自启"
    log_info "启动服务: sudo systemctl start javis-agent"
    log_info "查看日志: sudo journalctl -u javis-agent -f"
}

# 创建 .env 文件
create_env_file() {
    if [ -f ".env" ]; then
        log_warn ".env 文件已存在，跳过创建"
        return 0
    fi

    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_ok ".env 文件已创建，请编辑配置"
    fi
}

# 主菜单
show_menu() {
    local os_info=$1
    local os_type=$(echo $os_info | cut -d'|' -f1)
    local distrib_id=$(echo $os_info | cut -d'|' -f2)
    local distrib_version=$(echo $os_info | cut -d'|' -f3)

    echo ""
    echo "================================================"
    echo "      Javis-DB-Agent 安装向导"
    echo "================================================"
    echo ""
    echo "检测到环境:"
    if [ "$os_type" = "darwin" ]; then
        echo "  操作系统: macOS"
    else
        echo "  操作系统: $distrib_id $distrib_version"
    fi
    echo ""
    echo "请选择安装选项:"
    echo ""
    echo "  1) 全自动安装 (推荐)"
    echo "  2) 仅安装系统依赖"
    echo "  3) 仅安装 Python 依赖"
    echo "  4) 配置 Ollama"
    echo "  5) 初始化数据库"
    echo "  6) 安装 systemd 服务 (Linux)"
    echo "  7) 查看安装状态"
    echo "  0) 退出"
    echo ""
    echo -n "请输入选项 [0-7]: "
}

# 主函数
main() {
    local os_info=$(detect_os)
    local os_type=$(echo $os_info | cut -d'|' -f1)
    local distrib_id=$(echo $os_info | cut -d'|' -f2)
    local distrib_version=$(echo $os_info | cut -d'|' -f3)
    local python_cmd="python3"
    local need_manual_steps=false

    echo ""
    echo "================================================"
    echo "  Javis-DB-Agent 跨平台安装脚本 v1.3.1"
    echo "  支持: Ubuntu 22+, CentOS 7+, RHEL 7+, macOS"
    echo "================================================"
    echo ""

    # 解析命令行参数
    case "${1:-}" in
        --auto|--全自动)
            log_info "开始全自动安装..."
            need_manual_steps=false
            ;;
        --ubuntu)
            log_info "Ubuntu 安装模式..."
            distrib_id="ubuntu"
            ;;
        --centos)
            log_info "CentOS/RHEL 安装模式..."
            distrib_id="centos"
            ;;
        --macos)
            log_info "macOS 安装模式..."
            os_type="darwin"
            ;;
        --help|-h)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  --auto, --全自动    全自动安装"
            echo "  --ubuntu            Ubuntu/Debian 安装"
            echo "  --centos            CentOS/RHEL 安装"
            echo "  --macos             macOS 安装"
            echo "  --help, -h          显示此帮助"
            exit 0
            ;;
        "")
            # 交互模式
            ;;
        *)
            log_error "未知选项: $1"
            exit 1
            ;;
    esac

    # 检查 Python
    log_info "检查 Python 版本..."
    if ! check_python "$python_cmd"; then
        # 尝试找 Python 3.11
        for cmd in python3.11 python3.10 python3.9; do
            if check_python "$cmd"; then
                python_cmd="$cmd"
                break
            fi
        done
    fi

    # 根据操作系统安装系统依赖
    if [ "$os_type" = "darwin" ]; then
        install_macos_deps || need_manual_steps=true
    elif [ "$distrib_id" = "ubuntu" ] || [ "$distrib_id" = "debian" ]; then
        install_ubuntu_deps
    elif [ "$distrib_id" = "centos" ] || [ "$distrib_id" = "rhel" ]; then
        if [[ "$distrib_version" == 7* ]]; then
            install_centos7_deps || need_manual_steps=true
        else
            install_centos8_deps
        fi
    else
        log_error "不支持的操作系统"
        exit 1
    fi

    # 创建虚拟环境
    create_venv "$python_cmd"

    # 安装 Python 依赖
    install_python_deps

    # 配置 Ollama
    setup_ollama

    # 初始化数据库
    init_database

    # 创建 .env 文件
    create_env_file

    echo ""
    echo "================================================"
    if [ "$need_manual_steps" = true ]; then
        log_warn "安装完成，但有部分步骤需要手动完成"
    else
        log_ok "安装完成！"
    fi
    echo "================================================"
    echo ""
    echo "下一步:"
    echo "  1. 激活虚拟环境: source .venv/bin/activate"
    echo "  2. 配置 .env 文件: vim .env"
    echo "  3. 启动服务: make start"
    echo "  4. 或使用 Docker: make docker"
    echo ""
}

# 运行
main "$@"
