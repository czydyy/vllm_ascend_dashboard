# vLLM Ascend Dashboard 快速开始

## 本地开发

```bash
bash operations/development/bootstrap.sh
docker compose -f deploy/compose/dev/compose.yml up --build
```

停止本地环境：

```bash
docker compose -f deploy/compose/dev/compose.yml down
```

## 本地开发（前端 + 后端）

推荐直接使用仓库提供的一键启动脚本：

```powershell
.\dev-setup.ps1
```

它会启动本地前端、本地后端和本地数据库，前端访问 `http://localhost:3000`，API 文档访问
`http://localhost:8000/docs`，并自动写入一套本地演示数据。

演示账号：

```text
admin / admin123
manager / manager123
user / user123
```

如果需要手动重新写入演示数据：

```powershell
docker compose --env-file .env.local -f deploy/compose/dev/compose.yml exec -T backend python database/seed_local_demo.py
```

脚本只更新自己创建的演示记录，不会清空本地数据库。

## 生产环境

生产发布只允许通过受备份、迁移和健康检查保护的入口执行：

```bash
bash operations/production/deploy.sh
```

不要使用历史的根目录部署脚本，也不要直接运行数据库 bootstrap。数据库变更使用：

```bash
bash operations/production/migrate.sh
```

更多运行与恢复说明见 [架构与运维方案](docs/current/架构演进与运维方案.md)。
