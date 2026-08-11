# vLLM Ascend 社区看板项目技术方案设计

## 1. 系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            前端层 (React)                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │  首页    │  │ CI 看板  │  │ 模型看板 │  │ 性能看板 │  ...              │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                         API 网关层 (FastAPI)                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  认证中间件 │ 权限校验 │ 速率限制 │ CORS │ 日志记录                 │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                           业务逻辑层                                     │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                │
│  │ CI 服务  │  │模型服务  │  │性能服务  │  │ 用户服务 │                   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                              │
│  │采集服务  │  │解析服务  │  │ 通知服务 │  ...                           │
│  └──────────┘  └──────────┘  └──────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                           数据访问层                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │   MySQL/SQLite   │  │   Redis (缓存)   │  │  GitHub API      │       │
│  │   (持久化存储)    │  │   (可选)         │  │  (数据源)        │        │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 技术栈选型

| 层级 | 技术 | 版本 | 说明 |
|-----|------|------|------|
| **前端** | React | 18.x | 组件化 UI 框架 |
| | TypeScript | 5.x | 类型安全 |
| | Ant Design | 5.x | UI 组件库 |
| | Recharts | 2.x | 图表库 |
| | Axios | 1.x | HTTP 客户端 |
| | React Query | 5.x | 数据获取和缓存 |
| **后端** | Python | 3.9+ | 后端语言 |
| | FastAPI | 0.100+ | Web 框架 |
| | SQLAlchemy | 2.x | ORM 框架 |
| | Pydantic | 2.x | 数据验证 |
| | Python-Jose | 4.x | JWT 认证 |
| | Passlib | 1.x | 密码加密 |
| | HTTPX | 0.24+ | 异步 HTTP 客户端 |
| **数据库** | MySQL | 8.0+ | 生产环境 |
| | SQLite | 3.x | 测试/开发环境 |
| **部署** | Docker | 24.x | 容器化 |
| | Docker Compose | 2.x | 编排工具 |

### 1.3 系统组件

```
vllm-ascend-dashboard/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/               # API 路由
│   │   │   ├── v1/
│   │   │   │   ├── ci.py
│   │   │   │   ├── models.py
│   │   │   │   ├── performance.py
│   │   │   │   ├── auth.py
│   │   │   │   └── users.py
│   │   │   └── deps.py       # 依赖注入
│   │   ├── core/             # 核心配置
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── exceptions.py
│   │   ├── db/               # 数据库相关
│   │   │   ├── session.py    # 数据库会话
│   │   │   └── base.py       # 基类
│   │   ├── models/           # 数据模型
│   │   │   ├── user.py
│   │   │   ├── ci_result.py
│   │   │   ├── model_report.py
│   │   │   └── performance_data.py
│   │   ├── schemas/          # Pydantic 模式
│   │   │   ├── user.py
│   │   │   ├── ci.py
│   │   │   ├── model.py
│   │   │   └── performance.py
│   │   ├── services/         # 业务逻辑
│   │   │   ├── github_client.py
│   │   │   ├── ci_collector.py
│   │   │   ├── model_manager.py
│   │   │   └── performance_parser.py
│   │   └── main.py           # 应用入口
│   ├── tests/                # 测试
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                  # 前端服务
│   ├── src/
│   │   ├── components/       # 通用组件
│   │   ├── pages/           # 页面组件
│   │   ├── services/        # API 服务
│   │   ├── hooks/           # 自定义 Hooks
│   │   ├── types/           # TypeScript 类型
│   │   ├── utils/           # 工具函数
│   │   └── App.tsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## 2. 数据库设计

### 2.1 ER 图

```
┌─────────────────┐       ┌─────────────────┐
│     users       │       │   model_configs │
├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │
│ username        │       │ model_name      │
│ password_hash   │       │ series          │
│ role            │       │ config_yaml     │
│ created_at      │       │ status          │
│ updated_at      │       │ created_by (FK) │
└─────────────────┘       │ created_at      │
                          │ updated_at      │
                          └─────────────────┘
┌─────────────────┐                 │
│  ci_results     │                 │
├─────────────────┤                 │
│ id (PK)         │                 ▼
│ workflow_name   │       ┌─────────────────┐
│ run_id          │       │  model_reports  │
│ job_name        │       ├─────────────────┤
│ status          │       │ id (PK)         │
│ conclusion      │       │ model_config_id │
│ started_at      │       │ report_json     │
│ duration        │       │ pass_fail       │
│ data            │       │ metrics         │
│ created_at      │       │ known_issues    │
└─────────────────┘       │ created_at      │
                          └─────────────────┘
┌─────────────────┐
│ performance_data│
├─────────────────┤
│ id (PK)         │
│ test_name       │
│ hardware        │
│ model_name      │
│ vllm_version    │
│ vllm_commit     │
│ test_type       │
│ metrics_json    │
│ timestamp       │
│ created_at      │
└─────────────────┘
```

### 2.2 数据表结构

#### 2.2.1 用户表 (users)

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',  -- 'admin', 'super_admin', 'user'
    email VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);
```

#### 2.2.2 模型配置表 (model_configs)

```sql
CREATE TABLE model_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_name VARCHAR(200) NOT NULL,
    series VARCHAR(50),  -- 'Qwen', 'Llama', 'DeepSeek', 'Other'
    config_yaml TEXT,
    status VARCHAR(20) DEFAULT 'active',  -- 'active', 'inactive'
    created_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_model_configs_name ON model_configs(model_name);
CREATE INDEX idx_model_configs_series ON model_configs(series);
```

#### 2.2.3 模型看板报告表 (model_reports)

