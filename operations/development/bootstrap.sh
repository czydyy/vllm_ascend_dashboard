#!/bin/bash
set -e

echo "========================================"
echo "vLLM Ascend Dashboard 项目初始化脚本"
echo "========================================"
echo ""

# 检查 Python 版本
echo "检查 Python 版本..."
python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python 版本：$python_version"

# 检查 Node.js 版本
echo "检查 Node.js 版本..."
node_version=$(node --version 2>&1)
echo "Node.js 版本：$node_version"

# 检查 uv
echo "检查 uv..."
if ! command -v uv &> /dev/null; then
    echo "❌ uv 未安装，正在安装..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source $HOME/.local/bin/env
fi
echo "✅ uv 已安装：$(uv --version)"

# 检查 pnpm
echo "检查 pnpm..."
if ! command -v pnpm &> /dev/null; then
    echo "❌ pnpm 未安装，正在安装..."
    corepack enable
    corepack prepare pnpm@latest --activate
fi
echo "✅ pnpm 已安装：$(pnpm --version)"

echo ""
echo "========================================"
echo "初始化后端..."
echo "========================================"

cd backend

# 创建虚拟环境并安装依赖
echo "创建虚拟环境并安装依赖..."
uv sync --dev

# 安装 pre-commit
echo "安装 pre-commit..."
uv run pre-commit install

cd ..

echo ""
echo "========================================"
echo "初始化前端..."
echo "========================================"

cd frontend

# 安装依赖
echo "安装前端依赖..."
pnpm install

cd ..

echo ""
echo "========================================"
echo "创建默认数据库..."
echo "========================================"

# 创建初始管理员用户的脚本
cat > create_admin_user.py << 'EOF'
import sys
sys.path.insert(0, 'backend')

from sqlalchemy.orm import Session
from app.db.base import engine, SessionLocal
from app.models import User, Base
from app.core.security import hash_password

# 创建表
Base.metadata.create_all(bind=engine)

# 创建默认管理员用户
db = SessionLocal()
try:
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash=hash_password("admin123"),
            role="super_admin",
            is_active=True
        )
        db.add(admin)
        db.commit()
        print("✅ 默认管理员用户已创建")
        print("   用户名：admin")
        print("   密码：admin123")
    else:
        print("ℹ️  管理员用户已存在")
except Exception as e:
    print(f"❌ 创建用户失败：{e}")
    db.rollback()
finally:
    db.close()
EOF

echo "运行初始化脚本..."
cd backend
uv run python ../create_admin_user.py
cd ..
rm create_admin_user.py

echo ""
echo "========================================"
echo "✅ 项目初始化完成！"
echo "========================================"
echo ""
echo "启动开发环境："
echo "  docker-compose up -d"
echo ""
echo "访问服务："
echo "  前端：http://localhost:3000"
echo "  后端 API: http://localhost:8000"
echo "  API 文档：http://localhost:8000/docs"
echo ""
echo "默认管理员账号："
echo "  用户名：admin"
echo "  密码：admin123"
echo ""
echo "========================================"
