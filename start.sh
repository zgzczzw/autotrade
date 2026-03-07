#!/bin/bash
#
# AutoTrade 一键启动脚本 (Shell 版本)
# 同时启动后端和前端服务
#
# Usage:
#   ./start.sh
#   ./start.sh --no-backend    # 只启动前端
#   ./start.sh --no-frontend   # 只启动后端

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 打印横幅
print_banner() {
    echo -e "${CYAN}${BOLD}"
    echo "    ___       __        __            ______"
    echo "   /   | ____/ /_____ _/ /___  ____  /_  __/__  ____  __________"
    echo "  / /| |/ __  / __/ __  / __ \/ __ \  / / / _ \/ __ \/ ___/ ___/"
    echo " / ___ / /_/ / /  / /_/ / /_/ / /_/ / / / /  __/ / / / /__(__  )"
    echo "/_/  |_\__,_/_/   \__,_/\____/ .___/ /_/  \___/_/ /_/\___/____/"
    echo "                            /_/"
    echo -e "${GREEN}                    加密货币自动交易平台${NC}"
    echo ""
}

# 日志函数
log_backend() {
    echo -e "${BLUE}[后端]${NC} $1"
}

log_frontend() {
    echo -e "${YELLOW}[前端]${NC} $1"
}

log_info() {
    echo -e "${CYAN}[信息]${NC} $1"
}

log_error() {
    echo -e "${RED}[错误]${NC} $1" >&2
}

log_success() {
    echo -e "${GREEN}[成功]${NC} $1"
}

# 检查后端环境
check_backend_env() {
    if [ ! -d "backend/venv" ]; then
        log_error "后端虚拟环境不存在"
        log_info "请先运行: cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

# 检查前端环境
check_frontend_env() {
    if [ ! -d "frontend/node_modules" ]; then
        log_error "前端依赖未安装"
        log_info "请先运行: cd frontend && npm install"
        exit 1
    fi
}

# 清理函数
cleanup() {
    echo ""
    log_info "正在停止所有服务..."
    
    if [ -n "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null || true
        wait $BACKEND_PID 2>/dev/null || true
        log_info "后端服务已停止"
    fi
    
    if [ -n "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
        wait $FRONTEND_PID 2>/dev/null || true
        log_info "前端服务已停止"
    fi
    
    log_success "所有服务已停止"
    exit 0
}

# 注册信号处理
trap cleanup SIGINT SIGTERM

# 解析参数
NO_BACKEND=false
NO_FRONTEND=false
BACKEND_PORT=8000
FRONTEND_PORT=3000
HOST="0.0.0.0"

while [[ $# -gt 0 ]]; do
    case $1 in
        --no-backend)
            NO_BACKEND=true
            shift
            ;;
        --no-frontend)
            NO_FRONTEND=true
            shift
            ;;
        --backend-port)
            BACKEND_PORT="$2"
            shift 2
            ;;
        --frontend-port)
            FRONTEND_PORT="$2"
            shift 2
            ;;
        --host)
            HOST="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --no-backend          只启动前端，不启动后端"
            echo "  --no-frontend         只启动后端，不启动前端"
            echo "  --backend-port PORT   后端服务端口 (默认: 8000)"
            echo "  --frontend-port PORT  前端服务端口 (默认: 3000)"
            echo "  --host HOST           后端监听地址 (默认: 0.0.0.0)"
            echo "  -h, --help            显示帮助信息"
            exit 0
            ;;
        *)
            log_error "未知参数: $1"
            exit 1
            ;;
    esac
done

# 主程序
print_banner

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 检查环境
if [ "$NO_BACKEND" = false ]; then
    check_backend_env
fi

if [ "$NO_FRONTEND" = false ]; then
    check_frontend_env
fi

# 启动后端
if [ "$NO_BACKEND" = false ]; then
    log_info "启动后端服务..."
    
    (
        cd backend
        source venv/bin/activate
        exec python -u -m uvicorn app.main:app --reload --host "$HOST" --port "$BACKEND_PORT"
    ) &
    BACKEND_PID=$!
    
    sleep 2
    
    if kill -0 $BACKEND_PID 2>/dev/null; then
        log_success "后端服务已启动: http://localhost:$BACKEND_PORT"
    else
        log_error "后端服务启动失败"
        exit 1
    fi
fi

# 启动前端
if [ "$NO_FRONTEND" = false ]; then
    log_info "启动前端服务..."
    
    (
        cd frontend
        PORT=$FRONTEND_PORT exec npm run dev
    ) &
    FRONTEND_PID=$!
    
    sleep 3
    
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        log_success "前端服务已启动: http://localhost:$FRONTEND_PORT"
    else
        log_error "前端服务启动失败"
        cleanup
        exit 1
    fi
fi

# 打印访问信息
echo ""
echo -e "${GREEN}${BOLD}服务已启动！${NC}"
if [ "$NO_BACKEND" = false ]; then
    log_info "后端 API:   http://localhost:$BACKEND_PORT"
    log_info "API 文档:   http://localhost:$BACKEND_PORT/docs"
fi
if [ "$NO_FRONTEND" = false ]; then
    log_info "前端页面:   http://localhost:$FRONTEND_PORT"
fi
echo ""
log_info "按 Ctrl+C 停止所有服务"
echo ""

# 等待进程
if [ -n "$BACKEND_PID" ] && [ -n "$FRONTEND_PID" ]; then
    wait $BACKEND_PID $FRONTEND_PID
elif [ -n "$BACKEND_PID" ]; then
    wait $BACKEND_PID
elif [ -n "$FRONTEND_PID" ]; then
    wait $FRONTEND_PID
fi
