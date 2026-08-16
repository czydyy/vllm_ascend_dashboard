# vLLM Ascend 社区看板

> 为 vLLM Ascend 项目提供 CI 状态、模型看板、性能指标的可视化展示

## 📋 项目简介

vLLM Ascend 社区看板是一个面向 vLLM Ascend 项目的信息汇聚和处理平台，提供：

- **CI 看板**：展示夜间测试、性能测试的运行状态和趋势
- **模型看板**：各大模型的功能验证报告
- **性能看板**：吞吐量、延迟、显存占用等性能指标

## 🏗️ 项目结构

```
vllm-ascend-dashboard/
├── backend/              # 后端代码根目录；按可独立运行的角色拆分
│   ├── api/              # HTTP 查询与控制面（FastAPI）
│   ├── collector/        # 数据采集进程（python -m collector）
│   ├── scheduler/        # 定时调度进程（python -m scheduler）
│   ├── reporting/        # 报告领域服务
│   ├── failure_analysis/ # 失败分析领域服务
│   ├── model_sync/       # 模型同步领域服务
│   ├── pr_pipeline/      # PR 流水线领域服务
│   ├── test_board/       # 测试看板领域服务
│   ├── support_matrix/   # 支持矩阵领域服务
│   ├── contracts/        # API/事件契约
│   ├── infrastructure/  # 数据库、客户端、存储等基础设施适配器
│   ├── tooling/          # 无业务归属的解析、分析、渲染工具
│   └── pyproject.toml
├── database/              # MySQL 迁移与数据库工具
├── deploy/                # Compose、Nginx、配置模板
├── operations/            # development / production / cluster 运维入口
├── frontend/              # 前端服务 (React + TypeScript)
│   ├── src/
│   │   ├── components/  # 组件
│   │   ├── pages/       # 页面
│   │   ├── services/    # API 服务
│   │   ├── hooks/       # Hooks
│   │   └── types/       # 类型定义
│   ├── package.json
│   └── Dockerfile
├── docs/                 # current 有效文档，archive 历史记录
├── tests/                # 跨服务单元、集成和迁移测试
└── README.md
```

`backend` 下不再使用旧的 `app/`、`shared/` 或通用 `runner/` 目录；服务之间通过
`contracts`、数据库控制面和明确的客户端接口协作。运维脚本统一放在
`operations/`，数据库变更统一从 `database/migrations/` 进入。

## 🚀 快速开始

### 前置要求

- Python 3.11+
- Node.js 20+
- pnpm 9+
- uv 0.4+
- Docker & Docker Compose

### 开发环境启动

```bash
# 1. 克隆项目
git clone https://github.com/vllm-project/vllm-ascend-dashboard.git
cd vllm-ascend-dashboard

# 2. 配置环境变量
./dev-setup.sh
# 编辑 .env 文件，设置 GITHUB_TOKEN 等

# 3. 启动开发环境
# Windows PowerShell: .\dev-setup.ps1

# 4. 访问服务
# 前端：http://localhost:3000
# 后端 API：http://localhost:8000
# API 文档：http://localhost:8000/docs
```

## 📦 开发指南

### 后端开发

```bash
cd backend

# 安装依赖
uv sync

# 运行开发服务器
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# 运行测试
uv run pytest

# 代码检查
uv run ruff check .
uv run mypy .
```

### 前端开发

```bash
cd frontend

# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev

# 构建生产版本
pnpm build

# 代码检查
pnpm lint
```

## 📊 开发计划

| Phase | 周期 | 内容 | 状态 |
|-------|------|------|------|
| Phase 1 | 2 周 | 基础架构 + 认证系统 | 📋 待开始 |
| Phase 2 | 2 周 | CI 看板 + 数据采集 | 📋 待开始 |
| Phase 3 | 2 周 | 模型看板 + 性能看板 | 📋 待开始 |
| Phase 4 | 1 周 | 高级功能 + 优化 | 📋 待开始 |

## 🔧 技术栈

**后端**：
- FastAPI 0.100+
- SQLAlchemy 2.x
- Pydantic 2.x
- JWT 认证

**前端**：
- React 18.x
- TypeScript 5.x
- Ant Design 5.x
- Recharts 2.x

**部署**：
- Docker
- Docker Compose

## 📝 相关文档

- [需求文档](docs/requirements.md)
- [技术方案设计](docs/technical_design.md)

## 🤝 贡献指南

欢迎贡献！请查看 [贡献指南](CONTRIBUTING.md) 了解详细信息。

## 📄 许可证

Apache License 2.0