```sql
CREATE TABLE model_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_config_id INTEGER REFERENCES model_configs(id),
    workflow_run_id INTEGER,
    report_json TEXT NOT NULL,  -- 完整的报告 JSON
    pass_fail VARCHAR(10),  -- 'pass', 'fail'
    metrics_json TEXT,  -- 关键指标提取
    known_issues TEXT,  -- 已知问题
    github_artifact_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_model_reports_config_id ON model_reports(model_config_id);
CREATE INDEX idx_model_reports_created_at ON model_reports(created_at);
```

#### 2.2.4 CI 结果表 (ci_results)

```sql
CREATE TABLE ci_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name VARCHAR(100) NOT NULL,
    run_id INTEGER NOT NULL,
    job_name VARCHAR(200),
    status VARCHAR(20),  -- 'completed', 'in_progress', 'queued'
    conclusion VARCHAR(20),  -- 'success', 'failure', 'cancelled'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    hardware VARCHAR(20),  -- 'A2', 'A3'
    data TEXT,  -- 完整的 workflow run 数据
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_ci_results_workflow ON ci_results(workflow_name);
CREATE INDEX idx_ci_results_run_id ON ci_results(run_id);
CREATE INDEX idx_ci_results_status ON ci_results(status);
CREATE INDEX idx_ci_results_created_at ON ci_results(created_at);
```

#### 2.2.5 性能数据表 (performance_data)

```sql
CREATE TABLE performance_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    test_name VARCHAR(200) NOT NULL,
    hardware VARCHAR(20) NOT NULL,  -- 'A2', 'A3'
    model_name VARCHAR(200) NOT NULL,
    vllm_version VARCHAR(50),
    vllm_commit VARCHAR(40),
    vllm_ascend_commit VARCHAR(40),
    test_type VARCHAR(20),  -- 'latency', 'throughput', 'serving'
    metrics_json TEXT NOT NULL,  -- 完整的测试结果 JSON
    timestamp TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_perf_test_name ON performance_data(test_name);
CREATE INDEX idx_perf_hardware ON performance_data(hardware);
CREATE INDEX idx_perf_model ON performance_data(model_name);
CREATE INDEX idx_perf_version ON performance_data(vllm_version);
CREATE INDEX idx_perf_timestamp ON performance_data(timestamp);
```

---

## 3. API 设计

### 3.1 API 规范

- **基础路径**: `/api/v1`
- **认证方式**: Bearer Token (JWT)
- **数据格式**: JSON
- **错误格式**: 
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误信息",
    "details": {}
  }
}
```

### 3.2 认证接口

| 方法 | 路径 | 说明 | 认证 |
|-----|------|------|------|
| POST | `/api/v1/auth/login` | 用户登录 | ❌ |
| POST | `/api/v1/auth/logout` | 用户登出 | ✅ |
| POST | `/api/v1/auth/refresh` | 刷新 Token | ✅ |
| GET | `/api/v1/auth/me` | 获取当前用户信息 | ✅ |

**请求示例 - 登录**:
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "password123"
}
```

**响应示例**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 86400
}
```

### 3.3 CI 数据接口

| 方法 | 路径 | 说明 | 认证 |
|-----|------|------|------|
| GET | `/api/v1/ci/workflows` | 获取 workflow 列表 | ❌ |
| GET | `/api/v1/ci/workflows/{name}/runs` | 获取 workflow 运行历史 | ❌ |
| GET | `/api/v1/ci/runs/{run_id}` | 获取单次运行详情 | ❌ |
| GET | `/api/v1/ci/stats` | 获取 CI 统计数据 | ❌ |
| GET | `/api/v1/ci/trends` | 获取 CI 趋势数据 | ❌ |
| POST | `/api/v1/ci/sync` | 手动触发数据同步 | ✅ (admin) |

**响应示例 - CI 统计**:
```json
{
  "workflows": [
    {
      "name": "Nightly-A2",
      "total_runs": 365,
      "success_rate": 0.92,
      "avg_duration_seconds": 5400,
      "last_7_days": {
        "runs": 7,
        "success_rate": 0.86
      }
    }
  ]
}
```

### 3.4 模型管理接口

| 方法 | 路径 | 说明 | 认证 |
|-----|------|------|------|
| GET | `/api/v1/models` | 获取模型列表 | ❌ |
| GET | `/api/v1/models/{id}` | 获取模型详情 | ❌ |
| POST | `/api/v1/models` | 创建模型配置 | ✅ (admin) |
| PUT | `/api/v1/models/{id}` | 更新模型配置 | ✅ (admin) |
| DELETE | `/api/v1/models/{id}` | 删除模型配置 | ✅ (admin) |
| GET | `/api/v1/models/{id}/reports` | 获取模型报告列表 | ❌ |
| GET | `/api/v1/models/{id}/reports/latest` | 获取最新报告 | ❌ |

**请求示例 - 创建模型**:
```http
POST /api/v1/models
Content-Type: application/json
Authorization: Bearer {token}

{
  "model_name": "Qwen/Qwen3-8B",
  "series": "Qwen",
  "config_yaml": "model_name: \"Qwen/Qwen3-8B\"...\n"
}
```

### 3.5 性能数据接口

| 方法 | 路径 | 说明 | 认证 |
|-----|------|------|------|
| GET | `/api/v1/performance` | 获取性能数据列表 | ❌ |
| GET | `/api/v1/performance/{id}` | 获取单次测试详情 | ❌ |
| GET | `/api/v1/performance/trends` | 获取性能趋势 | ❌ |
| GET | `/api/v1/performance/compare` | 性能对比 | ❌ |
| POST | `/api/v1/performance/upload` | 手动上传性能数据 | ✅ (admin) |
| POST | `/api/v1/performance/sync` | 触发数据同步 | ✅ (admin) |

**请求示例 - 性能对比**:
```http
GET /api/v1/performance/compare?
  model=Qwen/Qwen3-8B&
  hardware=A2&
  baseline_date=2026-03-01&
  compare_date=2026-03-23
