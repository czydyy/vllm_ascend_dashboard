"""
数据库初始化脚本
- 创建数据库表（包含所有最新版本的表结构）
- 执行版本化升级（兼容已有数据库的升级）
- 创建默认管理员账号

使用方法:
    python scripts/init_db.py              # 初始化 + 升级到最新版本
    python scripts/init_db.py --no-upgrade  # 只创建表，不升级（用于调试）

注意：
    对于新数据库，会直接创建最新结构的表
    对于已有数据库，会执行增量升级
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加父目录到路径以便导入
repository_root = Path(__file__).resolve().parents[1]
application_root = repository_root / "backend"
if not application_root.is_dir():
    application_root = repository_root
sys.path.insert(0, str(application_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

from sqlalchemy import text, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.security import hash_password
from app.db.base import SessionLocal, engine
from app.models import Base, User


# ============ 版本管理相关 ============

VERSION_TABLE = "database_versions"


async def check_table_exists(table_name: str) -> bool:
    """检查表是否存在"""
    try:
        from sqlalchemy import inspect
        
        def _get_table_names(conn):
            inspector = inspect(conn)
            return inspector.get_table_names()

        async with engine.begin() as conn:
            table_names = await conn.run_sync(_get_table_names)
            return table_name in table_names
    except Exception:
        return False


async def check_column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在"""
    try:
        from sqlalchemy import inspect
        
        def _get_columns(conn):
            inspector = inspect(conn)
            return [col['name'] for col in inspector.get_columns(table_name)]

        async with engine.begin() as conn:
            columns = await conn.run_sync(_get_columns)
            return column_name in columns
    except Exception:
        return False


async def ensure_version_table():
    """创建版本记录表"""
    is_mysql = "mysql" in str(engine.url)

    if is_mysql:
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
            id INT PRIMARY KEY AUTO_INCREMENT,
            version VARCHAR(20) NOT NULL UNIQUE,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
        """
    else:
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version VARCHAR(20) NOT NULL UNIQUE,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            description TEXT
        )
        """

    async with engine.begin() as conn:
        await conn.execute(text(create_sql))
    logger.info(f"Version table '{VERSION_TABLE}' ready")


async def get_current_version() -> str:
    """获取当前数据库版本"""
    try:
        if not await check_table_exists(VERSION_TABLE):
            return "0.0.0"

        async with SessionLocal() as db:
            stmt = text(f"SELECT version FROM {VERSION_TABLE} ORDER BY id DESC LIMIT 1")
            result = await db.execute(stmt)
            row = result.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return "0.0.0"


async def mark_version_applied(version: str, description: str = ""):
    """标记版本已应用"""
    async with SessionLocal() as db:
        stmt = text(
            f"INSERT INTO {VERSION_TABLE} (version, description, applied_at) "
            "VALUES (:version, :description, :applied_at)"
        )
        await db.execute(stmt, {
            "version": version,
            "description": description,
            "applied_at": datetime.now()
        })
        await db.commit()


# ============ 表创建逻辑（使用最新 schema） ============

