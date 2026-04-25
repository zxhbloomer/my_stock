"""
LightGBM参数优化脚本（改进版）
基于Qlib官方最佳实践 + Bayesian Optimization

改进点：
1. 修复路径问题（添加项目根目录到sys.path）
2. 使用官方推荐的参数范围
3. 优化IC计算方法
4. 添加更详细的结果分析
5. 支持直接生成可用的YAML配置

使用方法：
    python scripts/参数优化_改进版.py --n-iter 30
    python scripts/参数优化_改进版.py --n-iter 50 --instruments csi500

作者：基于Qlib官方实践改进
日期：2025-11-16
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径 (从 scripts/30_模型训练/ 回到根目录)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any
import yaml

# Qlib
import qlib
from qlib.contrib.model.gbdt import LGBModel
from qlib.data.dataset import DatasetH
from qlib.utils import init_instance_by_config

# 贝叶斯优化
try:
    from bayes_opt import BayesianOptimization
    BAYES_OPT_AVAILABLE = True
except ImportError:
    print("[ERROR] bayesian-optimization未安装")
    print("   请运行: pip install bayesian-optimization")
    BAYES_OPT_AVAILABLE = False


class ImprovedLightGBMOptimizer:
    """改进版LightGBM参数优化器（基于Qlib官方实践）"""

    def __init__(
        self,
        config_path=None,  # 配置文件路径(YAML格式)。如指定,则从中读取handler配置
        instruments='csi300',
        train_start='2008-01-01',
        train_end='2014-12-31',
        valid_start='2015-01-01',
        valid_end='2016-12-31'
    ):
        self.config_path = config_path
        self.instruments = instruments
        self.train_start = train_start
        self.train_end = train_end
        self.valid_start = valid_start
        self.valid_end = valid_end
        self.dataset = None
        self.best_params = None
        self.best_score = None
        self.optimization_history = []
        self.handler_config = None  # 保存从YAML读取的handler配置或默认Alpha158配置

    def load_dataset(self):
        """
        加载数据集

        加载逻辑:
        1. 如果指定了config_path,从YAML配置文件读取handler配置
        2. 如果未指定config_path,使用默认的Alpha158配置(向后兼容)
        3. 使用Qlib的init_instance_by_config自动识别handler类型并初始化
        """
        print("加载数据集...")

        # 如果指定了配置文件,从中读取handler配置
        if self.config_path:
            print(f"从配置文件读取handler: {self.config_path}")

            # 检查配置文件是否存在
            if not Path(self.config_path).exists():
                raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

            # 读取YAML配置
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 提取handler配置(完整的handler定义)
            self.handler_config = config['task']['dataset']['kwargs']['handler']

            # 更新instruments(使用配置文件中的值,优先级高于命令行参数)
            if 'instruments' in self.handler_config['kwargs']:
                self.instruments = self.handler_config['kwargs']['instruments']
                print(f"  使用配置中的股票池: {self.instruments}")

            print(f"  Handler类型: {self.handler_config['class']}")

        else:
            # 默认使用Alpha158(向后兼容)
            print("未指定配置文件,使用默认Alpha158 handler")
            self.handler_config = {
                'class': 'Alpha158',
                'module_path': 'qlib.contrib.data.handler',
                'kwargs': {
                    'instruments': self.instruments,
                    'start_time': '2008-01-01',
                    'end_time': '2025-11-14',        # 更新为最新数据日期
                    'fit_start_time': '2015-01-01',  # 更新拟合开始时间
                    'fit_end_time': '2022-12-31',    # 避免测试期泄漏
                    'infer_processors': [
                        {
                            'class': 'RobustZScoreNorm',
                            'kwargs': {'fields_group': 'feature', 'clip_outlier': True}
                        },
                        {'class': 'Fillna', 'kwargs': {'fields_group': 'feature'}}
                    ],
                    'learn_processors': [
                        {'class': 'DropnaLabel'},
                        {'class': 'CSRankNorm', 'kwargs': {'fields_group': 'label'}}
                    ],
                    'label': ['Ref($close, -2) / Ref($close, -1) - 1']
                }
            }

        # 构建dataset配置(使用读取的或默认的handler配置)
        dataset_config = {
            'class': 'DatasetH',
            'module_path': 'qlib.data.dataset',
            'kwargs': {
                'handler': self.handler_config,  # 使用从YAML读取的配置或默认Alpha158
                'segments': {
                    'train': (self.train_start, self.train_end),
                    'valid': (self.valid_start, self.valid_end),
                    'test': ('2017-01-01', '2020-12-31')
                }
            }
        }

        # 使用Qlib的init_instance_by_config初始化dataset
        # 该函数会自动识别handler类型(Alpha158或DataHandlerLP)并正确初始化
        self.dataset = init_instance_by_config(dataset_config)
        print("[OK] 数据集加载完成")

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
        优化目标函数：最大化IC均值

        Returns:
            float: IC均值（验证集）
        """
        # 构建参数配置（参考Qlib官方推荐范围）
        params = {
            'num_leaves': int(num_leaves),
            'learning_rate': learning_rate,
            'feature_fraction': feature_fraction,
            'bagging_fraction': bagging_fraction,
            'max_depth': int(max_depth),
            'min_data_in_leaf': int(min_data_in_leaf),
            # 固定参数（来自Qlib官方配置）
            'loss': 'mse',
            'colsample_bytree': 0.8879,
            'subsample': 0.8789,
            'lambda_l1': 205.6999,
            'lambda_l2': 580.9768,
            'num_threads': 20,
            'verbosity': -1
        }

        try:
            # 训练模型
            model = LGBModel(**params)
            model.fit(self.dataset)

            # 在验证集上预测
            pred = model.predict(self.dataset, segment='valid')
            label = self.dataset.prepare('valid', col_set='label')

            # 计算IC（Information Coefficient）
            merged = pd.concat([label, pred], axis=1, sort=True).reindex(label.index)
            if isinstance(merged.columns, pd.MultiIndex):
                merged.columns = ['label', 'score']
            else:
                merged.columns = ['label', 'score']

            # 计算每日IC
            ic_series = merged.groupby(level=0).apply(
                lambda x: x['label'].corr(x['score'])
            )
            ic_mean = ic_series.mean()
            ic_std = ic_series.std()
            ic_ir = ic_mean / ic_std if ic_std > 0 else 0  # IC Information Ratio

            # 记录历史
            self.optimization_history.append({
                'iteration': len(self.optimization_history) + 1,
                'num_leaves': int(num_leaves),
                'learning_rate': learning_rate,
                'feature_fraction': feature_fraction,
                'bagging_fraction': bagging_fraction,
                'max_depth': int(max_depth),
                'min_data_in_leaf': int(min_data_in_leaf),
                'ic_mean': ic_mean,
                'ic_std': ic_std,
                'ic_ir': ic_ir
            })

            print(f"  迭代 {len(self.optimization_history)}: IC均值={ic_mean:.4f}, IC_IR={ic_ir:.2f} | "
                  f"num_leaves={int(num_leaves)}, lr={learning_rate:.3f}")

            return ic_mean

        except Exception as e:
            print(f"[WARNING] 训练失败: {e}")
            return -1.0

    def optimize(self, n_iter=30, init_points=5) -> Dict[str, Any]:
        """
        执行贝叶斯优化

        Args:
            n_iter: 优化迭代次数
            init_points: 初始随机探索点数

        Returns:
            dict: 最优参数
        """
        if not BAYES_OPT_AVAILABLE:
            raise ImportError("请先安装bayesian-optimization: pip install bayesian-optimization")

        if self.dataset is None:
            self.load_dataset()

        print("\n" + "="*80)
        print("LightGBM参数优化（改进版 - 基于Qlib官方实践）")
        print("="*80)
        print(f"优化目标: 最大化IC均值（验证集{self.valid_start}至{self.valid_end}）")
        print(f"优化方法: 贝叶斯优化（Gaussian Process）")
        print(f"股票池: {self.instruments}")
        print(f"迭代次数: {n_iter}")
        print(f"初始探索: {init_points}\n")

        # 定义参数空间（参考Qlib官方推荐范围）
        pbounds = {
            'num_leaves': (20, 210),           # Qlib官方使用210
            'learning_rate': (0.01, 0.3),      # Qlib官方使用0.2
            'feature_fraction': (0.6, 1.0),    # 特征采样率
            'bagging_fraction': (0.6, 1.0),    # 样本采样率
            'max_depth': (3, 10),              # Qlib官方使用8
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
        print("开始优化...")
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

        print("\n" + "="*80)
        print("优化完成！")
        print("="*80)
        print(f"\n🏆 最优IC均值: {self.best_score:.4f}")
        print(f"\n📋 最优参数：")
        for param, value in best_params.items():
            print(f"   - {param}: {value}")

        # 找到最优参数对应的IC_IR
        best_record = [r for r in self.optimization_history if r['ic_mean'] == self.best_score]
        if best_record:
            print(f"\n📊 最优参数的其他指标：")
            print(f"   - IC标准差: {best_record[0]['ic_std']:.4f}")
            print(f"   - IC信息比率: {best_record[0]['ic_ir']:.2f}")

        return best_params

    def save_results(self, output_path=None) -> None:
        """保存优化结果"""
        if output_path is None:
            project_root = Path(__file__).parent.parent.parent
            output_path = project_root / 'docs' / 'lightgbm_optimization_results_improved.txt'

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("LightGBM参数优化结果（改进版 - 基于Qlib官方实践）\n")
            f.write("="*80 + "\n\n")

            f.write(f"优化时间: {datetime.now()}\n")
            f.write(f"股票池: {self.instruments}\n")
            f.write(f"验证集: {self.valid_start} ~ {self.valid_end}\n")
            f.write(f"优化迭代: {len(self.optimization_history)}\n")

            # 显示handler类型
            if self.handler_config:
                handler_class = self.handler_config.get('class', 'Unknown')
                f.write(f"Handler类型: {handler_class}\n")
            f.write("\n")

            f.write(f"🏆 最优IC均值: {self.best_score:.4f}\n\n")

            # 找到最优记录
            best_record = [r for r in self.optimization_history if r['ic_mean'] == self.best_score]
            if best_record:
                f.write(f"📊 最优参数的详细指标：\n")
                f.write(f"   - IC均值: {best_record[0]['ic_mean']:.4f}\n")
                f.write(f"   - IC标准差: {best_record[0]['ic_std']:.4f}\n")
                f.write(f"   - IC信息比率: {best_record[0]['ic_ir']:.2f}\n\n")

            f.write("📋 最优参数配置（可直接复制到YAML）：\n")
            f.write("```yaml\n")
            f.write("task:\n")
            f.write("  model:\n")
            f.write("    class: LGBModel\n")
            f.write("    module_path: qlib.contrib.model.gbdt\n")
            f.write("    kwargs:\n")
            f.write("      loss: mse\n")
            f.write("      colsample_bytree: 0.8879\n")
            f.write("      subsample: 0.8789\n")
            f.write("      lambda_l1: 205.6999\n")
            f.write("      lambda_l2: 580.9768\n")
            for param, value in self.best_params.items():
                f.write(f"      {param}: {value}\n")
            f.write("      num_threads: 20\n")
            f.write("```\n\n")

            # 优化历史（Top 10）
            history_df = pd.DataFrame(self.optimization_history)
            history_df = history_df.sort_values('ic_mean', ascending=False)

            f.write("📊 优化历史（Top 10）：\n")
            f.write(history_df.head(10).to_string(index=False))
            f.write("\n\n")

            f.write("="*80 + "\n")

        print(f"\n[OK] 优化结果已保存至: {output_path}")

        # 同时保存为CSV
        csv_path = output_path.parent / output_path.name.replace('.txt', '.csv')
        history_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
        print(f"[OK] 优化历史已保存至: {csv_path}")

        # 生成可直接使用的YAML配置文件
        # 如果指定了config_path,生成基于原配置文件名的优化版本
        if self.config_path:
            base_name = Path(self.config_path).stem
            yaml_path = output_path.parent.parent / 'configs' / f'{base_name}_optimized.yaml'
        else:
            yaml_path = output_path.parent.parent / 'configs' / f'workflow_config_optimized_{self.instruments}.yaml'

        self.generate_yaml_config(yaml_path)

    def generate_yaml_config(self, yaml_path):
        """
        生成可直接使用的YAML配置文件

        生成逻辑:
        1. 如果指定了config_path,基于原始配置文件生成(保留handler配置)
        2. 如果未指定config_path,生成默认Alpha158配置
        3. 更新模型参数为优化后的最优参数
        """
        yaml_path = Path(yaml_path)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        # 将NumPy类型转换为Python原生类型(避免YAML序列化问题)
        best_params_native = {}
        for key, value in self.best_params.items():
            if isinstance(value, np.integer):
                best_params_native[key] = int(value)
            elif isinstance(value, np.floating):
                best_params_native[key] = float(value)
            else:
                best_params_native[key] = value

        # 如果指定了原始配置文件,基于它生成优化版本
        if self.config_path:
            print(f"基于配置文件生成优化版本: {self.config_path}")

            # 读取原始配置
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)

            # 更新模型参数(保留原有handler配置)
            config['task']['model']['kwargs'].update(best_params_native)
            config['task']['model']['kwargs']['num_threads'] = 20

        else:
            # 生成默认Alpha158配置
            print("生成默认Alpha158配置")
            config = {
                'qlib_init': {
                    'provider_uri': 'D:/Data/my_stock',
                    'region': 'cn'
                },
                'market': self.instruments,
                'benchmark': 'SH000300' if self.instruments == 'csi300' else 'SH000905',
                'data_handler_config': {
                    'start_time': '2008-01-01',
                    'end_time': '2025-11-14',        # 更新为最新数据日期
                    'fit_start_time': '2015-01-01',  # 更新拟合开始时间
                    'fit_end_time': '2022-12-31',    # 避免测试期泄漏
                    'instruments': self.instruments
                },
                'port_analysis_config': {
                    'strategy': {
                        'class': 'TopkDropoutStrategy',
                        'module_path': 'qlib.contrib.strategy',
                        'kwargs': {
                            'signal': '<PRED>',
                            'topk': 50,
                            'n_drop': 5
                        }
                    },
                    'backtest': {
                        'start_time': '2025-01-01',  # 回测使用最新一年
                        'end_time': '2025-11-14',    # 更新为最新数据日期
                        'account': 100000000,
                        'benchmark': 'SH000300' if self.instruments == 'csi300' else 'SH000905',
                        'exchange_kwargs': {
                            'limit_threshold': 0.095,
                            'deal_price': 'close',
                            'open_cost': 0.0005,
                            'close_cost': 0.0015,
                            'min_cost': 5
                        }
                    }
                },
                'task': {
                    'model': {
                        'class': 'LGBModel',
                        'module_path': 'qlib.contrib.model.gbdt',
                        'kwargs': {
                            'loss': 'mse',
                            'colsample_bytree': 0.8879,
                            'subsample': 0.8789,
                            'lambda_l1': 205.6999,
                            'lambda_l2': 580.9768,
                            **best_params_native,
                            'num_threads': 20
                        }
                    },
                    'dataset': {
                        'class': 'DatasetH',
                        'module_path': 'qlib.data.dataset',
                        'kwargs': {
                            'handler': self.handler_config,  # 使用保存的handler配置
                            'segments': {
                                'train': ['2015-01-01', '2022-12-31'],  # 8年训练期
                                'valid': ['2023-01-01', '2024-12-31'],  # 2年验证期
                                'test': ['2025-01-01', '2025-11-14']    # 最新年份测试
                            }
                        }
                    },
                    'record': [
                        {
                            'class': 'SignalRecord',
                            'module_path': 'qlib.workflow.record_temp',
                            'kwargs': {}
                        },
                        {
                            'class': 'SigAnaRecord',
                            'module_path': 'qlib.workflow.record_temp',
                            'kwargs': {
                                'ana_long_short': False,
                                'ann_scaler': 252
                            }
                        },
                        {
                            'class': 'PortAnaRecord',
                            'module_path': 'qlib.workflow.record_temp',
                            'kwargs': {
                                'config': '<PORT_ANALYSIS_CONFIG>'
                            }
                        }
                    ]
                }
            }

        # 保存配置到YAML文件
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, allow_unicode=True, sort_keys=False)

        print(f"[OK] 已生成可用配置文件: {yaml_path}")
        print(f"\n💡 可直接运行: python scripts/30_运行工作流.py {yaml_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='LightGBM参数优化(支持任意配置文件)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 方式1: 优化Alpha158因子(默认,向后兼容)
  python scripts/参数优化_改进版.py --n-iter 30

  # 方式2: 优化Top50因子
  python scripts/参数优化_改进版.py --config configs/workflow_config_top50.yaml --n-iter 30

  # 方式3: 优化自定义配置
  python scripts/参数优化_改进版.py --config configs/my_custom_config.yaml --n-iter 50
        """
    )
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='配置文件路径(YAML格式)。如不指定则使用默认Alpha158配置'
    )
    parser.add_argument('--n-iter', type=int, default=30, help='优化迭代次数(默认30)')
    parser.add_argument('--init-points', type=int, default=5, help='初始随机探索点数(默认5)')
    parser.add_argument(
        '--instruments',
        type=str,
        default='csi300',
        help='股票池(仅在不指定--config时有效,默认csi300)'
    )

    args = parser.parse_args()

    # 初始化Qlib
    print("初始化Qlib...")
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')
    print("[OK] Qlib初始化完成\n")

    # 创建优化器
    # 使用更近期的数据进行参数优化：
    # - 训练集：2015-2022（8年，覆盖完整牛熊周期）
    # - 验证集：2023-2024（2年，用于参数调优）
    optimizer = ImprovedLightGBMOptimizer(
        config_path=args.config,  # 传入配置文件路径
        instruments=args.instruments,  # 如果有config,此参数会被配置覆盖
        train_start='2015-01-01',
        train_end='2022-12-31',
        valid_start='2023-01-01',
        valid_end='2024-12-31'
    )

    # 执行优化
    best_params = optimizer.optimize(
        n_iter=args.n_iter,
        init_points=args.init_points
    )

    # 保存结果
    optimizer.save_results()

    print("\n[OK] 参数优化完成!")
    print("\n📝 下一步操作:")
    print("   1. 查看优化结果: docs/lightgbm_optimization_results_improved.txt")

    # 根据是否指定config给出不同的运行建议
    if args.config:
        # 生成基于原配置的优化版本文件名
        base_name = Path(args.config).stem
        optimized_config = f"configs/{base_name}_optimized.yaml"
        print(f"   2. 使用优化后的配置: python scripts/30_运行工作流.py {optimized_config}")
    else:
        print(f"   2. 使用优化后的配置: python scripts/30_运行工作流.py configs/workflow_config_optimized_{args.instruments}.yaml")

    print("   3. 对比性能提升\n")