```

**响应示例**:
```json
{
  "baseline": {
    "date": "2026-03-01",
    "throughput": 1200.5,
    "ttft_median_ms": 45.0
  },
  "current": {
    "date": "2026-03-23",
    "throughput": 1250.5,
    "ttft_median_ms": 42.0
  },
  "change": {
    "throughput": "+4.2%",
    "ttft_median_ms": "-6.7%"
  }
}
```

### 3.6 用户管理接口

| 方法 | 路径 | 说明 | 认证 |
|-----|------|------|------|
| GET | `/api/v1/users` | 获取用户列表 | ✅ (super_admin) |
| GET | `/api/v1/users/{id}` | 获取用户详情 | ✅ (admin) |
| POST | `/api/v1/users` | 创建用户 | ✅ (super_admin) |
| PUT | `/api/v1/users/{id}` | 更新用户信息 | ✅ (admin) |
| DELETE | `/api/v1/users/{id}` | 删除用户 | ✅ (super_admin) |

---

## 4. 核心模块设计

### 4.1 GitHub API 客户端

```python
# backend/app/services/github_client.py

from typing import Optional
import httpx
from datetime import datetime

class GitHubClient:
    """GitHub API 客户端，处理速率限制和重试"""
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self, token: str):
        self.token = token
        self.client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"
            },
            timeout=30.0
        )
        self.rate_limit_remaining = 5000
    
    async def get_workflow_runs(
        self,
        owner: str,
        repo: str,
        workflow_id_or_name: str,
        status: Optional[str] = None,
        per_page: int = 100
    ) -> list[dict]:
        """获取 workflow 运行历史
        
        Args:
            owner: GitHub 组织名，如 "vllm-project"
            repo: 仓库名，如 "vllm-ascend"
            workflow_id_or_name: workflow ID 或文件名，如 "schedule_nightly_test_a2.yaml"
            status: 状态过滤，如 "success", "failure", "completed"
            per_page: 每页数量，最大 100
        
        Returns:
            workflow runs 列表
        """
        params = {"per_page": per_page}
        if status:
            params["status"] = status

        response = await self.client.get(
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id_or_name}/runs",
            params=params
        )
        self._update_rate_limit(response)
        response.raise_for_status()
        return response.json()["workflow_runs"]
    
    async def get_artifact(self, owner: str, repo: str, artifact_id: int) -> bytes:
        """下载 artifact 文件"""
        # 获取 artifact 下载 URL
        resp = await self.client.get(
            f"/repos/{owner}/{repo}/actions/artifacts/{artifact_id}/zip"
        )
        resp.raise_for_status()
        return resp.content
    
    def _update_rate_limit(self, response: httpx.Response):
        """更新速率限制信息"""
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining:
            self.rate_limit_remaining = int(remaining)
    
    async def check_rate_limit(self) -> dict:
        """检查当前速率限制状态"""
        response = await self.client.get("/rate_limit")
        return response.json()
```

### 4.2 CI 数据采集服务

```python
# backend/app/services/ci_collector.py

from datetime import datetime, timedelta, timezone
from typing import List
import json
import logging
from app.services.github_client import GitHubClient
from app.models.ci_result import CIResult
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

class CICollector:
    """CI 数据采集服务"""

    def __init__(self, github_client: GitHubClient):
        self.github = github_client
        self.owner = "vllm-project"
        self.repo = "vllm-ascend"

    async def collect_workflow_runs(
        self,
        workflow_files: List[str],
        days_back: int = 7
    ) -> int:
        """采集指定 workflow 的运行数据

        从 GitHub Actions API 获取 workflow runs 数据
        不依赖源码，只通过 API 获取公开信息
        
        Args:
            workflow_files: workflow 文件名列表，如 ["schedule_nightly_test_a2.yaml", ...]
            days_back: 获取多少天的数据，默认 7 天
        
        Returns:
            新增的记录数
        """
        collected = 0
        since = datetime.now(timezone.utc) - timedelta(days=days_back)

        # 批量收集所有 workflow 的 runs
        all_runs = []
        for workflow_file in workflow_files:
            try:
                runs = await self.github.get_workflow_runs(
                    self.owner,
                    self.repo,
                    workflow_file,  # 使用文件名作为 workflow_id
                    per_page=100
                )
                all_runs.extend(runs)
            except Exception as e:
                logger.error(f"Failed to fetch workflow {workflow_file}: {e}")

        # 保存到数据库
        session = SessionLocal()
        try:
            for run in all_runs:
                created_at = datetime.fromisoformat(
                    run["created_at"].replace("Z", "+00:00")
                )
                if created_at < since:
                    continue

                # 检查是否已存在
                existing = session.query(CIResult).filter(
                    CIResult.run_id == run["id"]
                ).first()
                if existing:
                    # 更新现有记录
                    self._update_ci_result(existing, run)
                else:
                    # 创建新记录
                    ci_result = self._create_ci_result(run)
                    session.add(ci_result)
                    collected += 1

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save CI results: {e}")
            raise
        finally:
            session.close()

        return collected

    def _create_ci_result(self, run: dict) -> CIResult:
        """创建 CI 结果对象
        
        从 GitHub API 返回的 workflow run 数据中提取信息：
        - workflow_id: 数字 ID，如 12345
        - path: workflow 文件路径，如 ".github/workflows/schedule_nightly_test_a2.yaml"
        - name: workflow 显示名称，如 "Nightly-A2"
        """
        # 从 workflow path 中提取 workflow 文件名
        # 例如：".github/workflows/schedule_nightly_test_a2.yaml" -> "schedule_nightly_test_a2.yaml"
        workflow_path = run.get("path", "")
        workflow_filename = workflow_path.split("/")[-1] if workflow_path else ""
        
        # 从文件名中提取硬件信息（A2/A3）
        hardware = self._extract_hardware_from_filename(workflow_filename)
        
        return CIResult(
            workflow_name=run.get("name", str(run.get("workflow_id", ""))),  # 使用显示名称
            run_id=run["id"],
            job_name=run.get("name", ""),
            status=run["status"],
            conclusion=run.get("conclusion"),
            started_at=run["created_at"],
            completed_at=run.get("updated_at"),
            duration_seconds=self._calculate_duration(run),
            hardware=hardware,
            data=json.dumps(run)
        )

    def _update_ci_result(self, result: CIResult, run: dict):
        """更新 CI 结果对象"""
        result.status = run["status"]
        result.conclusion = run.get("conclusion")
        result.completed_at = run.get("updated_at")
        result.duration_seconds = self._calculate_duration(run)
        result.data = json.dumps(run)
        # 更新硬件信息
        workflow_path = run.get("path", "")
        workflow_filename = workflow_path.split("/")[-1] if workflow_path else ""
        result.hardware = self._extract_hardware_from_filename(workflow_filename)

    def _calculate_duration(self, run: dict) -> int:
        """计算运行时长（秒）"""
        if not run.get("updated_at") or not run.get("created_at"):
            return 0
        start = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        return int((end - start).total_seconds())

    def _extract_hardware_from_filename(self, filename: str) -> str:
        """从 workflow 文件名中提取硬件信息
        
        根据 vllm-ascend 项目的 workflow 命名规范：
        - schedule_nightly_test_a2.yaml -> A2
        - schedule_nightly_test_a3.yaml -> A3
        - schedule_test_benchmarks.yaml -> 需要根据 job 配置判断
        """
        if not filename:
            return "unknown"
            
        filename_lower = filename.lower()
        
        # 根据文件名关键词识别硬件
        if "a2" in filename_lower and "nightly" in filename_lower:
            return "A2"
        elif "a3" in filename_lower and "nightly" in filename_lower:
            return "A3"
        elif "benchmarks" in filename_lower or "performance" in filename_lower:
            # 性能测试需要根据实际 job 判断，默认返回 A2
            return "A2"
        
        return "unknown"