async def create_tables_with_latest_schema():
    """
    创建所有数据库表（使用最新 schema）

    包含所有功能：
    - 基础表：users, model_configs, model_reports, ci_results, ci_jobs, workflow_configs
    - 性能数据：performance_data
    - Job 管理：job_owners
    - 模型同步：model_sync_configs
    - 项目看板：project_dashboard_config
    - GitHub 缓存：github_cache
    - 每日总结：daily_prs, daily_issues, daily_commits, daily_summaries, llm_provider_configs
    """
    print("Step 1: Creating database tables with latest schema...")
    
    is_mysql = "mysql" in str(engine.url)
    
    async with SessionLocal() as db:
        try:
            # 1. 使用 SQLAlchemy Model 创建基础表
            print("  Creating base tables from models...")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("  ✅ Base tables created\n")
            
            # 2. 检查并创建 github_cache 表
            if not await check_table_exists("github_cache"):
                print("  Creating github_cache table...")
                create_sql = """
                    CREATE TABLE github_cache (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        owner VARCHAR(100) NOT NULL,
                        repo VARCHAR(100) NOT NULL,
                        data_type VARCHAR(50) NOT NULL,
                        days INTEGER DEFAULT 1,
                        cache_data JSON NOT NULL,
                        cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        UNIQUE(owner, repo, data_type, days)
                    )
                """
                if is_mysql:
                    create_sql = """
                    CREATE TABLE github_cache (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        owner VARCHAR(100) NOT NULL,
                        repo VARCHAR(100) NOT NULL,
                        data_type VARCHAR(50) NOT NULL,
                        days INT DEFAULT 1,
                        cache_data JSON NOT NULL,
                        cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        expires_at DATETIME NOT NULL,
                        UNIQUE KEY uq_github_cache_owner_repo_type_days (owner, repo, data_type, days)
                    )
                    """
                
                await db.execute(text(create_sql))
                
                # 创建索引
                indexes = [
                    ("idx_github_cache_owner", "owner"),
                    ("idx_github_cache_repo", "repo"),
                    ("idx_github_cache_data_type", "data_type"),
                    ("idx_github_cache_cached_at", "cached_at"),
                    ("idx_github_cache_expires_at", "expires_at"),
                ]
                
                for index_name, column in indexes:
                    try:
                        if is_mysql:
                            await db.execute(text(f"CREATE INDEX {index_name} ON github_cache({column})"))
                        else:
                            await db.execute(text(f"CREATE INDEX {index_name} ON github_cache({column})"))
                    except Exception as e:
                        logger.warning(f"Index {index_name} may already exist: {e}")
                
                print("  ✅ github_cache table created\n")
            else:
                print("  ✓ github_cache table already exists\n")
            
            # 3. 创建每日总结相关表
            await _create_daily_summary_tables(db, is_mysql)
            
            # 4. 检查并修复现有表的字段缺失
            await _fix_existing_table_columns(db, is_mysql)
            
            await db.commit()
            print("  ✅ All tables created with latest schema\n")
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to create tables: {e}", exc_info=True)
            print(f"  ❌ Failed to create tables: {e}\n")
            raise


