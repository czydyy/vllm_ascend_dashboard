#!/bin/bash
set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 打印横幅
print_banner() {
    echo ""
    echo "========================================"
    echo "  vLLM Ascend Dashboard"
    echo "  一键启动脚本"
    echo "========================================"
    echo ""
}

# 检查依赖
check_dependencies() {
    log_info "检查依赖..."

    # 检查 Python (需要 3.11+)
    if ! command -v python3 &> /dev/null; then
        log_error "Python3 未安装"
        exit 1
    fi
    python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
    log_success "Python: $python_version"

    # 检查 uv
    if ! command -v uv &> /dev/null; then
        log_error "uv 未安装，请先安装：curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    log_success "uv: $(uv --version)"

    # 检查 Node.js (需要 20+)
    if ! command -v node &> /dev/null; then
        log_error "Node.js 未安装"
        exit 1
    fi
    node_version=$(node --version 2>&1)
    log_success "Node.js: $node_version"

    # 检查 pnpm
    if ! command -v pnpm &> /dev/null; then
        log_warning "pnpm 未安装，尝试使用 corepack 启用..."
        if command -v corepack &> /dev/null; then
            corepack enable
            corepack prepare pnpm@latest --activate
            log_success "pnpm: $(pnpm --version)"
        else
            log_error "请安装 pnpm: npm install -g pnpm"
            exit 1
        fi
    else
        pnpm_version=$(pnpm --version)
        log_success "pnpm: $pnpm_version"
    fi

    # 检查 Docker（可选）
    if command -v docker &> /dev/null && docker ps &> /dev/null 2>&1; then
        log_success "Docker: $(docker --version)"
        USE_DOCKER=true
    else
        log_warning "Docker 未安装或无法访问，将使用本地开发模式启动"
        USE_DOCKER=false
    fi

    echo ""
}

# 检查 .env 文件
check_env_file() {
    log_info "检查环境变量配置..."

    if [ ! -f "$BACKEND_DIR/.env" ]; then
        if [ -f "$PROJECT_ROOT/.env.example" ]; then
            log_warning ".env 文件不存在，从 .env.example 复制..."
            cp "$PROJECT_ROOT/.env.example" "$BACKEND_DIR/.env"
            log_warning "请编辑 .env 文件，设置正确的配置，特别是 GITHUB_TOKEN 和 JWT_SECRET"
        else
            log_error ".env.example 文件不存在"
            exit 1
        fi
    fi

    # 检查必需的环境变量
    if [ -f "$BACKEND_DIR/.env" ]; then
        source "$BACKEND_DIR/.env"

        if [ -z "$GITHUB_TOKEN" ] || [[ "$GITHUB_TOKEN" == *"your-"* ]]; then
            log_warning "GITHUB_TOKEN 未配置或为默认值"
            log_warning "请编辑 .env 文件，设置有效的 GitHub Token"
        fi

        if [ -z "$JWT_SECRET" ] || [[ "$JWT_SECRET" == *"your-"* ]]; then
            log_warning "JWT_SECRET 未配置或为默认值"
            log_warning "建议生成一个随机密钥：openssl rand -hex 32"
        fi
    fi

    log_success "环境变量配置检查完成"
    echo ""
}

# 初始化后端
init_backend() {
    log_info "初始化后端..."

    cd "$BACKEND_DIR"

    # 检查虚拟环境
    if [ ! -d ".venv" ]; then
        log_info "创建 uv 虚拟环境..."
        if ! uv venv; then
            log_error "创建虚拟环境失败"
            cd "$PROJECT_ROOT"
            return 1
        fi
    fi

    # 安装依赖
    log_info "安装后端依赖..."
    if ! uv sync; then
        log_error "安装依赖失败"
        cd "$PROJECT_ROOT"
        return 1
    fi

    # 创建数据库和初始管理员用户
    log_info "初始化数据库..."
    uv run python ../database/bootstrap.py || {
        log_warning "数据库初始化失败，可能已经初始化过了"
        log_warning "如果需要重新初始化，请先删除数据库文件"
    }

    cd "$PROJECT_ROOT"
    log_success "后端初始化完成"
    echo ""
    return 0
}

