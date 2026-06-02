#!/usr/bin/env bash
# NexusAgent v4.0+ — 一键安装脚本
# 支持: Linux, macOS, WSL2
# 用法: curl -fsSL https://.../install.sh | bash

set -euo pipefail

REPO_URL="https://github.com/nexusagent/nexusagent"
INSTALL_DIR="${NEXUS_HOME:-$HOME/.nexusagent}"
PYTHON_MIN="3.10"

color_red='\033[0;31m'
color_green='\033[0;32m'
color_yellow='\033[1;33m'
color_reset='\033[0m'

log_info() { echo -e "${color_green}[INFO]${color_reset} $*"; }
log_warn() { echo -e "${color_yellow}[WARN]${color_reset} $*"; }
log_error() { echo -e "${color_red}[ERROR]${color_reset} $*"; }

check_python() {
    log_info "检查 Python 版本..."
    if command -v python3 &>/dev/null; then
        PYTHON="python3"
    elif command -v python &>/dev/null; then
        PYTHON="python"
    else
        log_error "未找到 Python。请安装 Python ${PYTHON_MIN}+"
        exit 1
    fi

    PY_VERSION=$($PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    log_info "Python 版本: $PY_VERSION"

    if [ "$($PYTHON -c "import sys; print(sys.version_info >= (3,10))")" != "True" ]; then
        log_error "需要 Python ${PYTHON_MIN}+，当前为 $PY_VERSION"
        exit 1
    fi
}

install_deps() {
    log_info "安装依赖..."
    $PYTHON -m pip install --quiet --upgrade pip
    $PYTHON -m pip install --quiet aiohttp pydantic cryptography pyyaml
    log_info "核心依赖安装完成"
}

generate_env() {
    local env_file="$INSTALL_DIR/.env"
    if [ -f "$env_file" ]; then
        log_warn ".env 文件已存在，跳过生成"
        return
    fi

    log_info "生成 .env 配置文件..."
    cat > "$env_file" <<EOF
# NexusAgent 配置文件
# 请填写以下必填项

# LLM API Key (至少配置一个)
# DEEPSEEK_API_KEY=your_key_here
# MOONSHOT_API_KEY=your_key_here
# OPENAI_API_KEY=your_key_here

# 安全主密钥 (32+ 字节, base64 编码)
# 生成命令: python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
NEXUS_MASTER_KEY=$(python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())")

# 调试模式
NEXUS_DEBUG=false
EOF
    log_info ".env 文件已生成: $env_file"
    log_warn "请编辑 .env 文件，填写你的 API Key"
}

main() {
    echo ""
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║      NexusAgent 安装程序 v4.0+           ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo ""

    check_python
    install_deps

    mkdir -p "$INSTALL_DIR"
    log_info "安装目录: $INSTALL_DIR"

    generate_env

    # 生成 nexus 命令别名
    local shell_rc=""
    if [ -n "${ZSH_VERSION:-}" ] || [ "${SHELL##*/}" = "zsh" ]; then
        shell_rc="$HOME/.zshrc"
    elif [ "${SHELL##*/}" = "bash" ]; then
        shell_rc="$HOME/.bashrc"
    fi

    if [ -n "$shell_rc" ] && [ -f "$shell_rc" ]; then
        if ! grep -q "nexusagent" "$shell_rc" 2>/dev/null; then
            echo "alias nexus-dev='cd $INSTALL_DIR && python -m nexusagent'" >> "$shell_rc"
            log_info "已添加 nexus-dev 别名到 $shell_rc"
            log_warn "请运行: source $shell_rc"
        fi
    fi

    echo ""
    echo "  ✅ NexusAgent 安装完成!"
    echo ""
    echo "  下一步:"
    echo "    1. 编辑 $INSTALL_DIR/.env 填写 API Key"
    echo "    2. 运行: nexus doctor      # 诊断环境"
    echo "    3. 运行: nexus demo weather # 运行示例"
    echo ""
}

main "$@"
