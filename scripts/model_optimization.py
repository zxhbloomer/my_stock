"""
LightGBM参数优化脚本
使用贝叶斯优化（Bayesian Optimization）调优LightGBM参数

目标：
- 最大化IC均值
- 提升预测准确率
- 减少过拟合风险

优化参数：
- num_leaves: 叶子节点数（控制模型复杂度）
- learning_rate: 学习率
- feature_fraction: 特征采样率
- bagging_fraction: 样本采样率
- max_depth: 树的最大深度
- min_data_in_leaf: 叶子节点最小样本数

作者：Claude Code
日期：2025-11-15
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Tuple

# Qlib
import qlib
from qlib.contrib.model.gbdt import LGBModel
from qlib.data.dataset import DatasetH
from qlib.utils import init_instance_by_config
from qlib.workflow import R

# 贝叶斯优化
try:
    from bayes_opt import BayesianOptimization
    BAYES_OPT_AVAILABLE = True
except ImportError:
    print("⚠️ bayesian-optimization未安装")
    print("   请运行: pip install bayesian-optimization")
    BAYES_OPT_AVAILABLE = False


class LightGBMOptimizer:
    """LightGBM参数优化器"""

    def __init__(
        self,
        dataset_config: Dict[str, Any],
        train_start='2008-01-01',
        train_end='2014-12-31',
        valid_start='2015-01-01',
        valid_end='2016-12-31'
    ):
        """
        初始化优化器

        Args:
            dataset_config: 数据集配置
            train_start: 训练开始时间
            train_end: 训练结束时间
            valid_start: 验证开始时间
            valid_end: 验证结束时间
        """
        self.dataset_config = dataset_config
        self.train_start = train_start
        self.train_end = train_end
        self.valid_start = valid_start
        self.valid_end = valid_end

        # 初始化数据集
        self.dataset = None
        self.best_params = None
        self.best_score = -np.inf
        self.optimization_history = []

    def load_dataset(self) -> None:
        """加载数据集"""
        self.dataset = init_instance_by_config(self.dataset_config)
        print("✅ 数据集加载完成")

    def objective_function(
        self,
        num_leaves,
        learning_rate,
        feature_fraction,
        bagging_fraction,
        max_depth,
        min_data_in_leaf
    ) -> float:
        """
        目标函数（IC均值）

        Args:
            num_leaves: 叶子节点数
            learning_rate: 学习率
            feature_fraction: 特征采样率
            bagging_fraction: 样本采样率
            max_depth: 最大深度
            min_data_in_leaf: 叶子最小样本数

        Returns:
            float: IC均值（越大越好）
        """
        # 参数转换（贝叶斯优化要求浮点数，需转为整数）
        num_leaves = int(num_leaves)
        max_depth = int(max_depth)
        min_data_in_leaf = int(min_data_in_leaf)

        # 构建LightGBM配置
        model_config = {
            'class': 'LGBModel',
            'module_path': 'qlib.contrib.model.gbdt',
            'kwargs': {
                'loss': 'mse',
                'num_leaves': num_leaves,
                'learning_rate': learning_rate,
                'feature_fraction': feature_fraction,
                'bagging_fraction': bagging_fraction,
                'max_depth': max_depth,
                'min_data_in_leaf': min_data_in_leaf,
                'verbosity': -1
            }
        }

        try:
            # 训练模型
            model = init_instance_by_config(model_config)
            model.fit(self.dataset)

            # 预测验证集
            pred = model.predict(self.dataset)

            # 计算IC（Spearman相关系数）
            from scipy.stats import spearmanr

            # 获取验证集数据
            valid_pred = pred.loc(axis=0)[self.valid_start:self.valid_end]
            valid_label = self.dataset.prepare('valid', col_set='label')

            # 对齐索引
            common_idx = valid_pred.index.intersection(valid_label.index)
            valid_pred = valid_pred.loc[common_idx]
            valid_label = valid_label.loc[common_idx]

            # 计算每日IC
            ic_list = []
            for date in valid_pred.index.get_level_values('datetime').unique():
                daily_pred = valid_pred.xs(date, level='datetime')
                daily_label = valid_label.xs(date, level='datetime')

                # 对齐
                common_stocks = daily_pred.index.intersection(daily_label.index)
                if len(common_stocks) > 10:
                    pred_values = daily_pred.loc[common_stocks].values.ravel()
                    label_values = daily_label.loc[common_stocks].values.ravel()

                    # 去除NaN
                    mask = ~(np.isnan(pred_values) | np.isnan(label_values))
                    if mask.sum() > 10:
                        ic, _ = spearmanr(pred_values[mask], label_values[mask])
                        ic_list.append(ic)

            # IC均值
            ic_mean = np.mean(ic_list) if len(ic_list) > 0 else -1.0

            # 记录历史
            self.optimization_history.append({
                'num_leaves': num_leaves,
                'learning_rate': learning_rate,
                'feature_fraction': feature_fraction,
                'bagging_fraction': bagging_fraction,
                'max_depth': max_depth,
                'min_data_in_leaf': min_data_in_leaf,
                'ic_mean': ic_mean
            })

            print(f"   IC={ic_mean:.4f} | leaves={num_leaves}, lr={learning_rate:.4f}, "
                  f"feat_frac={feature_fraction:.2f}, bag_frac={bagging_fraction:.2f}")

            return ic_mean

        except Exception as e:
            print(f"   ❌ 训练失败: {e}")
            return -1.0  # 失败返回最差分数

    def optimize(
        self,
        n_iter=30,
        init_points=5
    ) -> Dict[str, Any]:
        """
        执行贝叶斯优化

        Args:
            n_iter: 优化迭代次数
            init_points: 初始随机探索点数

        Returns:
            dict: 最优参数
        """
        if not BAYES_OPT_AVAILABLE:
            raise ImportError("请先安装bayesian-optimization")

        if self.dataset is None:
            self.load_dataset()

        print("\\n" + "="*80)
        print("开始LightGBM参数优化")
        print("="*80)
        print(f"优化目标: 最大化IC均值（验证集{self.valid_start}至{self.valid_end}）")
        print(f"优化方法: 贝叶斯优化")
        print(f"迭代次数: {n_iter}")
        print(f"初始探索: {init_points}\\n")

        # 定义参数空间
        pbounds = {
            'num_leaves': (20, 100),           # 叶子节点数
            'learning_rate': (0.01, 0.3),      # 学习率
            'feature_fraction': (0.6, 1.0),    # 特征采样率
            'bagging_fraction': (0.6, 1.0),    # 样本采样率
            'max_depth': (3, 10),              # 最大深度
            'min_data_in_leaf': (10, 100)      # 叶子最小样本数
        }

        # 创建优化器
        optimizer = BayesianOptimization(
            f=self.objective_function,
            pbounds=pbounds,
            random_state=42,
            verbose=0
        )

        # 执行优化
        optimizer.maximize(
            init_points=init_points,
            n_iter=n_iter
        )

        # 提取最优参数
        best_params = optimizer.max['params']
        best_params['num_leaves'] = int(best_params['num_leaves'])
        best_params['max_depth'] = int(best_params['max_depth'])
        best_params['min_data_in_leaf'] = int(best_params['min_data_in_leaf'])

        self.best_params = best_params
        self.best_score = optimizer.max['target']

        print("\\n" + "="*80)
        print("优化完成！")
        print("="*80)
        print(f"\\n🏆 最优IC均值: {self.best_score:.4f}")
        print(f"\\n📋 最优参数：")
        for param, value in best_params.items():
            print(f"   - {param}: {value}")

        return best_params

    def save_results(
        self,
        output_path=None
    ) -> None:
        """
        保存优化结果

        Args:
            output_path: 输出文件路径
        """
        # 默认保存到项目根目录的docs目录
        if output_path is None:
            project_root = Path(__file__).parent.parent
            output_path = project_root / 'docs' / 'lightgbm_optimization_results.txt'

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\\n")
            f.write("LightGBM参数优化结果\\n")
            f.write("="*80 + "\\n\\n")

            f.write(f"优化时间: {datetime.now()}\\n")
            f.write(f"验证集: {self.valid_start} ~ {self.valid_end}\\n")
            f.write(f"优化迭代: {len(self.optimization_history)}\\n\\n")

            f.write(f"🏆 最优IC均值: {self.best_score:.4f}\\n\\n")

            f.write("📋 最优参数配置：\\n")
            f.write("```yaml\\n")
            f.write("model:\\n")
            f.write("  class: LGBModel\\n")
            f.write("  module_path: qlib.contrib.model.gbdt\\n")
            f.write("  kwargs:\\n")
            for param, value in self.best_params.items():
                f.write(f"    {param}: {value}\\n")
            f.write("```\\n\\n")

            # 优化历史（Top 10）
            history_df = pd.DataFrame(self.optimization_history)
            history_df = history_df.sort_values('ic_mean', ascending=False)

            f.write("📊 优化历史（Top 10）：\\n")
            f.write(history_df.head(10).to_string(index=False))
            f.write("\\n\\n")

            f.write("="*80 + "\\n")

        print(f"\\n[OK] 优化结果已保存至: {output_path}")

        # 同时保存为CSV
        csv_path = output_path.parent / output_path.name.replace('.txt', '.csv')
        history_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"[OK] 优化历史已保存至: {csv_path}")


# 命令行运行
if __name__ == "__main__":
    """命令行使用示例"""
    import argparse

    parser = argparse.ArgumentParser(description='LightGBM参数优化')
    parser.add_argument(
        '--n-iter',
        type=int,
        default=30,
        help='优化迭代次数（默认30）'
    )
    parser.add_argument(
        '--init-points',
        type=int,
        default=5,
        help='初始随机探索点数（默认5）'
    )
    parser.add_argument(
        '--instruments',
        type=str,
        default='csi300',
        help='股票池（默认csi300）'
    )

    args = parser.parse_args()

    # 初始化Qlib
    print("初始化Qlib...")
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')

    # 数据集配置（使用OptimizedHandler）
    dataset_config = {
        'class': 'DatasetH',
        'module_path': 'qlib.data.dataset',
        'kwargs': {
            'handler': {
                'class': 'OptimizedHandler',
                'module_path': 'handlers.optimized_handler',
                'kwargs': {
                    'instruments': args.instruments,
                    'start_time': '2008-01-01',
                    'end_time': '2020-12-31',
                    'fit_start_time': '2008-01-01',
                    'fit_end_time': '2014-12-31',
                    'ic_threshold': 0.01,
                    'use_factor_selector': True
                }
            },
            'segments': {
                'train': ('2008-01-01', '2014-12-31'),
                'valid': ('2015-01-01', '2016-12-31'),
                'test': ('2017-01-01', '2020-12-31')
            }
        }
    }

    # 创建优化器
    optimizer = LightGBMOptimizer(
        dataset_config=dataset_config,
        train_start='2008-01-01',
        train_end='2014-12-31',
        valid_start='2015-01-01',
        valid_end='2016-12-31'
    )

    # 执行优化
    best_params = optimizer.optimize(
        n_iter=args.n_iter,
        init_points=args.init_points
    )

    # 保存结果
    optimizer.save_results()

    print("\\n[OK] 参数优化完成！")
    print("\\n下一步：")
    print("   1. 将最优参数更新到 configs/workflow_config_custom.yaml")
    print("   2. 运行完整workflow验证性能提升")