# 初始化前端
init_frontend() {
    log_info "初始化前端..."

    cd "$PROJECT_ROOT/frontend"

    # 检查 node_modules
    if [ ! -d "node_modules" ]; then
        log_info "安装前端依赖..."
        if ! pnpm install; then
            log_error "安装前端依赖失败"
            cd "$PROJECT_ROOT"
            return 1
        fi
    else
        log_info "检查依赖更新..."
        if ! pnpm install; then
            log_error "更新前端依赖失败"
            cd "$PROJECT_ROOT"
            return 1
        fi
    fi

    cd "$PROJECT_ROOT"
    log_success "前端初始化完成"
    echo ""
    return 0
}

# 启动后端（本地模式）
start_backend_local() {
    log_info "启动后端服务（本地模式）..."

    cd "$BACKEND_DIR"

    # 检查端口 8000 是否被占用
    if lsof -i :8000 > /dev/null 2>&1; then
        log_warning "端口 8000 被占用，尝试释放..."
        existing_pid=$(lsof -t -i :8000 2>/dev/null | head -1)
        if [ -n "$existing_pid" ]; then
            kill $existing_pid 2>/dev/null || true
            sleep 2
            if lsof -i :8000 > /dev/null 2>&1; then
                log_error "无法释放端口 8000，请手动处理"
                cd "$PROJECT_ROOT"
                return 1
            fi
            log_success "端口 8000 已释放"
        fi
    fi

    # 设置环境变量
    export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"

    # 启动后端
    uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!

    echo $BACKEND_PID > "$PROJECT_ROOT/.backend.pid"
    log_success "后端服务已启动 (PID: $BACKEND_PID)"
    log_info "API 文档：http://localhost:8000/docs"
    echo ""
}

# 启动前端（本地模式）
start_frontend_local() {
    log_info "启动前端服务（本地模式）..."

    cd "$PROJECT_ROOT/frontend"

    # 检查端口 3000 是否被占用
    if lsof -i :3000 > /dev/null 2>&1; then
        log_warning "端口 3000 被占用，尝试释放..."
        existing_pid=$(lsof -t -i :3000 2>/dev/null | head -1)
        if [ -n "$existing_pid" ]; then
            kill $existing_pid 2>/dev/null || true
            sleep 2
            if lsof -i :3000 > /dev/null 2>&1; then
                log_error "无法释放端口 3000，请手动处理"
                cd "$PROJECT_ROOT"
                return 1
            fi
            log_success "端口 3000 已释放"
        fi
    fi

    # 设置环境变量
    export VITE_API_BASE_URL="http://localhost:8000/api/v1"

    # 启动前端
    pnpm dev &
    FRONTEND_PID=$!

    echo $FRONTEND_PID > "$PROJECT_ROOT/.frontend.pid"
    log_success "前端服务已启动 (PID: $FRONTEND_PID)"
    log_info "访问地址：http://localhost:3000"
    echo ""
}

# 启动 Docker Compose
start_docker() {
    log_info "使用 Docker Compose 启动服务..."

    cd "$PROJECT_ROOT"

    # 确保 .env.production 文件存在
    if [ ! -f ".env.production" ]; then
        if [ -f ".env.production.example" ]; then
            cp .env.production.example .env.production
            log_warning "请编辑 .env.production 文件，设置生产环境配置"
        fi
    fi

    # 启动服务
    docker compose up -d

    # 等待服务启动
    log_info "等待服务启动..."
    sleep 10

    # 初始化数据库
    log_info "初始化数据库..."
    docker compose exec -T backend python scripts/init_db.py || {
        log_warning "数据库初始化失败，可能已经初始化过了"
    }

    log_success "服务已启动"
    log_info "前端：http://localhost:3000"
    log_info "后端：http://localhost:8000"
    log_info "API 文档：http://localhost:8000/docs"
    echo ""
}

