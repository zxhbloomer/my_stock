"""
因子筛选器工具（MLflow集成版）
根据IC分析结果自动筛选强因子

功能：
1. 从MLflow实验记录加载IC分析结果
2. 按阈值筛选强因子（IC > 0.01）
3. 生成因子配置供Handler使用
4. 导出因子清单和统计报告

改进：
- 与IC分析脚本统一使用MLflow管理
- 支持通过recorder_id或自动加载最新实验
- 无需CSV文件，直接从MLflow加载

作者：Claude Code
日期：2025-11-15
更新：2025-11-15（MLflow集成）
"""
import os
import pandas as pd
from typing import List, Dict, Tuple, Optional


class FactorSelector:
    """因子筛选器（MLflow集成版）"""

    def __init__(self):
        """初始化因子筛选器（从MLflow自动加载最新IC分析结果）"""
        self.ic_threshold = 0.01
        self.experiment_name = 'ic_analysis'
        self.recorder_id = None
        self.ic_data = None
        self.selected_factors = None

    def load_ic_results(self) -> pd.DataFrame:
        """
        加载IC分析结果（仅从MLflow加载）

        Returns:
            DataFrame: IC分析结果
        """
        from qlib.workflow import R
        from qlib.workflow.recorder import Recorder

        if self.recorder_id:
            # 使用指定的recorder_id
            recorder = R.get_recorder(
                recorder_id=self.recorder_id,
                experiment_name=self.experiment_name
            )
            print(f"[OK] 使用指定的MLflow记录: {self.recorder_id}")
        else:
            # 自动使用最新的recorder
            recorders = Recorder.list_recorders(experiment_name=self.experiment_name)
            if not recorders:
                raise ValueError(
                    f"[ERROR] 实验 '{self.experiment_name}' 中没有找到任何运行记录\n"
                    f"请先运行 IC 分析:\n"
                    f"  python scripts/20_ic_analysis.py --pool csi300\n"
                    f"或指定已有的 recorder_id"
                )

            # 按开始时间降序排序，取最新的
            recorder = sorted(
                recorders,
                key=lambda r: r.info.get('start_time', 0),
                reverse=True
            )[0]
            self.recorder_id = recorder.id
            print(f"[OK] 自动使用最新的MLflow记录: {self.recorder_id}")

        # 从MLflow加载IC分析数据
        self.ic_data = recorder.load_object('ic_analysis_full')
        print(f"[OK] 已从MLflow加载 {len(self.ic_data)} 个因子的IC分析结果")

        return self.ic_data

    def select_strong_factors(self) -> pd.DataFrame:
        """
        筛选强因子

        Returns:
            DataFrame: 强因子列表
        """
        if self.ic_data is None:
            self.load_ic_results()

        # 筛选条件：|IC_mean| > threshold
        self.selected_factors = self.ic_data[
            abs(self.ic_data['ic_mean']) > self.ic_threshold
        ].copy()

        # 按IC均值降序排序
        self.selected_factors = self.selected_factors.sort_values(
            'ic_mean',
            ascending=False
        )

        print(f"[OK] 筛选出 {len(self.selected_factors)} 个强因子")
        print(f"   - 阈值: |IC| > {self.ic_threshold}")
        print(f"   - IC均值: {self.selected_factors['ic_mean'].mean():.4f}")
        print(f"   - IC标准差: {self.selected_factors['ic_std'].mean():.4f}")

        return self.selected_factors

    def get_factor_expressions_by_library(
        self,
        library: str
    ) -> List[str]:
        """
        按因子库获取因子表达式

        Args:
            library: 因子库名称（Alpha158, AlphaFactors, ChinaMarketFactors）

        Returns:
            list: 因子表达式列表
        """
        if self.selected_factors is None:
            self.select_strong_factors()

        # 筛选特定库的因子
        library_factors = self.selected_factors[
            self.selected_factors['library'] == library
        ]

        # 获取因子名称（需要从原始因子库映射到表达式）
        factor_names = library_factors['factor_name'].tolist()

        print(f"\\n{library} 强因子：{len(factor_names)} 个")

        return factor_names

    def get_all_strong_factor_expressions(self) -> Dict[str, List[str]]:
        """
        获取所有强因子的表达式（按库分组）

        Returns:
            dict: {库名: [因子表达式列表]}
        """
        if self.selected_factors is None:
            self.select_strong_factors()

        result = {}

        # 从Alpha158获取强因子
        from qlib.contrib.data.handler import Alpha158
        alpha158_handler = Alpha158()
        alpha158_all = alpha158_handler.get_feature_config()

        alpha158_names = self.get_factor_expressions_by_library('Alpha158')
        # 提取索引
        alpha158_indices = [
            int(name.replace('Alpha158_', '')) - 1
            for name in alpha158_names
        ]
        result['Alpha158'] = [alpha158_all[i] for i in alpha158_indices]

        # 从AlphaFactors获取强因子
        from factors.alpha_factors import AlphaFactors
        alpha_all = AlphaFactors.get_all_features()
        alpha_name_list = AlphaFactors.get_feature_names()

        alpha_names = self.get_factor_expressions_by_library('AlphaFactors')
        # 提取因子名称后缀
        alpha_suffixes = [
            name.replace('AlphaFactor_', '')
            for name in alpha_names
        ]
        alpha_indices = [
            alpha_name_list.index(suffix)
            for suffix in alpha_suffixes
        ]
        result['AlphaFactors'] = [alpha_all[i] for i in alpha_indices]

        # 从ChinaMarketFactors获取强因子
        from factors.china_market_factors import ChinaMarketFactors
        china_all = ChinaMarketFactors.get_all_features()
        china_name_list = ChinaMarketFactors.get_feature_names()

        china_names = self.get_factor_expressions_by_library('ChinaMarketFactors')
        china_suffixes = [
            name.replace('ChinaFactor_', '')
            for name in china_names
        ]
        china_indices = [
            china_name_list.index(suffix)
            for suffix in china_suffixes
        ]
        result['ChinaMarketFactors'] = [china_all[i] for i in china_indices]

        # 统计
        total = sum(len(v) for v in result.values())
        print(f"\\n📊 强因子统计：")
        for lib, factors in result.items():
            print(f"   - {lib}: {len(factors)} 个")
        print(f"   - 总计: {total} 个")

        return result

    def get_feature_config_for_handler(self) -> List[str]:
        """
        获取Handler所需的特征配置列表

        Returns:
            list: 所有强因子表达式的列表
        """
        strong_factors = self.get_all_strong_factor_expressions()

        # 合并所有库的因子
        all_features = []
        for factors in strong_factors.values():
            all_features.extend(factors)

        # 去重
        all_features = list(set(all_features))

        print(f"\\n[OK] 生成Handler特征配置: {len(all_features)} 个因子")

        return all_features


# 命令行使用示例
if __name__ == "__main__":
    """命令行运行示例（MLflow集成版）"""

    # 创建筛选器（自动从MLflow加载最新IC分析结果）
    selector = FactorSelector()

    # 加载并筛选因子
    selector.load_ic_results()
    selector.select_strong_factors()

    # 显示因子配置
    print("\n" + "="*80)
    print("Handler特征配置")
    print("="*80)
    features = selector.get_feature_config_for_handler()
    print(f"\n共 {len(features)} 个强因子，示例前5个：")
    for i, feat in enumerate(features[:5], 1):
        print(f"{i}. {feat}")
    print("...")
    print(f"\n使用方法:")
    print(f"  from utils.factor_selector import FactorSelector")
    print(f"  selector = FactorSelector()")
    print(f"  features = selector.get_feature_config_for_handler()")


