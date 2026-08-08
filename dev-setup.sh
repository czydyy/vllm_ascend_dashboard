#!/bin/bash
# ============================================================
# vLLM Ascend Dashboard - 本地开发环境一键搭建脚本
# ============================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

echo ""
echo "============================================================"
echo " vLLM Ascend Dashboard - 本地开发环境搭建"
echo "============================================================"
echo ""

# ── 0. 检查前置依赖 ──
echo "--- 检查依赖 ---"
command -v node   >/dev/null 2>&1 || err "需要 Node.js 20+"
command -v pnpm   >/dev/null 2>&1 || err "需要 pnpm"
command -v docker >/dev/null 2>&1 || err "需要 Docker Desktop"
command -v python >/dev/null 2>&1 || err "需要 Python 3.11+"
log "依赖检查通过"

# ── 1. 创建 .env ──
echo ""
echo "--- 配置环境变量 ---"
if [ ! -f .env ]; then
    echo "请粘贴 GITHUB_TOKEN（输入后按回车）："
    read -r GITHUB_TOKEN
    cat > .env << EOF
GITHUB_TOKEN=${GITHUB_TOKEN}
GITHUB_OWNER=vllm-project
GITHUB_REPO=vllm-ascend
DATABASE_URL=mysql+aiomysql://dashboard:dashboard123@127.0.0.1:3308/vllm_dashboard
JWT_SECRET=local-dev-jwt-secret-123
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO
CI_SYNC_INTERVAL_MINUTES=720
REPORT_ENABLED=false
DAILY_SUMMARY_ENABLED=false
EOF
    cp .env backend/.env
    log ".env 创建完成"
else
    warn ".env 已存在，跳过"
    [ ! -f backend/.env ] && cp .env backend/.env
fi

# ── 2. 修复 Windows 换行符 ──
echo ""
echo "--- 修复换行符 ---"
if [ -f backend/docker-entrypoint.sh ]; then
    sed -i 's/\r$//' backend/docker-entrypoint.sh 2>/dev/null || true
fi
log "换行符修复完成"

# ── 3. 构建 + 启动 Docker ──
echo ""
echo "--- 构建并启动后端 (Docker) ---"

# 创建数据目录
mkdir -p backend/data backend/logs

docker build -t vllm-dashboard-backend -f backend/Dockerfile.prod backend
docker rm -f vllm-backend-dev 2>/dev/null || true

DOCKER_RUN="docker run"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    # Git Bash 路径转换保护
    export MSYS_NO_PATHCONV=1
fi

docker run -d --name vllm-backend-dev \
  -p 8000:8000 \
  -v vllm_backend_data:/app/data \
  --env-file .env \
  --network vllm-dev-net \
  --entrypoint "" \
  vllm-dashboard-backend \
  /opt/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

sleep 5
docker logs vllm-backend-dev --tail 3
log "后端启动完成: http://localhost:8000"

# ── 4. 创建管理员 ──
echo ""
echo "--- 创建管理员账号（通过 API） ---"
sleep 2
ADMIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","email":"admin@local.dev"}')
if echo "$ADMIN_RESPONSE" | grep -q "success\|created\|已存在\|exists\|already"; then
    log "管理员: admin / admin123"
else
    warn "管理员创建可能失败（如已存在则忽略）: $ADMIN_RESPONSE"
fi

# ── 5. 安装前端依赖 ──
echo ""
echo "--- 安装前端依赖 ---"
cd frontend
pnpm install --silent 2>/dev/null || pnpm install
cd ..

# ── 6. 完成 ──
echo ""
echo "============================================================"
echo " 环境搭建完成！"
echo "============================================================"
echo ""
echo " 启动前端:  cd frontend && pnpm dev"
echo " 后端 API:  http://localhost:8000/docs"
echo " 前端页面:  http://localhost:3000"
echo " 管理员:    admin / admin123"
echo ""
echo " 停止:      docker stop vllm-backend-dev"
echo " 重启:      docker restart vllm-backend-dev"
echo ""