```

### 4.3 性能数据解析服务

```python
# backend/app/services/performance_parser.py

import json
import yaml
import logging
from datetime import datetime
from typing import Optional
from app.models.performance_data import PerformanceData

logger = logging.getLogger(__name__)

class PerformanceParser:
    """性能数据解析服务"""

    def parse_json_result(
        self,
        json_data: dict,
        hardware: str,
        timestamp: Optional[datetime] = None
    ) -> PerformanceData:
        """解析 vllm bench 输出的 JSON 结果"""
        if timestamp is None:
            timestamp = datetime.utcnow()
            
        return PerformanceData(
            test_name=json_data.get("test_name", "unknown"),
            hardware=hardware,
            model_name=json_data.get("model", "unknown"),
            vllm_version=json_data.get("vllm_version", ""),
            vllm_commit=json_data.get("vllm_commit", ""),
            vllm_ascend_commit=json_data.get("vllm_ascend_commit", ""),
            test_type=self._infer_test_type(json_data),
            metrics_json=json.dumps(json_data.get("results", {})),
            timestamp=timestamp
        )

    def parse_yaml_upload(
        self,
        yaml_content: str,
        hardware: str
    ) -> PerformanceData:
        """解析手动上传的 YAML 格式性能数据"""
        data = yaml.safe_load(yaml_content)
        timestamp_str = data.get("timestamp", datetime.utcnow().isoformat())
        return PerformanceData(
            test_name=data.get("test_name", "unknown"),
            hardware=hardware,
            model_name=data.get("model", "unknown"),
            vllm_version=data.get("vllm_version", ""),
            vllm_commit=data.get("vllm_commit", ""),
            test_type=data.get("test_type", "unknown"),
            metrics_json=json.dumps(data.get("metrics", {})),
            timestamp=datetime.fromisoformat(timestamp_str)
        )

    def _infer_test_type(self, json_data: dict) -> str:
        """从测试结果推断测试类型"""
        test_name = json_data.get("test_name", "").lower()
        if "latency" in test_name:
            return "latency"
        elif "throughput" in test_name:
            return "throughput"
        elif "serving" in test_name:
            return "serving"
        else:
            return "unknown"