# 检查服务状态
check_services() {
    log_info "检查服务状态..."
    echo ""

    # 检查后端
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_success "✅ 后端服务运行正常"
    else
        log_error "❌ 后端服务未响应"
    fi

    # 检查前端
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        log_success "✅ 前端服务运行正常"
    else
        log_error "❌ 前端服务未响应"
    fi

    echo ""
}

# 显示使用信息
show_usage() {
    echo ""
    echo "========================================"
    echo "  使用指南"
    echo "========================================"
    echo ""
    echo "  访问地址:"
    echo "    前端：http://localhost:3000"
    echo "    后端 API: http://localhost:8000"
    echo "    API 文档：http://localhost:8000/docs"
    echo ""
    echo "  默认账号:"
    echo "    用户名：admin"
    echo "    密码：admin123"
    echo ""
    echo "  停止服务:"
    if [ "$USE_DOCKER" = true ]; then
        echo "    docker compose down"
    else
        echo "    方式 1: $0 stop"
        echo "    方式 2: 手动杀死进程"
        echo "            kill \$(cat .backend.pid) \$(cat .frontend.pid) 2>/dev/null"
    fi
    echo ""
    echo "  查看日志:"
    if [ "$USE_DOCKER" = true ]; then
        echo "    docker compose logs -f"
    else
        echo "    按 Ctrl+C 查看日志"
    fi
    echo ""
    echo "========================================"
    echo ""
}

# 停止服务（本地模式）
stop_local() {
    log_info "停止本地服务..."

    if [ -f "$PROJECT_ROOT/.backend.pid" ]; then
        kill $(cat "$PROJECT_ROOT/.backend.pid") 2>/dev/null || true
        rm -f "$PROJECT_ROOT/.backend.pid"
        log_success "后端服务已停止"
    fi

    if [ -f "$PROJECT_ROOT/.frontend.pid" ]; then
        kill $(cat "$PROJECT_ROOT/.frontend.pid") 2>/dev/null || true
        rm -f "$PROJECT_ROOT/.frontend.pid"
        log_success "前端服务已停止"
    fi

    # 清理可能的残留进程
    pkill -f "uvicorn api.main:app" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true

    echo ""
}

# 主函数
main() {
    print_banner

    # 解析命令行参数
    case "${1:-start}" in
        start)
            check_dependencies
            check_env_file
            init_backend
            init_frontend

            if [ "$USE_DOCKER" = true ]; then
                start_docker
            else
                start_backend_local
                # 等待后端启动
                log_info "等待后端服务启动..."
                for i in {1..10}; do
                    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                        log_success "后端服务已就绪"
                        break
                    fi
                    sleep 1
                done
                start_frontend_local
            fi

            sleep 3
            check_services
            show_usage
            ;;

        stop)
            if [ "$USE_DOCKER" = true ]; then
                cd "$PROJECT_ROOT"
                docker compose down
                log_success "服务已停止"
            else
                stop_local
            fi
            ;;

        restart)
            $0 stop
            sleep 2
            $0 start
            ;;

        status)
            check_services
            ;;

        init)
            check_dependencies
            check_env_file
            init_backend
            init_frontend
            log_success "初始化完成"
            ;;

        backend)
            # 仅启动后端
            check_env_file
            init_backend
            start_backend_local
            ;;

        frontend)
            # 仅启动前端
            init_frontend
            start_frontend_local
            ;;

        help|--help|-h)
            echo "用法：$0 [start|stop|restart|status|init|backend|frontend|help]"
            echo ""
            echo "命令:"
            echo "  start    启动服务（默认）"
            echo "  stop     停止服务"
            echo "  restart  重启服务"
            echo "  status   查看服务状态"
            echo "  init     初始化项目"
            echo "  backend  仅启动后端"
            echo "  frontend 仅启动前端"
            echo "  help     显示帮助信息"
            echo ""
            ;;

        *)
            log_error "未知命令：$1"
            echo "使用 '$0 help' 查看帮助"
            exit 1
            ;;
    esac
}

# 捕获退出信号
cleanup() {
    log_info "正在停止服务..."
    if [ "$USE_DOCKER" != true ]; then
        stop_local
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

# 执行主函数
main "$@"
