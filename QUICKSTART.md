# Quick Start Guide

## 一键部署 (One-Click Deployment)

### 使用部署脚本 (Recommended)

```bash
# 1. 准备环境
cp .env.production.example .env.production

# 2. 编辑配置文件，设置必要的环境变量
# - GITHUB_TOKEN
# - JWT_SECRET (使用 openssl rand -hex 32 生成)
# - MYSQL_ROOT_PASSWORD (使用 openssl rand -base64 32 生成)
# - MYSQL_PASSWORD (使用 openssl rand -base64 32 生成)

# 3. 一键部署
./deploy.sh start

# 4. 查看状态
./deploy.sh status

# 5. 查看日志
./deploy.sh logs

# 6. 备份数据
./deploy.sh backup
```

## 访问服务

- **前端界面**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **健康检查**: http://localhost:8000/health

## 常用命令

### 部署脚本命令

`./deploy.sh` 支持以下命令：

| 命令 | 说明 | 示例 |
|------|------|------|
| `start` | 使用 MySQL 数据库部署 | `./deploy.sh start` |
| `status` | 查看服务运行状态 | `./deploy.sh status` |
| `logs [服务名]` | 查看服务日志，可按服务名过滤 | `./deploy.sh logs`<br>`./deploy.sh logs backend`<br>`./deploy.sh logs mysql`<br>`./deploy.sh logs frontend` |
| `restart` | 重启所有服务 | `./deploy.sh restart` |
| `stop` | 停止所有服务 | `./deploy.sh stop` |
| `backup` | 备份数据（数据库 + 日志） | `./deploy.sh backup` |
| `rebuild` | 重新构建并重启所有服务 | `./deploy.sh rebuild` |
| `help` | 显示帮助信息 | `./deploy.sh help` |

### Docker Compose 原生命令

```bash
# 查看服务状态
docker compose -f docker-compose.prod.yml --env-file .env.production ps

# 查看日志
docker compose -f docker-compose.prod.yml --env-file .env.production logs -f

# 重启服务
docker compose -f docker-compose.prod.yml --env-file .env.production restart

# 停止服务（保留数据卷）
docker compose -f docker-compose.prod.yml --env-file .env.production down

# 停止服务并删除数据卷（危险！会丢失数据）
docker compose -f docker-compose.prod.yml --env-file .env.production down -v

# 更新应用
git pull
docker compose -f docker-compose.prod.yml --env-file .env.production --profile full up -d --build
```

### 数据备份与恢复

```bash
# 使用脚本备份（推荐）
./deploy.sh backup

# 手动备份 MySQL 数据库
docker exec vllm-dashboard-mysql mysqldump -u root -p${MYSQL_ROOT_PASSWORD} vllm_dashboard > backup/db.$(date +%Y%m%d).sql

# 恢复 MySQL 数据库
docker exec -i vllm-dashboard-mysql mysql -u root -p${MYSQL_ROOT_PASSWORD} vllm_dashboard < backup/db.sql
```

## 数据持久化

所有数据存储在 Docker 命名卷中，容器重启不会丢失：

- `backend_data`: 应用数据
- `backend_logs`: 应用日志
- `mysql_data`: MySQL 数据库文件

## 配置外挂

配置文件通过挂载方式进入容器，方便修改：

- `deploy/config/backend.env` → 后端配置
- `deploy/config/nginx.conf` → 前端 Nginx 配置
- `deploy/config/mysql.cnf` → MySQL 配置

## 故障排查

```bash
# 检查后端健康状态
curl http://localhost:8000/health

# 查看后端日志
docker compose -f docker-compose.prod.yml logs backend

# 查看前端日志
docker compose -f docker-compose.prod.yml logs frontend

# 检查数据库连接
docker compose -f docker-compose.prod.yml logs mysql
```

## 安全提示

1. **不要提交 `.env.production` 到 Git** - 已添加到 `.gitignore`
2. **使用强密码** - 使用 `openssl rand` 生成
3. **定期轮换密钥** - 定期更新 JWT_SECRET 和数据库密码
4. **启用 HTTPS** - 生产环境建议使用 SSL/TLS

详细部署文档请参考：[deploy/DEPLOYMENT.md](deploy/DEPLOYMENT.md)