```

### 4.4 定时同步任务

```python
# backend/app/services/scheduler.py

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.ci_collector import CICollector
from app.services.github_client import GitHubClient
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class DataSyncScheduler:
    """数据同步定时任务调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.github_client = GitHubClient(settings.GITHUB_TOKEN)
        self.ci_collector = CICollector(self.github_client)

    def start(self):
        """启动调度器"""
        # CI 数据同步 - 每 10 分钟
        self.scheduler.add_job(
            self.sync_ci_data,
            CronTrigger(minute="*/10"),
            id="ci_sync",
            name="Sync CI Data"
        )

        # 性能数据同步 - 每天凌晨 1 点
        self.scheduler.add_job(
            self.sync_performance_data,
            CronTrigger(hour=1, minute=0),
            id="perf_sync",
            name="Sync Performance Data"
        )

        self.scheduler.start()
        logger.info("DataSyncScheduler started")

    def stop(self):
        """停止调度器"""
        self.scheduler.shutdown()
        logger.info("DataSyncScheduler stopped")

    async def sync_ci_data(self):
        """同步 CI 数据"""
        try:
            # workflow 文件名列表（从 vllm-ascend 项目的命名规范学习）
            workflow_files = [
                "schedule_nightly_test_a2.yaml",    # Nightly-A2
                "schedule_nightly_test_a3.yaml",    # Nightly-A3
                "schedule_test_benchmarks.yaml"     # Performance Schedule Test
            ]
            await self.ci_collector.collect_workflow_runs(workflow_files, days_back=1)
            logger.info(f"CI data sync completed")
        except Exception as e:
            logger.error(f"CI data sync failed: {e}")

    async def sync_performance_data(self):
        """同步性能数据
        
        性能数据同步方式：
        1. 从 GitHub Actions artifacts 下载 benchmarks/results/*.json
        2. 解析 JSON 文件，提取性能指标
        3. 保存到 performance_data 表
        
        注意：性能测试 workflow 是 schedule_test_benchmarks.yaml
        artifacts 名称格式：benchmark-performance-{version}-report
        """
        try:
            # 从 GitHub artifacts 下载并解析性能数据
            logger.info("Performance data sync started")
            # 实现步骤：
            # 1. 调用 GitHub API 获取最新的 artifacts 列表
            # 2. 下载 benchmark-performance-*.json 文件
            # 3. 调用 PerformanceParser 解析 JSON
            # 4. 保存到数据库
        except Exception as e:
            logger.error(f"Performance data sync failed: {e}")

    async def trigger_manual_sync(self, sync_type: str):
        """手动触发同步"""
        if sync_type == "ci":
            await self.sync_ci_data()
        elif sync_type == "performance":
            await self.sync_performance_data()
        else:
            raise ValueError(f"Unknown sync type: {sync_type}")
```

---

## 5. 前端设计

### 5.1 页面结构

```
src/
├── components/
│   ├── common/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Loading.tsx
│   │   └── ErrorBoundary.tsx
│   ├── charts/
│   │   ├── LineChart.tsx
│   │   ├── BarChart.tsx
│   │   └── TrendChart.tsx
│   └── tables/
│       ├── CITable.tsx
│       ├── ModelTable.tsx
│       └── PerformanceTable.tsx
├── pages/
│   ├── Dashboard.tsx          # 首页
│   ├── CIBoard.tsx            # CI 看板
│   ├── ModelDashboard.tsx     # 模型看板
│   ├── PerformanceBoard.tsx   # 性能看板
│   ├── Admin.tsx              # 管理后台
│   └── Login.tsx              # 登录页
├── services/
│   ├── api.ts
│   ├── ci.ts
│   ├── models.ts
│   └── performance.ts
├── hooks/
│   ├── useCI.ts
│   ├── useModels.ts
│   └── usePerformance.ts
└── types/
    ├── ci.ts
    ├── model.ts
    └── performance.ts
```

### 5.2 核心组件示例

#### CI 看板组件

```tsx
// src/pages/CIBoard.tsx

import React from 'react';
import { useCI } from '../hooks/useCI';
import { CITable } from '../components/tables/CITable';
import { TrendChart } from '../components/charts/TrendChart';
import { SummaryCard } from '../components/common/SummaryCard';
import { RefreshButton } from '../components/common/RefreshButton';
import { formatDuration } from '../utils/time';

export const CIBoard: React.FC = () => {
  const { workflows, trends, loading, refresh } = useCI();

  return (
    <div className="ci-board">
      <div className="header">
        <h1>CI 看板</h1>
        <RefreshButton onClick={refresh} loading={loading} />
      </div>

      <div className="summary-cards">
        <SummaryCard
          title="今日运行"
          value={workflows.todayRuns}
          trend={workflows.todayTrend}
        />
        <SummaryCard
          title="通过率"
          value={`${workflows.successRate}%`}
          trend={workflows.rateTrend}
        />
        <SummaryCard
          title="平均时长"
          value={formatDuration(workflows.avgDuration)}
        />
      </div>

      <div className="charts">
        <TrendChart
          data={trends}
          title="通过率趋势"
          period="7d"
        />
      </div>

      <CITable data={workflows.runs} />
    </div>
  );
};
```

#### 自定义 Hook

```tsx
// src/hooks/useCI.ts

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { ciService } from '../services/ci';

export interface CIStats {
  todayRuns: number;
  successRate: number;
  avgDuration: number;
  todayTrend: number;
  rateTrend: number;
  runs: any[];
}

export const useCI = () => {
  const queryClient = useQueryClient();

  // 获取 CI 统计数据
  const { data: workflows, isLoading } = useQuery<CIStats>({
    queryKey: ['ci', 'stats'],
    queryFn: ciService.getStats,
    refetchInterval: 600000, // 10 分钟
  });

  // 获取趋势数据
  const { data: trends } = useQuery({
    queryKey: ['ci', 'trends'],
    queryFn: () => ciService.getTrends({ days: 7 }),
  });

  // 手动刷新
  const refreshMutation = useMutation({
    mutationFn: () => ciService.triggerSync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ci'] });
    },
  });

  return {
    workflows: workflows || { todayRuns: 0, successRate: 0, avgDuration: 0, todayTrend: 0, rateTrend: 0, runs: [] },
    trends: trends || [],
    loading: isLoading,
    refresh: refreshMutation.mutate,
  };
};
```

---

## 6. 部署方案

### 6.1 Docker Compose 配置

```yaml
# docker-compose.yml

version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./app.db
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - JWT_SECRET=${JWT_SECRET}
      - ENVIRONMENT=production
    volumes:
      - ./data:/app/data
    restart: unless-stopped
    networks:
      - dashboard-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "80:80"
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - dashboard-network

  # 可选：MySQL (生产环境)
  mysql:
    image: mysql:8.0
    environment:
      - MYSQL_ROOT_PASSWORD=${MYSQL_ROOT_PASSWORD}
      - MYSQL_DATABASE=vllm_dashboard
      - MYSQL_USER=dashboard
      - MYSQL_PASSWORD=${MYSQL_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    profiles:
      - production
    networks:
      - dashboard-network
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  mysql_data:

networks:
  dashboard-network:
    driver: bridge
```

### 6.2 后端 Dockerfile

```dockerfile
# backend/Dockerfile

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# 运行应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 6.3 前端 Dockerfile

```dockerfile
# frontend/Dockerfile

# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# 生产阶段
FROM nginx:alpine

# 复制自定义 nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 暴露端口
EXPOSE 80

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
```

---

## 7. 异常处理设计

### 7.1 GitHub API 限流处理

```python
# backend/app/core/exceptions.py

import logging
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

class GitHubRateLimitExceeded(HTTPException):
    """GitHub API 速率限制异常"""

    def __init__(self, retry_after: int):
        super().__init__(
            status_code=429,
            detail={
                "error": "GitHub API rate limit exceeded",
                "retry_after": retry_after,
                "message": f"Please retry after {retry_after} seconds"
            }
        )

async def github_rate_limit_handler(request: Request, call_next):
    """GitHub API 限流处理中间件"""
    try:
        response = await call_next(request)
    except GitHubRateLimitExceeded as e:
        # 记录日志
        logger.warning(f"GitHub rate limit exceeded: {e.detail}")

        # 返回友好的错误信息
        return JSONResponse(
            status_code=429,
            content={
                "error": "Data sync temporarily unavailable",
                "message": "GitHub API rate limit reached. Showing cached data.",
                "cached": True
            }
        )

    return response
```

### 7.2 数据解析失败处理

```python
# backend/app/services/data_parser.py

from typing import Optional, Tuple, Any, Callable
import logging
import json

logger = logging.getLogger(__name__)

class DataParseError(Exception):
    """数据解析错误"""
    pass

async def safe_parse_json(
    content: str,
    fallback_value: Optional[dict] = None
) -> Tuple[Optional[dict], bool]:
    """安全解析 JSON，失败时返回默认值"""
    try:
        return json.loads(content), True
    except json.JSONDecodeError as e:
        logger.error(f"JSON parse failed: {e}")
        return fallback_value, False

async def parse_with_fallback(
    primary_parser: Callable,
    fallback_parser: Callable,
    data: Any
) -> Any:
    """主备解析器模式"""
    try:
        return await primary_parser(data)
    except Exception as e:
        logger.warning(f"Primary parser failed, using fallback: {e}")
        try:
            return await fallback_parser(data)
        except Exception as fallback_error:
            logger.error(f"Fallback parser also failed: {fallback_error}")
            raise DataParseError("All parsers failed")
```

### 7.3 重试机制

```python
# backend/app/core/retry.py

import asyncio
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0
) -> Any:
    """带指数退避的重试机制"""

    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_exception = e

            if attempt == max_retries:
                break

            # 记录重试日志
            logger.warning(
                f"Attempt {attempt + 1} failed: {e}. "
                f"Retrying in {delay}s..."
            )

            await asyncio.sleep(delay)
            delay = min(delay * exponential_base, max_delay)

    raise last_exception


def retry_on_failure(
    max_retries: int = 3,
    initial_delay: float = 1.0
):
    """重试装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_with_backoff(
                lambda: func(*args, **kwargs),
                max_retries=max_retries,
                initial_delay=initial_delay
            )
        return wrapper
    return decorator
```

---

## 8. 安全设计

### 8.1 认证流程

```
用户登录 → 验证密码 → 生成 JWT → 返回 Token
                ↓
           (bcrypt 加密)
                ↓
        存储在 users 表

访问 API → 携带 Token → 验证签名 → 解析用户信息 → 权限检查
                ↓
         (JWT 验证中间件)
```

### 8.2 密码加密

```python
# backend/app/core/security.py

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """密码加密"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)
```

### 8.3 JWT Token 生成

```python
from datetime import datetime, timedelta, timezone
from jose import jwt
from typing import Optional

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 小时

def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """生成访问 Token"""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(
        to_encode,
        settings.JWT_SECRET,
        algorithm=ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """生成刷新 Token（7 天有效期）"""
    return create_access_token(data, timedelta(days=7))
```

---

## 9. 监控与日志

### 9.1 日志配置

```python
# backend/app/core/logging_config.py

import logging
import sys

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        },
        "access": {
            "format": "%(asctime)s - %(client_ip)s - %(request_line)s - %(status_code)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": sys.stdout
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "formatter": "default",
            "filename": "/app/data/app.log",
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"]
    }
}
```

### 9.2 关键指标监控

| 指标 | 采集方式 | 告警阈值 |
|-----|---------|---------|
| API 响应时间 | 中间件记录 | P99 > 1s |
| API 错误率 | 异常捕获统计 | > 5% |
| GitHub API 调用次数 | 请求头统计 | 接近限制 80% |
| 数据同步延迟 | 最后同步时间 | > 30 分钟 |
| 数据库连接数 | 连接池监控 | > 80% |

---

## 10. 开发计划

### 10.1 开发节奏（按 Phase）

本项目采用分阶段开发模式，每个 Phase 独立交付可用功能，逐步完善看板能力。

```
Phase 1 (2 周)          Phase 2 (2 周)          Phase 3 (2 周)          Phase 4 (1 周)
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│ 基础架构         │    │ CI 看板          │    │ 模型看板 + 性能  │    │ 高级功能        │
│ + 认证系统       │ -> │ 数据采集        │ -> │ 看板            │ -> │ + 优化          │
│                 │    │                 │    │                 │    │                 │
│ ✅ 项目脚手架   │    │ ✅ CI 数据同步   │    │ ✅ 模型管理      │    │ ✅ 趋势分析     │
│ ✅ 数据库设计   │    │ ✅ 数据展示      │    │ ✅ 性能数据解析  │    │ ✅ 基准对比     │
│ ✅ 用户认证     │    │ ✅ 硬件识别      │    │ ✅ 性能展示      │    │ ✅ 数据导出     │
│ ✅ GitHub API   │    │ ✅ 状态展示      │    │ ✅ 报告展示      │    │ ✅ REST API     │
└─────────────────┘    └─────────────────┘    └─────────────────┘    └─────────────────┘
```

---

### 10.2 Phase 1：基础架构 + 认证系统（2 周）

**目标**：搭建项目基础架构，实现用户认证和权限管理

**核心任务**：

| 周次 | 任务 | 交付物 |
|-----|------|--------|
| Week 1 | 后端脚手架搭建 | FastAPI 项目结构、数据库连接 |
| Week 1 | 数据库模型定义 | SQLAlchemy 模型、表结构创建 |
| Week 1 | 用户认证实现 | JWT Token 生成/验证、登录接口 |
| Week 1 | 前端脚手架搭建 | React 项目结构、路由配置 |
| Week 2 | 权限中间件 | 角色权限校验、API 访问控制 |
| Week 2 | 前端登录页面 | 登录表单、Token 存储 |
| Week 2 | Docker 配置 | docker-compose.yml、Dockerfile |

**验收标准**：
- [ ] 用户可以登录/登出
- [ ] Token 验证正常工作
- [ ] 管理员权限校验生效
- [ ] 数据库连接正常
- [ ] Docker 可以一键启动

**技术风险**：
- JWT Token 有效期设置需要合理（建议 24 小时）
- 密码加密使用 bcrypt，不要明文存储

---

### 10.3 Phase 2：CI 看板 + 数据采集（2 周）

**目标**：实现 CI 数据采集和展示，用户可以查看 CI 状态

**核心任务**：

| 周次 | 任务 | 交付物 |
|-----|------|--------|
| Week 3 | GitHub API 客户端 | 速率限制处理、重试机制 |
| Week 3 | CI 数据采集服务 | workflow runs 采集、硬件识别 |
| Week 3 | 数据库存储 | CI 结果表、索引优化 |
| Week 3 | 定时同步任务 | APScheduler 配置、自动同步 |
| Week 4 | CI 数据 API | 统计接口、趋势接口 |
| Week 4 | 前端 CI 看板页面 | 状态卡片、表格展示 |
| Week 4 | 硬件维度切换 | A2/A3 筛选、分类展示 |

**验收标准**：
- [ ] 可以自动同步 CI 数据（每 10 分钟）
- [ ] 正确识别硬件信息（A2/A3）
- [ ] 展示最近 7 天的 CI 运行状态
- [ ] 支持手动刷新数据
- [ ] GitHub API 限流时正常降级

**技术风险**：
- GitHub API 速率限制（5000 次/小时），需要合理使用
- workflow 文件名可能变化，需要灵活识别硬件

---

### 10.4 Phase 3：模型看板 + 性能看板（2 周）

**目标**：实现模型看板报告和性能数据展示

**核心任务**：

| 周次 | 任务 | 交付物 |
|-----|------|--------|
| Week 5 | 模型管理 API | 模型 CRUD、配置管理 |
| Week 5 | 模型看板报告解析 | lm_eval 结果解析、Pass/Fail 判定 |
| Week 5 | 性能数据解析 | benchmarks JSON 解析、指标提取 |
| Week 5 | 前端模型看板页面 | 模型列表、报告详情 |
| Week 6 | 性能数据 API | 趋势接口、对比接口 |
| Week 6 | 前端性能看板页面 | 性能图表、硬件切换 |
| Week 6 | 手动上传功能 | YAML/JSON 上传、解析验证 |

**验收标准**：
- [ ] 可以管理模型配置（增删改查）
- [ ] 正确解析模型看板报告
- [ ] 展示性能指标（吞吐量、延迟）
- [ ] 支持 A2/A3 硬件切换
- [ ] 支持手动上传性能数据

**技术风险**：
- 模型看板报告格式可能变化
- 性能数据量较大，需要分页展示

---

### 10.5 Phase 4：高级功能 + 优化（1 周）

**目标**：实现趋势分析、基准对比等高级功能

**核心任务**：

| 天数 | 任务 | 交付物 |
|-----|------|--------|
| Day 1-2 | 趋势分析功能 | 时间序列图表、版本筛选 |
| Day 2-3 | 基准对比功能 | 版本对比、基线对比 |
| Day 3-4 | 数据导出功能 | CSV/JSON 导出 |
| Day 4-5 | REST API 文档 | OpenAPI 文档、使用示例 |
| Day 5 | 性能优化 | 数据库查询优化、缓存 |

**验收标准**：
- [ ] 可以查看历史趋势（天/周/月）
- [ ] 支持版本对比（v0.16.0 vs 当前）
- [ ] 支持基线对比（手动输入目标值）
- [ ] 可以导出 CSV/JSON 数据
- [ ] API 响应时间 < 500ms

**技术风险**：
- 历史数据量大，需要优化查询性能
- 图表渲染性能需要优化

---

### 10.6 里程碑

```
Week 0 (2026-03-23)     : 项目启动
    ↓
Week 2 (2026-04-06)     : M1 - 基础架构完成，可以登录
    ↓
Week 4 (2026-04-20)     : M2 - CI 看板可用，数据自动同步
    ↓
Week 6 (2026-05-04)     : M3 - 模型看板 + 性能看板完成
    ↓
Week 7 (2026-05-11)     : M4 - 全部功能完成，上线发布
```

---

### 10.7 人员配置建议

| Phase | 后端 | 前端 | 测试 | 合计 |
|-------|------|------|------|------|
| Phase 1 | 2 人 | 1 人 | 0.5 人 | 3.5 人 |
| Phase 2 | 2 人 | 1 人 | 0.5 人 | 3.5 人 |
| Phase 3 | 2 人 | 1 人 | 0.5 人 | 3.5 人 |
| Phase 4 | 1 人 | 1 人 | 0.5 人 | 2.5 人 |

---

### 10.8 每周检查点

| 周次 | 检查点 | 负责人 |
|-----|--------|--------|
| Week 1 | 项目脚手架、数据库连接 | 后端负责人 |
| Week 2 | 认证系统、Docker 部署 | 后端负责人 |
| Week 3 | GitHub API 集成、数据同步 | 后端负责人 |
| Week 4 | CI 看板展示、硬件识别 | 前端负责人 |
| Week 5 | 模型管理、报告解析 | 后端负责人 |
| Week 6 | 性能看板、数据展示 | 前端负责人 |
| Week 7 | 高级功能、性能优化 | 全体 |

---

## 11. 附录

### 11.1 环境变量配置

```bash
# .env.example

# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
GITHUB_OWNER=vllm-project
GITHUB_REPO=vllm-ascend

# 数据库
DATABASE_URL=sqlite+aiosqlite:///./app.db
# 生产环境
# DATABASE_URL=mysql+aiomysql://user:pass@localhost/vllm_dashboard

# JWT
JWT_SECRET=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# 应用
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# 同步配置
SYNC_INTERVAL_MINUTES=10
DATA_RETENTION_DAYS=365
```

### 11.2 依赖清单

**后端依赖** (requirements.txt):
```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
aiosqlite==0.19.0
aiomysql==0.1.1
pydantic==2.5.0
pydantic-settings==2.1.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.25.2
apscheduler==3.10.4
python-multipart==0.0.6
```

**前端依赖** (package.json):
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@tanstack/react-query": "^5.8.0",
    "antd": "^5.11.0",
    "recharts": "^2.10.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "@types/react": "^18.2.0"
  }
}
```

### 11.3 GitHub Workflows 参考

**关键 Workflow 文件**：

| Workflow 文件 | Workflow 名称 | 用途 | 频率 |
|-------------|------------|------|------|
| `schedule_nightly_test_a2.yaml` | Nightly-A2 | A2 硬件夜间测试 | 每日 16:00 UTC+8 |
| `schedule_nightly_test_a3.yaml` | Nightly-A3 | A3 硬件夜间测试 | 每日 16:00 UTC+8 |
| `schedule_test_benchmarks.yaml` | Performance Schedule Test | 性能基准测试 | 每日 12:00/19:00 UTC+8 |
| `_e2e_test.yaml` | e2e test | E2E 测试（含 Doctests） | PR 触发/手动 |
| `pr_test_light.yaml` | E2E-Light | PR 轻量级测试 | PR 触发 |
| `pr_test_full.yaml` | E2E-Full | PR 完整测试 | PR 触发（带 ready 标签） |
| `_unit_test.yaml` | unit test | 单元测试 | PR 触发 |

**测试目录结构**（基于 vllm-ascend 源码）：

```
tests/
├── e2e/                    # E2E 测试
│   ├── singlecard/        # 单卡测试
│   │   ├── compile/       # 编译优化测试
│   │   ├── spec_decode/   # 推测解码测试
│   │   └── model_runner_v2/
│   ├── multicard/         # 多卡测试
│   │   ├── 2-cards/
│   │   └── 4-cards/
│   ├── nightly/           # 夜间测试
│   │   ├── single_node/
│   │   └── multi_node/
│   ├── models/            # 模型看板（lm_eval）
│   │   ├── configs/       # 模型配置文件
│   │   └── test_lm_eval_correctness.py
│   ├── doctests/          # 文档测试
│   └── weekly/            # 周测试
├── ut/                     # 单元测试
│   ├── attention/
│   ├── compilation/
│   ├── core/
│   ├── distributed/
│   ├── eplb/
│   ├── kv_connector/
│   ├── model_loader/
│   ├── ops/
│   ├── quantization/
│   ├── spec_decode/
│   └── worker/
└── __init__.py

benchmarks/
├── tests/
│   ├── latency-tests.json
│   ├── throughput-tests.json
│   └── serving-tests.json
└── scripts/
    ├── run-performance-benchmarks.sh
    └── convert_json_to_markdown.py
```

---

**文档版本**: v0.13  
**创建日期**: 2026-03-23  
**最后更新**: 2026-03-23  
**状态**: 可用于开发

## 修订历史

| 版本 | 日期 | 修订内容 |
|------|------|---------|
| v0.1 | 2026-03-23 | 初始版本 |
| v0.2 | 2026-03-23 | 修复代码 bug：补充缺失的导入、添加错误处理、完善辅助函数 |
| v0.3 | 2026-03-23 | 删除开发计划章节 |
| v0.4 | 2026-03-23 | 多轮审查修复：章节编号、类型注解、Docker 配置、健康检查 |
| v0.5 | 2026-03-23 | 开发前最终审查：修复数据库会话、API 路径、logger 导入、ER 图字段 |
| v0.6 | 2026-03-23 | 对照 vllm-ascend 源码：更新 Workflow 名称、补充测试目录结构 |
| v0.7 | 2026-03-23 | 最终审查：修复 workflow 名称提取逻辑、硬件信息识别逻辑 |
| v0.8 | 2026-03-23 | 明确数据采集方式：从 GitHub API 获取，不依赖源码，只学习测试方法 |
| v0.9 | 2026-03-23 | 统一命名：workflow_id_or_name、workflow_files，添加详细注释 |
| v0.10 | 2026-03-23 | 补充开发计划：按 Phase 划分、里程碑、人员配置 |
| v0.11 | 2026-03-23 | 最终审查：补充性能数据同步说明、验证章节编号和代码块 |
| v0.12 | 2026-03-23 | 深度审查：修复导入路径、类型注解、脚本检查逻辑（9 个 bug） |
| v0.13 | 2026-03-23 | 第 4 轮审查：修复汉化问题、后台日志输出（10 个 bug） |
