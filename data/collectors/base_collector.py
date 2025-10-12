"""
数据采集器基类
参考 Qlib 官方 scripts/data_collector/base.py
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import pandas as pd


class BaseCollector(ABC):
    """数据采集基类"""

    def __init__(self, source_dir: str, start_date: str, end_date: str,
                 interval: str = "1d", delay: float = 0.5):
        """
        初始化采集器

        Args:
            source_dir: 数据存储目录
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            interval: 数据间隔 (1d/1min/5min)
            delay: 请求延迟（秒）
        """
        self.source_dir = Path(source_dir)
        self.source_dir.mkdir(parents=True, exist_ok=True)
        self.start_date = start_date
        self.end_date = end_date
        self.interval = interval
        self.delay = delay

    @abstractmethod
    def download_data(self, symbols: Optional[list] = None):
        """
        下载数据

        Args:
            symbols: 股票代码列表，None表示下载所有
        """
        raise NotImplementedError

    @abstractmethod
    def get_instrument_list(self) -> list:
        """获取股票列表"""
        raise NotImplementedError

    def save_to_csv(self, data: pd.DataFrame, symbol: str):
        """
        保存数据到CSV文件

        Args:
            data: 数据DataFrame
            symbol: 股票代码
        """
        file_path = self.source_dir / f"{symbol}.csv"
        data.to_csv(file_path, index=False, encoding='utf-8')
        print(f"保存 {symbol} 数据到 {file_path}")


class BaseNormalize(ABC):
    """数据标准化基类"""

    def __init__(self, source_dir: str, normalize_dir: str, interval: str = "1d"):
        """
        初始化标准化器

        Args:
            source_dir: 原始数据目录
            normalize_dir: 标准化数据输出目录
            interval: 数据间隔
        """
        self.source_dir = Path(source_dir)
        self.normalize_dir = Path(normalize_dir)
        self.normalize_dir.mkdir(parents=True, exist_ok=True)
        self.interval = interval

    @abstractmethod
    def normalize_data(self, qlib_data_1d_dir: Optional[str] = None):
        """
        标准化数据

        Args:
            qlib_data_1d_dir: 1日数据目录（用于分钟数据标准化）
        """
        raise NotImplementedError

    def normalize_symbol(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化单个股票数据

        标准格式：
            - date: 日期
            - instrument: 股票代码
            - open, close, high, low: 价格
            - volume: 成交量
            - factor: 复权因子

        Args:
            df: 原始数据

        Returns:
            标准化后的数据
        """
        # 子类实现具体标准化逻辑
        return df


class BaseRun:
    """命令行运行基类"""

    def __init__(self):
        self.collector = None
        self.normalize = None

    def download(self, **kwargs):
        """执行下载"""
        if self.collector is None:
            raise NotImplementedError("collector not initialized")
        self.collector.download_data(**kwargs)

    def normalize(self, **kwargs):
        """执行标准化"""
        if self.normalize is None:
            raise NotImplementedError("normalize not initialized")
        self.normalize.normalize_data(**kwargs)
