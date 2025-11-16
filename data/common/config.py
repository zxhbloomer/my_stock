"""
配置管理模块
"""
import os
from typing import Optional


class Config:
    """全局配置类"""

    # Tushare配置
    TUSHARE_TOKEN: Optional[str] = None

    # 数据库配置
    DB_TYPE: str = "mysql"  # mysql, postgresql, clickhouse
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "my_stock"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""

    # 数据目录配置
    DATA_DIR: str = "D:/Data/my_stock"
    SOURCE_DIR: str = "D:/Data/my_stock/source"
    NORMALIZED_DIR: str = "D:/Data/my_stock/normalized"

    @classmethod
    def load_from_env(cls):
        """从环境变量加载配置"""
        cls.TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
        cls.DB_TYPE = os.getenv("DB_TYPE", cls.DB_TYPE)
        cls.DB_HOST = os.getenv("DB_HOST", cls.DB_HOST)
        cls.DB_PORT = int(os.getenv("DB_PORT", cls.DB_PORT))
        cls.DB_NAME = os.getenv("DB_NAME", cls.DB_NAME)
        cls.DB_USER = os.getenv("DB_USER", cls.DB_USER)
        cls.DB_PASSWORD = os.getenv("DB_PASSWORD", cls.DB_PASSWORD)

    @classmethod
    def get_tushare_token(cls) -> str:
        """获取Tushare Token"""
        if cls.TUSHARE_TOKEN is None:
            cls.load_from_env()

        if cls.TUSHARE_TOKEN is None:
            raise ValueError(
                "Tushare token not configured. "
                "Please set TUSHARE_TOKEN environment variable or configure in code."
            )

        return cls.TUSHARE_TOKEN


# 自动加载环境变量配置
Config.load_from_env()