async def _create_daily_summary_tables(db, is_mysql: bool):
    """创建每日总结相关表"""
    print("  Creating daily summary tables...")
    
    # daily_prs
    if not await check_table_exists("daily_prs"):
        if is_mysql:
            create_sql = """
                CREATE TABLE daily_prs (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    project VARCHAR(100) NOT NULL,
                    pr_number INT NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    state VARCHAR(20) NOT NULL,
                    author VARCHAR(100) NOT NULL,
                    created_at DATETIME NOT NULL,
                    merged_at DATETIME,
                    html_url VARCHAR(500) NOT NULL,
                    labels JSON,
                    body TEXT,
                    commits JSON NOT NULL,
                    data_date DATE NOT NULL,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_daily_pr_project_number_date (project, pr_number, data_date),
                    INDEX idx_daily_prs_project (project),
                    INDEX idx_daily_prs_date (data_date)
                )
            """
        else:
            create_sql = """
                CREATE TABLE daily_prs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project VARCHAR(100) NOT NULL,
                    pr_number INTEGER NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    state VARCHAR(20) NOT NULL,
                    author VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    merged_at TIMESTAMP,
                    html_url VARCHAR(500) NOT NULL,
                    labels JSON,
                    body TEXT,
                    commits JSON NOT NULL,
                    data_date DATE NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_daily_pr_project_number_date UNIQUE (project, pr_number, data_date)
                )
            """
        
        await db.execute(text(create_sql))
        
        if not is_mysql:
            await db.execute(text("CREATE INDEX idx_daily_prs_project ON daily_prs(project)"))
            await db.execute(text("CREATE INDEX idx_daily_prs_date ON daily_prs(data_date)"))

        print("    ✅ Created daily_prs")
    else:
        print("    ✓ daily_prs already exists")
    
    # daily_issues
    if not await check_table_exists("daily_issues"):
        if is_mysql:
            create_sql = """
                CREATE TABLE daily_issues (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    project VARCHAR(100) NOT NULL,
                    issue_number INT NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    state VARCHAR(20) NOT NULL,
                    author VARCHAR(100) NOT NULL,
                    created_at DATETIME NOT NULL,
                    closed_at DATETIME,
                    html_url VARCHAR(500) NOT NULL,
                    labels JSON,
                    body TEXT,
                    comments_count INT DEFAULT 0,
                    data_date DATE NOT NULL,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_daily_issue_project_number_date (project, issue_number, data_date),
                    INDEX idx_daily_issues_project (project),
                    INDEX idx_daily_issues_date (data_date)
                )
            """
        else:
            create_sql = """
                CREATE TABLE daily_issues (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project VARCHAR(100) NOT NULL,
                    issue_number INTEGER NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    state VARCHAR(20) NOT NULL,
                    author VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    closed_at TIMESTAMP,
                    html_url VARCHAR(500) NOT NULL,
                    labels JSON,
                    body TEXT,
                    comments_count INTEGER DEFAULT 0,
                    data_date DATE NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_daily_issue_project_number_date UNIQUE (project, issue_number, data_date)
                )
            """
        
        await db.execute(text(create_sql))
        
        if not is_mysql:
            await db.execute(text("CREATE INDEX idx_daily_issues_project ON daily_issues(project)"))
            await db.execute(text("CREATE INDEX idx_daily_issues_date ON daily_issues(data_date)"))
        
        print("    ✅ Created daily_issues")
    else:
        print("    ✓ daily_issues already exists")
    
    # daily_commits
    if not await check_table_exists("daily_commits"):
        if is_mysql:
            create_sql = """
                CREATE TABLE daily_commits (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    project VARCHAR(100) NOT NULL,
                    sha VARCHAR(40) NOT NULL,
                    short_sha VARCHAR(7) NOT NULL,
                    message VARCHAR(1000) NOT NULL,
                    full_message TEXT,
                    author VARCHAR(100) NOT NULL,
                    author_email VARCHAR(200),
                    committed_at DATETIME NOT NULL,
                    html_url VARCHAR(500) NOT NULL,
                    pr_number INT,
                    pr_title VARCHAR(500),
                    pr_description TEXT,
                    files_changed JSON,
                    additions INT DEFAULT 0,
                    deletions INT DEFAULT 0,
                    data_date DATE NOT NULL,
                    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_daily_commit_project_sha_date (project, sha, data_date),
                    INDEX idx_daily_commits_project (project),
                    INDEX idx_daily_commits_date (data_date),
                    INDEX idx_daily_commits_pr (pr_number)
                )
            """
        else:
            create_sql = """
                CREATE TABLE daily_commits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project VARCHAR(100) NOT NULL,
                    sha VARCHAR(40) NOT NULL,
                    short_sha VARCHAR(7) NOT NULL,
                    message VARCHAR(1000) NOT NULL,
                    full_message TEXT,
                    author VARCHAR(100) NOT NULL,
                    author_email VARCHAR(200),
                    committed_at TIMESTAMP NOT NULL,
                    html_url VARCHAR(500) NOT NULL,
                    pr_number INTEGER,
                    pr_title VARCHAR(500),
                    pr_description TEXT,
                    files_changed JSON,
                    additions INTEGER DEFAULT 0,
                    deletions INTEGER DEFAULT 0,
                    data_date DATE NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_daily_commit_project_sha_date UNIQUE (project, sha, data_date)
                )
            """
        
        await db.execute(text(create_sql))
        
        if not is_mysql:
            await db.execute(text("CREATE INDEX idx_daily_commits_project ON daily_commits(project)"))
            await db.execute(text("CREATE INDEX idx_daily_commits_date ON daily_commits(data_date)"))
            await db.execute(text("CREATE INDEX idx_daily_commits_pr ON daily_commits(pr_number)"))
        
        print("    ✅ Created daily_commits")
    else:
        print("    ✓ daily_commits already exists")
    
    # daily_summaries
    if not await check_table_exists("daily_summaries"):
        if is_mysql:
            create_sql = """
                CREATE TABLE daily_summaries (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    project VARCHAR(100) NOT NULL,
                    data_date DATE NOT NULL,
                    summary_markdown TEXT NOT NULL,
                    has_data BOOLEAN DEFAULT TRUE,
                    pr_count INT DEFAULT 0,
                    issue_count INT DEFAULT 0,
                    commit_count INT DEFAULT 0,
                    llm_provider VARCHAR(50),
                    llm_model VARCHAR(100),
                    prompt_tokens INT,
                    completion_tokens INT,
                    generation_time_seconds INT,
                    status VARCHAR(20) DEFAULT 'success',
                    error_message TEXT,
                    generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    regenerated_at DATETIME,
                    UNIQUE KEY uq_daily_summary_project_date (project, data_date),
                    INDEX idx_daily_summaries_project (project),
                    INDEX idx_daily_summaries_date (data_date)
                )
            """
        else:
            create_sql = """
                CREATE TABLE daily_summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project VARCHAR(100) NOT NULL,
                    data_date DATE NOT NULL,
                    summary_markdown TEXT NOT NULL,
                    has_data BOOLEAN DEFAULT 1,
                    pr_count INTEGER DEFAULT 0,
                    issue_count INTEGER DEFAULT 0,
                    commit_count INTEGER DEFAULT 0,
                    llm_provider VARCHAR(50),
                    llm_model VARCHAR(100),
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    generation_time_seconds INTEGER,
                    status VARCHAR(20) DEFAULT 'success',
                    error_message TEXT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    regenerated_at TIMESTAMP,
                    CONSTRAINT uq_daily_summary_project_date UNIQUE (project, data_date)
                )
            """
        
        await db.execute(text(create_sql))
        
        if not is_mysql:
            await db.execute(text("CREATE INDEX idx_daily_summaries_project ON daily_summaries(project)"))
            await db.execute(text("CREATE INDEX idx_daily_summaries_date ON daily_summaries(data_date)"))
        
        print("    ✅ Created daily_summaries")
    else:
        print("    ✓ daily_summaries already exists")
    
    # llm_provider_configs
    if not await check_table_exists("llm_provider_configs"):
        if is_mysql:
            create_sql = """
                CREATE TABLE llm_provider_configs (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    provider VARCHAR(50) NOT NULL UNIQUE,
                    display_name VARCHAR(100) NOT NULL,
                    api_key VARCHAR(500),
                    api_base_url VARCHAR(500),
                    default_model VARCHAR(100) NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    is_active BOOLEAN DEFAULT FALSE,
                    display_order INT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                )
            """
            await db.execute(text(create_sql))

            # 初始化默认配置
            insert_sql = """
                INSERT INTO llm_provider_configs
                (provider, display_name, api_base_url, default_model, enabled, is_active, display_order)
                VALUES
                ('openai', 'OpenAI GPT-4', 'https://api.openai.com/v1', 'gpt-4o', 1, 0, 1),
                ('anthropic', 'Anthropic Claude', 'https://api.anthropic.com', 'claude-sonnet-4-20250514', 1, 0, 2),
                ('qwen', '通义千问', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus', 1, 0, 3)
            """
            await db.execute(text(insert_sql))
            print("    ✅ Created llm_provider_configs (with default providers)")
        else:
            create_sql = """
                CREATE TABLE llm_provider_configs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider VARCHAR(50) NOT NULL UNIQUE,
                    display_name VARCHAR(100) NOT NULL,
                    api_key VARCHAR(500),
                    api_base_url VARCHAR(500),
                    default_model VARCHAR(100) NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    is_active BOOLEAN DEFAULT 0,
                    display_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            await db.execute(text(create_sql))
            
            # 初始化默认配置
            insert_sql = """
                INSERT INTO llm_provider_configs
                (provider, display_name, api_base_url, default_model, enabled, is_active, display_order)
                VALUES
                ('openai', 'OpenAI GPT-4', 'https://api.openai.com/v1', 'gpt-4o', 1, 0, 1),
                ('anthropic', 'Anthropic Claude', 'https://api.anthropic.com', 'claude-sonnet-4-20250514', 1, 0, 2),
                ('qwen', '通义千问', 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'qwen-plus', 1, 0, 3)
            """
            await db.execute(text(insert_sql))
            print("    ✅ Created llm_provider_configs (with default providers)")
    else:
        print("    ✓ llm_provider_configs already exists")
    
    print()


async def _fix_existing_table_columns(db, is_mysql: bool):
    """修复现有表的字段缺失（添加最新 schema 的列）"""
    print("  Checking for missing columns in existing tables...")
    
    # model_configs 表字段
    if await check_table_exists("model_configs"):
        columns_to_add = [
            ("key_metrics_config", "TEXT"),
            ("pass_threshold", "TEXT"),
            ("startup_commands", "TEXT"),
            ("official_doc_url", "VARCHAR(500)"),
        ]
        
        for col_name, col_type in columns_to_add:
            if not await check_column_exists("model_configs", col_name):
                print(f"    Adding {col_name} to model_configs...")
                await db.execute(text(f"ALTER TABLE model_configs ADD COLUMN {col_name} {col_type}"))
                print(f"      ✅ Added {col_name}")
    
    # model_reports 表字段
    if await check_table_exists("model_reports"):
        columns_to_add = [
            ("report_markdown", "TEXT"),
            ("auto_pass_fail", "VARCHAR(10)"),
            ("manual_override", "TINYINT(1) DEFAULT 0" if is_mysql else "INTEGER DEFAULT 0"),
            ("vllm_version", "VARCHAR(50)"),
            ("hardware", "VARCHAR(20)"),
            ("dtype", "VARCHAR(50)"),
            ("features", "JSON"),
            ("serve_cmd", "JSON"),
            ("environment", "JSON"),
            ("tasks", "JSON"),
        ]
        
        for col_name, col_type in columns_to_add:
            if not await check_column_exists("model_reports", col_name):
                print(f"    Adding {col_name} to model_reports...")
                if is_mysql:
                    await db.execute(text(f"ALTER TABLE model_reports ADD COLUMN {col_name} {col_type}"))
                else:
                    await db.execute(text(f"ALTER TABLE model_reports ADD COLUMN {col_name}"))
                print(f"      ✅ Added {col_name}")
        
        # 删除废弃字段
        columns_to_drop = ["known_issues", "github_artifact_url"]
        for col_name in columns_to_drop:
            if await check_column_exists("model_reports", col_name):
                print(f"    Dropping deprecated {col_name} from model_reports...")
                await db.execute(text(f"ALTER TABLE model_reports DROP COLUMN {col_name}"))
                print(f"      ✅ Dropped {col_name}")
    
    # model_sync_configs 表字段
    if await check_table_exists("model_sync_configs"):
        if not await check_column_exists("model_sync_configs", "branch"):
            print("    Adding branch to model_sync_configs...")
            if is_mysql:
                await db.execute(text("ALTER TABLE model_sync_configs ADD COLUMN branch VARCHAR(100) DEFAULT 'main'"))
            else:
                await db.execute(text("ALTER TABLE model_sync_configs ADD COLUMN branch VARCHAR(100) DEFAULT 'main'"))
            print("      ✅ Added branch")
        
        # 删除废弃字段
        for col_name in ["runs_limit", "sync_interval_minutes"]:
            if await check_column_exists("model_sync_configs", col_name):
                print(f"    Dropping deprecated {col_name} from model_sync_configs...")
                await db.execute(text(f"ALTER TABLE model_sync_configs DROP COLUMN {col_name}"))
                print(f"      ✅ Dropped {col_name}")
    
    # workflow_configs 表字段
    if await check_table_exists("workflow_configs"):
        if not await check_column_exists("workflow_configs", "last_sync_at"):
            print("    Adding last_sync_at to workflow_configs...")
            await db.execute(text("ALTER TABLE workflow_configs ADD COLUMN last_sync_at TIMESTAMP"))
            print("      ✅ Added last_sync_at")
    
    # ci_results 表字段
    if await check_table_exists("ci_results"):
        columns_to_add = [
            ("run_number", "INTEGER"),
            ("event", "VARCHAR(50)"),
            ("branch", "VARCHAR(100)"),
            ("head_sha", "VARCHAR(100)"),
        ]
        
        for col_name, col_type in columns_to_add:
            if not await check_column_exists("ci_results", col_name):
                print(f"    Adding {col_name} to ci_results...")
                await db.execute(text(f"ALTER TABLE ci_results ADD COLUMN {col_name} {col_type}"))
                print(f"      ✅ Added {col_name}")
    
    # llm_provider_configs 表字段
    if await check_table_exists("llm_provider_configs"):
        if not await check_column_exists("llm_provider_configs", "api_key"):
            print("    Adding api_key to llm_provider_configs...")
            await db.execute(text("ALTER TABLE llm_provider_configs ADD COLUMN api_key VARCHAR(500)"))
            print("      ✅ Added api_key")
        
        if not await check_column_exists("llm_provider_configs", "is_active"):
            print("    Adding is_active to llm_provider_configs...")
            if is_mysql:
                await db.execute(text("ALTER TABLE llm_provider_configs ADD COLUMN is_active BOOLEAN DEFAULT FALSE"))
            else:
                await db.execute(text("ALTER TABLE llm_provider_configs ADD COLUMN is_active BOOLEAN DEFAULT 0"))
            print("      ✅ Added is_active")
    
    print("  ✅ Table columns checked and fixed\n")


# ============ 用户创建逻辑 ============

async def create_default_users():
    """创建默认用户账号"""
    print("Step 3: Creating default users...")

    async with SessionLocal() as db:
        try:
            # 检查是否已存在超级管理员
            stmt = select(User).where(User.role == "super_admin")
            result = await db.execute(stmt)
            super_admin = result.scalar_one_or_none()

            if not super_admin:
                # 创建超级管理员
                super_admin = User(
                    username="admin",
                    email="admin@vllm-ascend.local",
                    password_hash=hash_password("admin123"),
                    role="super_admin",
                    is_active=True,
                )
                db.add(super_admin)

                # 创建普通管理员
                admin = User(
                    username="manager",
                    email="manager@vllm-ascend.local",
                    password_hash=hash_password("manager123"),
                    role="admin",
                    is_active=True,
                )
                db.add(admin)

                # 创建普通用户
                user = User(
                    username="user",
                    email="user@vllm-ascend.local",
                    password_hash=hash_password("user123"),
                    role="user",
                    is_active=True,
                )
                db.add(user)

                await db.commit()
                logger.info("Default users created successfully")

                print("\n  ✅ Default users created:")
                print("    Super Admin: admin / admin123")
                print("    Admin:       manager / manager123")
                print("    User:        user / user123")
                print("\n  ⚠️  Please change default passwords in production!\n")
            else:
                print("\n  ℹ️  Users already exist, skipping creation\n")

        except SQLAlchemyError as e:
            await db.rollback()
            logger.error(f"Database error creating users: {e}", exc_info=True)
            print(f"\n  ❌ Database error creating users: {e}\n")
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"Error creating users: {e}", exc_info=True)
            print(f"\n  ❌ Error creating users: {e}\n")
            raise
        finally:
            await db.close()


# ============ 主流程 ============

async def run_upgrades():
    """Mark a local bootstrap database after current-schema creation.

    Historical versioned upgrades are intentionally not executed here. Existing
    MySQL databases must use the canonical production migration entrypoint.
    """
    await ensure_version_table()
    current_version = await get_current_version()
    if current_version == "0.0.0":
        await mark_version_applied("current", "Current schema bootstrap")
    logger.info("Local bootstrap completed without historical upgrade scripts")


async def main():
    from sqlalchemy import select
    
    parser = argparse.ArgumentParser(description="Database initialization tool")
    parser.add_argument(
        "--no-upgrade",
        action="store_true",
        help="Skip running upgrades (only create tables)"
    )
    parser.add_argument(
        "--no-users",
        action="store_true",
        help="Skip creating default users"
    )

    args = parser.parse_args()

    if os.environ.get("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError(
            "init_db.py is a local bootstrap tool and is forbidden in production; "
            "run scripts/migrate_prod.sh instead"
        )

    print("\n" + "="*60)
    print("  vLLM Ascend Dashboard - Database Initialization")
    print("="*60 + "\n")

    try:
        # 1. 创建表（包含最新 schema）
        await create_tables_with_latest_schema()

        # 2. 执行升级（仅对已有数据库）
        if not args.no_upgrade:
            await run_upgrades()
        else:
            print("  ⏭️  Skipped upgrades (--no-upgrade)\n")

        # 3. 创建用户（除非跳过）
        if not args.no_users:
            await create_default_users()
        else:
            print("  ⏭️  Skipped user creation (--no-users)\n")

        print("="*60)
        print("  ✅ Database initialization completed!")
        print("="*60 + "\n")

    except SQLAlchemyError as e:
        logger.error(f"Database error during initialization: {e}", exc_info=True)
        print("\n" + "="*60)
        print(f"  ❌ Database initialization failed: {e}")
        print("="*60 + "\n")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Initialization failed: {e}", exc_info=True)
        print("\n" + "="*60)
        print(f"  ❌ Initialization failed: {e}")
        print("="*60 + "\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
