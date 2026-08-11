"""
配置文件管理工具
用于读取和更新 .env 文件
"""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class EnvConfigManager:
    """
    .env 文件配置管理器

    功能：
    - 读取 .env 文件
    - 更新配置项
    - 保存 .env 文件

    注意：在生产环境（Docker 容器）中，配置通过环境变量传递，
         不需要读写 .env 文件
    """

    def __init__(self, env_file_path: str | None = None):
        """
        初始化配置管理器

        Args:
            env_file_path: .env 文件路径，默认为项目根目录的 .env 文件
        """
        # 检查是否在生产环境（通过环境变量判断）
        self.is_production = os.getenv('ENVIRONMENT') == 'production'
        
        if self.is_production:
            logger.info("Running in production mode, using environment variables")
            self.env_file = None
            self.config = {}
            return
        
        if env_file_path:
            self.env_file = Path(env_file_path)
        else:
            # 默认查找项目根目录的 .env 文件
            # 从当前文件向上查找 3 层
            current_dir = Path(__file__).parent
            found = False
            for _ in range(4):
                parent = current_dir.parent
                env_candidate = parent / ".env"
                if env_candidate.exists():
                    self.env_file = env_candidate
                    found = True
                    break
                current_dir = parent

            if not found:
                # 如果没找到，使用默认路径（backend 目录）
                self.env_file = Path(__file__).parent.parent / ".env"
                logger.warning(f".env file not found, using default path: {self.env_file}")

        self.config: dict[str, str] = {}
        self._load_config()

    def _load_config(self) -> None:
        """加载 .env 文件内容"""
        if not self.env_file.exists():
            logger.warning(f".env file not found: {self.env_file}")
            return

        try:
            with open(self.env_file, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 跳过空行和注释
                    if not line or line.startswith('#'):
                        continue

                    # 解析 KEY=VALUE
                    if '=' in line:
                        key, value = line.split('=', 1)
                        self.config[key.strip()] = value.strip()

            logger.info(f"Loaded {len(self.config)} config entries from {self.env_file}")
        except Exception as e:
            logger.error(f"Failed to load .env file: {e}")

    def get(self, key: str, default: str | None = None) -> str | None:
        """获取配置值"""
        return self.config.get(key, default)

    def set(self, key: str, value: str) -> None:
        """设置配置值（只更新内存）"""
        self.config[key] = value
        logger.info(f"Config updated: {key}={value}")

    def save(self) -> bool:
        """
        保存配置到 .env 文件

        Returns:
            是否保存成功
        """
        # 生产环境不保存文件
        if self.is_production:
            logger.info("Production mode: configuration saved to memory only (using environment variables)")
            return True
        
        try:
            # 备份原文件
            if self.env_file.exists():
                backup_file = self.env_file.with_suffix('.env.bak')
                with open(self.env_file, encoding='utf-8') as f:
                    original_content = f.read()
                with open(backup_file, 'w', encoding='utf-8') as f:
                    f.write(original_content)
                logger.info(f"Backed up .env file to {backup_file}")

            # 写入新内容
            with open(self.env_file, 'w', encoding='utf-8') as f:
                f.write("# vLLM Ascend Dashboard Configuration\n")
                f.write("# Auto-generated - DO NOT EDIT MANUALLY\n\n")

                # 写入配置项
                for key, value in self.config.items():
                    f.write(f"{key}={value}\n")

            logger.info(f"Saved {len(self.config)} config entries to {self.env_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save .env file: {e}")
            return False

    def update_multiple(self, updates: dict[str, Any]) -> bool:
        """
        批量更新配置并保存
        
        Args:
            updates: 配置更新字典
            
        Returns:
            是否更新成功
        """
        try:
            for key, value in updates.items():
                # 转换为大写键名
                config_key = key.upper()

                # 转换值为字符串
                if isinstance(value, bool):
                    str_value = str(value).lower()
                else:
                    str_value = str(value)

                self.config[config_key] = str_value

            return self.save()

        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return False


# 全局配置管理器实例
_config_manager: EnvConfigManager | None = None


def get_config_manager() -> EnvConfigManager:
    """获取全局配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = EnvConfigManager()
    return _config_manager


def update_env_config(updates: dict[str, Any]) -> bool:
    """
    便捷函数：更新配置并保存
    
    Args:
        updates: 配置更新字典
        
    Returns:
        是否更新成功
    """
    manager = get_config_manager()
    return manager.update_multiple(updates)
