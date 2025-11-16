"""
滚动窗口验证脚本 - 自动化多时间段回测

功能:
1. 自动滚动训练和测试时间窗口
2. 生成多期回测结果对比
3. 评估策略稳健性

使用方法:
    python scripts/50_滚动窗口验证.py --config configs/workflow_config_top50_optimized.yaml
    python scripts/50_滚动窗口验证.py --config configs/workflow_config_top50_optimized.yaml --train-years 6 --test-years 1

作者: 基于Qlib官方Rolling Benchmark改进
日期: 2025-11-16
"""
import sys
from pathlib import Path
import argparse
from datetime import datetime, timedelta
import yaml
import pandas as pd
import numpy as np
from scipy.stats import spearmanr
import qlib
from qlib.workflow import R
from qlib.utils import init_instance_by_config
from qlib.contrib.evaluate import risk_analysis

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


class RollingWindowBacktest:
    """滚动窗口回测管理器"""

    def __init__(self, config_path, train_years=6, valid_years=2, test_years=1):
        """
        初始化滚动窗口回测

        参数:
            config_path: 配置文件路径
            train_years: 训练窗口年数(默认6年)
            valid_years: 验证窗口年数(默认2年)
            test_years: 测试窗口年数(默认1年)
        """
        self.config_path = Path(config_path)
        self.train_years = train_years
        self.valid_years = valid_years
        self.test_years = test_years

        # 加载基础配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.base_config = yaml.safe_load(f)

        # 存储所有测试结果
        self.results = []

    def generate_rolling_periods(self, start_year=2008, end_year=2025):
        """
        生成滚动时间窗口

        返回:
            list: [(train_start, train_end, valid_start, valid_end, test_start, test_end), ...]
        """
        periods = []
        current_year = start_year

        while True:
            # 计算各个时间段
            train_start = f"{current_year}-01-01"
            train_end = f"{current_year + self.train_years - 1}-12-31"
            valid_start = f"{current_year + self.train_years}-01-01"
            valid_end = f"{current_year + self.train_years + self.valid_years - 1}-12-31"
            test_start = f"{current_year + self.train_years + self.valid_years}-01-01"
            test_end = f"{current_year + self.train_years + self.valid_years + self.test_years - 1}-12-31"

            # 检查是否超出范围
            test_end_year = int(test_end.split('-')[0])
            if test_end_year > end_year:
                break

            periods.append({
                'train': (train_start, train_end),
                'valid': (valid_start, valid_end),
                'test': (test_start, test_end),
                'name': f"Test_{test_start[:4]}"
            })

            # 滚动到下一年
            current_year += self.test_years

        return periods

    def run_single_period(self, period):
        """
        运行单个时间段的回测

        参数:
            period: 时间段配置字典

        返回:
            dict: 回测结果指标
        """
        print(f"\n{'='*80}")
        print(f"测试期: {period['test'][0]} 至 {period['test'][1]}")
        print(f"训练期: {period['train'][0]} 至 {period['train'][1]}")
        print(f"验证期: {period['valid'][0]} 至 {period['valid'][1]}")
        print(f"{'='*80}\n")

        # 复制配置并更新时间段
        config = self.base_config.copy()
        config['task']['dataset']['kwargs']['segments'] = {
            'train': [period['train'][0], period['train'][1]],
            'valid': [period['valid'][0], period['valid'][1]],
            'test': [period['test'][0], period['test'][1]]
        }

        # 更新handler时间范围
        if 'handler' in config['task']['dataset']['kwargs']:
            handler_kwargs = config['task']['dataset']['kwargs']['handler']['kwargs']
            handler_kwargs['start_time'] = period['train'][0]
            handler_kwargs['end_time'] = period['test'][1]
            if 'fit_start_time' in handler_kwargs:
                handler_kwargs['fit_start_time'] = period['train'][0]
            if 'fit_end_time' in handler_kwargs:
                handler_kwargs['fit_end_time'] = period['train'][1]

        try:
            # 创建实验并保存到MLflow
            exp_name = "rolling_validation"
            with R.start(experiment_name=exp_name):
                # 记录时间段参数
                R.log_params(
                    period_name=period['name'],
                    train_start=period['train'][0],
                    train_end=period['train'][1],
                    valid_start=period['valid'][0],
                    valid_end=period['valid'][1],
                    test_start=period['test'][0],
                    test_end=period['test'][1]
                )

                # 初始化模型和数据集
                model = init_instance_by_config(config['task']['model'])
                dataset = init_instance_by_config(config['task']['dataset'])

                # 训练模型
                print("训练模型...")
                model.fit(dataset)

                # 生成预测
                print("生成预测...")
                pred = model.predict(dataset)

                # 计算IC指标
                test_pred = pred.loc[period['test'][0]:period['test'][1]]
                test_label = dataset.prepare("test", col_set="label")

                # 计算每日IC - 使用与model_optimization.py相同的方法
                ic_list = []
                for date in test_pred.index.get_level_values('datetime').unique():
                    daily_pred = test_pred.xs(date, level='datetime')
                    daily_label = test_label.xs(date, level='datetime')

                    # 对齐股票
                    common_stocks = daily_pred.index.intersection(daily_label.index)
                    if len(common_stocks) > 10:
                        pred_values = daily_pred.loc[common_stocks].values.ravel()
                        label_values = daily_label.loc[common_stocks].values.ravel()

                        # 去除NaN
                        mask = ~(pd.isna(pred_values) | pd.isna(label_values))
                        if mask.sum() > 10:
                            # 计算Spearman相关系数(Rank IC)
                            ic, _ = spearmanr(pred_values[mask], label_values[mask])
                            if not pd.isna(ic):
                                ic_list.append(ic)

                if len(ic_list) == 0:
                    print("⚠️ 警告: 测试集无有效IC数据")
                    return None

                daily_ic = pd.Series(ic_list)

                # 汇总指标
                results = {
                    'period': period['name'],
                    'test_start': period['test'][0],
                    'test_end': period['test'][1],
                    'ic_mean': daily_ic.mean(),
                    'ic_std': daily_ic.std(),
                    'ic_ir': daily_ic.mean() / daily_ic.std() if daily_ic.std() > 0 else 0,
                    'ic_positive_ratio': (daily_ic > 0).sum() / len(daily_ic),
                    'sample_days': len(daily_ic)  # 有效交易日数
                }

                # 记录指标到MLflow
                R.log_metrics(
                    ic_mean=results['ic_mean'],
                    ic_std=results['ic_std'],
                    ic_ir=results['ic_ir'],
                    ic_positive_ratio=results['ic_positive_ratio'],
                    sample_days=results['sample_days']
                )

                # 保存对象到MLflow
                R.save_objects(**{
                    "model.pkl": model,
                    "pred.pkl": test_pred,
                    "daily_ic.pkl": daily_ic
                })

                # 获取recorder ID
                rid = R.get_recorder().id
                results['recorder_id'] = rid

                print(f"\n✅ 测试结果:")
                print(f"   IC均值: {results['ic_mean']:.4f}")
                print(f"   IC标准差: {results['ic_std']:.4f}")
                print(f"   IC_IR: {results['ic_ir']:.4f}")
                print(f"   IC正值占比: {results['ic_positive_ratio']:.2%}")
                print(f"   有效交易日数: {results['sample_days']}")
                print(f"   MLflow Recorder ID: {rid}")

                return results

        except Exception as e:
            print(f"❌ 错误: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def run_all_periods(self, start_year=2008, end_year=2025):
        """
        运行所有滚动窗口回测

        参数:
            start_year: 起始年份
            end_year: 结束年份(使用当前年份)
        """
        periods = self.generate_rolling_periods(start_year, end_year)

        print(f"\n🎯 滚动窗口验证计划:")
        print(f"   训练窗口: {self.train_years}年")
        print(f"   验证窗口: {self.valid_years}年")
        print(f"   测试窗口: {self.test_years}年")
        print(f"   总测试期数: {len(periods)}期\n")

        for i, period in enumerate(periods, 1):
            print(f"\n进度: [{i}/{len(periods)}]")
            result = self.run_single_period(period)
            if result:
                self.results.append(result)

        # 生成汇总报告
        self.generate_summary_report()

    def generate_summary_report(self):
        """生成汇总报告"""
        if not self.results:
            print("\n⚠️ 无有效结果")
            return

        # 转换为DataFrame
        df = pd.DataFrame(self.results)

        # 保存详细结果(包含recorder_id)
        output_dir = Path("validation_results")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = output_dir / f"rolling_validation_{timestamp}.csv"
        df.to_csv(csv_path, index=False, encoding='utf-8-sig')

        # 打印汇总报告
        print("\n" + "="*80)
        print("📊 滚动窗口验证汇总报告")
        print("="*80)
        print(f"\n💾 MLflow实验名称: rolling_validation")
        print(f"💾 所有结果已保存到MLflow,可通过以下方式查看:")
        print(f"   - MLflow UI: mlflow ui")
        print(f"   - 访问: http://localhost:5000")

        print(f"\n总测试期数: {len(df)}")
        print(f"\nIC指标统计:")
        print(f"   平均IC均值: {df['ic_mean'].mean():.4f}")
        print(f"   IC均值标准差: {df['ic_mean'].std():.4f}")
        print(f"   IC均值范围: [{df['ic_mean'].min():.4f}, {df['ic_mean'].max():.4f}]")
        print(f"   平均IC_IR: {df['ic_ir'].mean():.4f}")
        print(f"   IC>0.03的期数: {(df['ic_mean'] > 0.03).sum()}/{len(df)} ({(df['ic_mean'] > 0.03).mean():.1%})")
        print(f"   IC>0.01的期数: {(df['ic_mean'] > 0.01).sum()}/{len(df)} ({(df['ic_mean'] > 0.01).mean():.1%})")
        print(f"   IC<0的期数: {(df['ic_mean'] < 0).sum()}/{len(df)} ({(df['ic_mean'] < 0).mean():.1%})")

        print(f"\n稳健性评估:")
        ic_std = df['ic_mean'].std()
        if ic_std < 0.01:
            stability = "极其稳定 ⭐⭐⭐"
        elif ic_std < 0.02:
            stability = "稳定 ⭐⭐"
        elif ic_std < 0.03:
            stability = "一般 ⭐"
        else:
            stability = "不稳定 ❌"
        print(f"   策略稳定性: {stability}")

        print(f"\n各期详细结果:")
        print(df.to_string(index=False))

        print(f"\n✅ 详细结果已保存至: {csv_path}")

        # 判断是否可以实盘
        print("\n" + "="*80)
        print("🎯 实盘建议")
        print("="*80)

        avg_ic = df['ic_mean'].mean()
        positive_ratio = (df['ic_mean'] > 0.03).mean()

        if avg_ic > 0.03 and positive_ratio > 0.7:
            print("✅ 策略表现优秀，可考虑小资金实盘测试")
        elif avg_ic > 0.02 and positive_ratio > 0.5:
            print("⚠️ 策略表现一般，建议继续优化或模拟盘测试")
        elif avg_ic > 0.01:
            print("⚠️ 策略表现较弱，建议重新训练或调整因子")
        else:
            print("❌ 策略已失效，不建议实盘，需要重新开发")

        # MLflow使用说明
        print("\n" + "="*80)
        print("📊 如何查看MLflow中的结果")
        print("="*80)
        print("\n1️⃣ 启动MLflow UI:")
        print("   mlflow ui")
        print("\n2️⃣ 浏览器访问:")
        print("   http://localhost:5000")
        print("\n3️⃣ 查看方法:")
        print("   - 实验名称: rolling_validation")
        print("   - 每个测试期都有独立的run记录")
        print("   - 可查看IC指标、加载模型和预测结果")
        print("\n4️⃣ 加载特定期的结果 (Python代码):")
        print("   from qlib.workflow import R")
        print("   recorder = R.get_recorder(recorder_id='<rid>', experiment_name='rolling_validation')")
        print("   model = recorder.load_object('model.pkl')")
        print("   pred = recorder.load_object('pred.pkl')")
        print("   daily_ic = recorder.load_object('daily_ic.pkl')")
        print(f"\n💡 Recorder IDs已保存在CSV文件中: {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='滚动窗口验证 - 评估策略稳健性',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认参数(6年训练+2年验证+1年测试) - 自动生成图表
  python scripts/50_滚动窗口验证.py --config configs/workflow_config_top50_optimized.yaml

  # 自定义窗口大小
  python scripts/50_滚动窗口验证.py --config configs/workflow_config_top50_optimized.yaml --train-years 5 --test-years 2

  # 指定验证时间范围
  python scripts/50_滚动窗口验证.py --config configs/workflow_config_top50_optimized.yaml --start-year 2015 --end-year 2025

  # 不自动生成图表(只做验证)
  python scripts/50_滚动窗口验证.py --config configs/workflow_config_top50_optimized.yaml --no-charts

注意:
  - 默认会在验证完成后自动生成可视化图表和HTML报告
  - 所有结果保存到MLflow实验 'rolling_validation'
  - 图表保存在 validation_results/charts/ 目录
        """
    )
    parser.add_argument('--config', type=str, required=True, help='配置文件路径')
    parser.add_argument('--train-years', type=int, default=6, help='训练窗口年数(默认6)')
    parser.add_argument('--valid-years', type=int, default=2, help='验证窗口年数(默认2)')
    parser.add_argument('--test-years', type=int, default=1, help='测试窗口年数(默认1)')
    parser.add_argument('--start-year', type=int, default=2008, help='起始年份(默认2008)')
    parser.add_argument('--end-year', type=int, default=2025, help='结束年份(默认2025)')
    parser.add_argument('--no-charts', action='store_true', help='不自动生成图表(默认会自动生成)')

    args = parser.parse_args()

    # 初始化Qlib
    print("初始化Qlib...")
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')
    print("[OK] Qlib初始化完成\n")

    # 创建滚动窗口回测管理器
    validator = RollingWindowBacktest(
        config_path=args.config,
        train_years=args.train_years,
        valid_years=args.valid_years,
        test_years=args.test_years
    )

    # 运行所有测试期
    validator.run_all_periods(
        start_year=args.start_year,
        end_year=args.end_year
    )

    print("\n[OK] 滚动窗口验证完成!\n")

    # 自动生成可视化报告(除非用户指定--no-charts)
    if not args.no_charts:
        print("="*80)
        print("📊 自动生成可视化报告")
        print("="*80)

        try:
            # 方案1: 直接导入并运行（避免编码问题）
            visualizer_module_path = Path(__file__).parent / "result"
            if str(visualizer_module_path) not in sys.path:
                sys.path.insert(0, str(visualizer_module_path))

            try:
                # 导入可视化模块
                from 滚动验证可视化 import RollingValidationVisualizer

                print("\n正在从MLflow加载数据并生成图表...\n")

                # 创建可视化器并运行
                visualizer = RollingValidationVisualizer(experiment_name="rolling_validation")
                visualizer.run()

                print("\n✅ 可视化报告生成成功!")
                print(f"📁 查看报告: validation_results/charts/rolling_validation_report.html")

            except ImportError as e:
                print(f"⚠️ 无法导入可视化模块: {str(e)}")
                print("提示: 请确认 scripts/result/滚动验证可视化.py 文件存在")

        except Exception as e:
            print(f"\n⚠️ 自动生成可视化报告时出错: {str(e)}")
            import traceback
            traceback.print_exc()
            print("\n提示: 可以手动运行以下命令生成报告:")
            print(f"  python scripts/result/滚动验证可视化.py")

        print("\n" + "="*80)
    else:
        print("\n💡 提示: 使用 --no-charts 跳过了图表生成")
        print("可以稍后手动运行: python scripts/result/滚动验证可视化.py\n")
