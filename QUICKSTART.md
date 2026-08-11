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
