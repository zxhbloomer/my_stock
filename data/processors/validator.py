"""
数据验证模块
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple


class DataValidator:
    """数据验证器"""

    @staticmethod
    def check_required_columns(df: pd.DataFrame, required_cols: List[str]) -> Tuple[bool, List[str]]:
        """
        检查必需列

        Args:
            df: 数据DataFrame
            required_cols: 必需列列表

        Returns:
            (是否通过, 缺失列列表)
        """
        missing_cols = [col for col in required_cols if col not in df.columns]
        return len(missing_cols) == 0, missing_cols

    @staticmethod
    def check_missing_values(df: pd.DataFrame, threshold: float = 0.5) -> Dict:
        """
        检查缺失值

        Args:
            df: 数据DataFrame
            threshold: 缺失率阈值（超过则警告）

        Returns:
            检查结果字典
        """
        missing_stats = {}
        total_rows = len(df)

        for col in df.columns:
            missing_count = df[col].isna().sum()
            missing_rate = missing_count / total_rows

            if missing_rate > 0:
                missing_stats[col] = {
                    'missing_count': missing_count,
                    'missing_rate': missing_rate,
                    'warning': missing_rate > threshold
                }

        return missing_stats

    @staticmethod
    def check_data_types(df: pd.DataFrame, expected_types: Dict) -> Dict:
        """
        检查数据类型

        Args:
            df: 数据DataFrame
            expected_types: 期望类型字典 {列名: 类型}

        Returns:
            类型不匹配的列
        """
        type_errors = {}

        for col, expected_type in expected_types.items():
            if col not in df.columns:
                type_errors[col] = f"列不存在"
                continue

            actual_type = df[col].dtype
            if not pd.api.types.is_dtype_equal(actual_type, expected_type):
                type_errors[col] = f"期望 {expected_type}, 实际 {actual_type}"

        return type_errors

    @staticmethod
    def check_date_continuity(df: pd.DataFrame, date_col: str = 'date',
                              freq: str = 'D') -> Dict:
        """
        检查日期连续性

        Args:
            df: 数据DataFrame
            date_col: 日期列名
            freq: 期望频率 (D/H/min)

        Returns:
            检查结果
        """
        if date_col not in df.columns:
            return {'error': f'日期列 {date_col} 不存在'}

        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col])
        df = df.sort_values(date_col)

        # 检查缺失的日期
        date_range = pd.date_range(
            start=df[date_col].min(),
            end=df[date_col].max(),
            freq=freq
        )

        missing_dates = date_range.difference(df[date_col])

        return {
            'total_dates': len(date_range),
            'actual_dates': len(df),
            'missing_dates': len(missing_dates),
            'missing_rate': len(missing_dates) / len(date_range),
            'first_missing_dates': missing_dates[:5].tolist() if len(missing_dates) > 0 else []
        }

    @staticmethod
    def check_price_validity(df: pd.DataFrame) -> Dict:
        """
        检查价格合理性

        Args:
            df: 数据DataFrame（包含 open, close, high, low）

        Returns:
            检查结果
        """
        issues = []

        # 检查价格是否为正
        price_cols = ['open', 'close', 'high', 'low']
        for col in price_cols:
            if col in df.columns:
                negative_count = (df[col] <= 0).sum()
                if negative_count > 0:
                    issues.append(f"{col} 有 {negative_count} 个非正值")

        # 检查最高价 >= 最低价
        if 'high' in df.columns and 'low' in df.columns:
            invalid_count = (df['high'] < df['low']).sum()
            if invalid_count > 0:
                issues.append(f"有 {invalid_count} 行 high < low")

        # 检查收盘价在最高最低价之间
        if all(col in df.columns for col in ['close', 'high', 'low']):
            invalid_count = ((df['close'] > df['high']) | (df['close'] < df['low'])).sum()
            if invalid_count > 0:
                issues.append(f"有 {invalid_count} 行 close 超出 [low, high] 范围")

        return {
            'valid': len(issues) == 0,
            'issues': issues
        }

    @staticmethod
    def check_volume(df: pd.DataFrame, volume_col: str = 'volume') -> Dict:
        """
        检查成交量

        Args:
            df: 数据DataFrame
            volume_col: 成交量列名

        Returns:
            检查结果
        """
        if volume_col not in df.columns:
            return {'error': f'成交量列 {volume_col} 不存在'}

        negative_count = (df[volume_col] < 0).sum()
        zero_count = (df[volume_col] == 0).sum()
        zero_rate = zero_count / len(df)

        return {
            'negative_count': negative_count,
            'zero_count': zero_count,
            'zero_rate': zero_rate,
            'mean_volume': df[volume_col].mean(),
            'median_volume': df[volume_col].median()
        }

    @staticmethod
    def generate_report(df: pd.DataFrame) -> str:
        """
        生成数据质量报告

        Args:
            df: 数据DataFrame

        Returns:
            报告文本
        """
        report = []
        report.append("=" * 60)
        report.append("数据质量检查报告")
        report.append("=" * 60)

        # 基本信息
        report.append(f"\n【基本信息】")
        report.append(f"总行数: {len(df)}")
        report.append(f"总列数: {len(df.columns)}")
        report.append(f"列名: {', '.join(df.columns)}")

        # 必需列检查
        required_cols = ['date', 'open', 'close', 'high', 'low', 'volume']
        passed, missing = DataValidator.check_required_columns(df, required_cols)
        report.append(f"\n【必需列检查】")
        if passed:
            report.append("✓ 所有必需列都存在")
        else:
            report.append(f"✗ 缺失列: {', '.join(missing)}")

        # 缺失值检查
        missing_stats = DataValidator.check_missing_values(df)
        report.append(f"\n【缺失值检查】")
        if missing_stats:
            for col, stats in missing_stats.items():
                warn = "⚠" if stats['warning'] else ""
                report.append(f"{warn} {col}: {stats['missing_count']} 个缺失 "
                            f"({stats['missing_rate']:.2%})")
        else:
            report.append("✓ 无缺失值")

        # 价格合理性检查
        price_check = DataValidator.check_price_validity(df)
        report.append(f"\n【价格合理性检查】")
        if price_check['valid']:
            report.append("✓ 价格数据合理")
        else:
            for issue in price_check['issues']:
                report.append(f"✗ {issue}")

        # 成交量检查
        volume_check = DataValidator.check_volume(df)
        report.append(f"\n【成交量检查】")
        if 'error' not in volume_check:
            report.append(f"负值数量: {volume_check['negative_count']}")
            report.append(f"零值数量: {volume_check['zero_count']} ({volume_check['zero_rate']:.2%})")
            report.append(f"平均成交量: {volume_check['mean_volume']:.2f}")

        report.append("\n" + "=" * 60)

        return "\n".join(report)
