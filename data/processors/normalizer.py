"""
数据标准化模块
参考 Qlib 数据处理器
"""
import pandas as pd
import numpy as np
from typing import Optional


class DataNormalizer:
    """数据标准化器"""

    @staticmethod
    def forward_adjust(df: pd.DataFrame) -> pd.DataFrame:
        """
        前复权处理

        Args:
            df: 包含 open, close, high, low, factor 的数据

        Returns:
            前复权后的数据
        """
        if 'factor' not in df.columns:
            print("警告: 数据中没有复权因子，跳过复权")
            return df

        df = df.copy()
        price_cols = ['open', 'close', 'high', 'low']

        for col in price_cols:
            if col in df.columns:
                df[col] = df[col] * df['factor']

        return df

    @staticmethod
    def backward_adjust(df: pd.DataFrame) -> pd.DataFrame:
        """
        后复权处理

        Args:
            df: 包含 open, close, high, low, factor 的数据

        Returns:
            后复权后的数据
        """
        if 'factor' not in df.columns:
            print("警告: 数据中没有复权因子，跳过复权")
            return df

        df = df.copy()
        price_cols = ['open', 'close', 'high', 'low']

        # 计算后复权因子（最新交易日因子为1）
        latest_factor = df['factor'].iloc[-1]
        df['adj_factor'] = df['factor'] / latest_factor

        for col in price_cols:
            if col in df.columns:
                df[col] = df[col] * df['adj_factor']

        df = df.drop('adj_factor', axis=1)
        return df

    @staticmethod
    def fill_missing_data(df: pd.DataFrame, method: str = 'ffill') -> pd.DataFrame:
        """
        填充缺失数据

        Args:
            df: 数据DataFrame
            method: 填充方法 (ffill/bfill/interpolate)

        Returns:
            填充后的数据
        """
        df = df.copy()

        if method == 'ffill':
            df = df.fillna(method='ffill')
        elif method == 'bfill':
            df = df.fillna(method='bfill')
        elif method == 'interpolate':
            numeric_cols = df.select_dtypes(include=[np.number]).columns
            df[numeric_cols] = df[numeric_cols].interpolate(method='linear')

        return df

    @staticmethod
    def remove_outliers(df: pd.DataFrame, columns: list, method: str = 'zscore',
                       threshold: float = 3.0) -> pd.DataFrame:
        """
        去除异常值

        Args:
            df: 数据DataFrame
            columns: 需要处理的列
            method: 方法 (zscore/iqr)
            threshold: 阈值

        Returns:
            处理后的数据
        """
        df = df.copy()

        for col in columns:
            if col not in df.columns:
                continue

            if method == 'zscore':
                # Z-score方法
                mean = df[col].mean()
                std = df[col].std()
                df = df[np.abs((df[col] - mean) / std) <= threshold]

            elif method == 'iqr':
                # IQR方法
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                lower_bound = Q1 - threshold * IQR
                upper_bound = Q3 + threshold * IQR
                df = df[(df[col] >= lower_bound) & (df[col] <= upper_bound)]

        return df

    @staticmethod
    def clip_outliers(df: pd.DataFrame, columns: list, lower: float = 0.01,
                     upper: float = 0.99) -> pd.DataFrame:
        """
        截断异常值（而非删除）

        Args:
            df: 数据DataFrame
            columns: 需要处理的列
            lower: 下分位数
            upper: 上分位数

        Returns:
            处理后的数据
        """
        df = df.copy()

        for col in columns:
            if col not in df.columns:
                continue

            lower_val = df[col].quantile(lower)
            upper_val = df[col].quantile(upper)
            df[col] = df[col].clip(lower=lower_val, upper=upper_val)

        return df

    @staticmethod
    def standardize(df: pd.DataFrame, columns: list, method: str = 'zscore') -> pd.DataFrame:
        """
        标准化数据

        Args:
            df: 数据DataFrame
            columns: 需要标准化的列
            method: 方法 (zscore/minmax/robust)

        Returns:
            标准化后的数据
        """
        df = df.copy()

        for col in columns:
            if col not in df.columns:
                continue

            if method == 'zscore':
                # Z-score标准化
                mean = df[col].mean()
                std = df[col].std()
                df[col] = (df[col] - mean) / std

            elif method == 'minmax':
                # Min-Max标准化
                min_val = df[col].min()
                max_val = df[col].max()
                df[col] = (df[col] - min_val) / (max_val - min_val)

            elif method == 'robust':
                # 鲁棒标准化（基于中位数和IQR）
                median = df[col].median()
                Q1 = df[col].quantile(0.25)
                Q3 = df[col].quantile(0.75)
                IQR = Q3 - Q1
                df[col] = (df[col] - median) / IQR

        return df
