"""
因子IC分析脚本（MLflow集成版）
替代 notebooks/factor_ic_analysis.ipynb，提供自动化的因子有效性分析

功能：
1. 加载所有因子库（Alpha158 + AlphaFactors + ChinaMarketFactors）
2. 计算每个因子的IC值（Information Coefficient）
3. 统计分析：IC均值、标准差、IR（Information Ratio）
4. 生成可视化图表
5. 筛选强因子并保存到MLflow实验管理系统

改进：
- 使用MLflow管理IC分析实验（与train_model、backtest_analysis统一）
- 支持历史记录查询和实验对比
- 自动记录参数、指标、数据和图表

作者：Claude Code
日期：2025-11-15
更新：2025-11-15（MLflow集成）
"""
import sys
import os
import warnings
import pandas as pd
import numpy as np
from pathlib import Path
from tqdm import tqdm
import matplotlib.pyplot as plt
import seaborn as sns
from scipy.stats import spearmanr

# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 忽略警告
warnings.filterwarnings('ignore')

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


def initialize_qlib():
    """初始化Qlib环境"""
    import qlib

    provider_uri = 'D:/Data/my_stock'
    region = 'cn'

    print("=" * 80)
    print("初始化Qlib环境")
    print("=" * 80)
    print(f"数据路径: {provider_uri}")
    print(f"市场区域: {region}")

    qlib.init(provider_uri=provider_uri, region=region)
    print("[OK] Qlib初始化完成\n")


def load_all_factors():
    """
    加载所有因子库

    Returns:
        tuple: (因子表达式列表, 因子名称列表, 因子库来源列表)
    """
    from qlib.contrib.data.handler import Alpha158
    from factors.alpha_factors import AlphaFactors
    from factors.china_market_factors import ChinaMarketFactors

    print("=" * 80)
    print("加载因子库")
    print("=" * 80)

    all_features = []
    all_names = []
    all_libraries = []

    # 1. Alpha158因子
    # 使用Alpha158DL的静态方法获取完整的158因子配置
    from qlib.contrib.data.handler import Alpha158DL
    conf = {
        "kbar": {},  # K线特征(9个)
        "price": {   # 价格特征
            "windows": [0, 1, 2, 3, 4],
            "feature": ["OPEN", "HIGH", "LOW", "CLOSE", "VWAP"],
        },
        "volume": {  # 成交量特征
            "windows": [0, 1, 2, 3, 4],
        },
        "rolling": {  # 滚动窗口特征(大量技术指标)
            "windows": [5, 10, 20, 30, 60],
        },
    }
    # get_feature_config返回tuple: (表达式列表, 名称列表)
    alpha158_result = Alpha158DL.get_feature_config(conf)
    alpha158_features = alpha158_result[0]  # 只取表达式列表
    alpha158_count = len(alpha158_features)

    for i, expr in enumerate(alpha158_features, 1):
        all_features.append(expr)
        all_names.append(f"Alpha158_{i}")
        all_libraries.append("Alpha158")

    print(f"[OK] Alpha158: {alpha158_count} 个因子")

    # 2. AlphaFactors因子
    alpha_features = AlphaFactors.get_all_features()
    alpha_names = AlphaFactors.get_feature_names()
    alpha_count = len(alpha_features)

    for expr, name in zip(alpha_features, alpha_names):
        all_features.append(expr)
        all_names.append(f"AlphaFactor_{name}")
        all_libraries.append("AlphaFactors")

    print(f"[OK] AlphaFactors: {alpha_count} 个因子")

    # 3. ChinaMarketFactors因子
    china_features = ChinaMarketFactors.get_all_features()
    china_names = ChinaMarketFactors.get_feature_names()
    china_count = len(china_features)

    for expr, name in zip(china_features, china_names):
        all_features.append(expr)
        all_names.append(f"ChinaFactor_{name}")
        all_libraries.append("ChinaMarketFactors")

    print(f"[OK] ChinaMarketFactors: {china_count} 个因子")

    total = len(all_features)
    print(f"\n总计: {total} 个因子")
    print(f"   - Alpha158: {alpha158_count}")
    print(f"   - AlphaFactors: {alpha_count}")
    print(f"   - ChinaMarketFactors: {china_count}\n")

    return all_features, all_names, all_libraries


def load_stock_pool(pool_name='csi300'):
    """
    加载股票池

    Args:
        pool_name: 股票池名称 ('csi300' 或 'csi500')

    Returns:
        list: 股票代码列表
    """
    print(f"加载股票池: {pool_name}")

    instruments_path = f'D:/Data/my_stock/instruments/{pool_name}.txt'

    try:
        # csi300.txt 和 csi500.txt 是3列TSV格式（股票代码\t开始日期\t结束日期）
        df = pd.read_csv(instruments_path, sep='\t', names=['instrument', 'start_date', 'end_date'])
        stocks = df['instrument'].tolist()

        print(f"[OK] 加载 {len(stocks)} 只股票\n")
        return stocks

    except Exception as e:
        print(f"[ERROR] 加载股票池失败: {e}")
        print(f"尝试使用all.txt...")

        # 备选方案：使用 all.txt（3列格式）
        all_path = 'D:/Data/my_stock/instruments/all.txt'
        df = pd.read_csv(all_path, sep='\t', names=['instrument', 'start_date', 'end_date'])
        stocks = df['instrument'].tolist()

        print(f"[OK] 从all.txt加载 {len(stocks)} 只股票\n")
        return stocks


def calculate_ic_for_factor(factor_expr, factor_name, instruments, start_time, end_time):
    """
    计算单个因子的IC值(使用Qlib官方方法)

    Args:
        factor_expr: 因子表达式
        factor_name: 因子名称
        instruments: 股票代码列表
        start_time: 开始时间
        end_time: 结束时间

    Returns:
        dict: IC统计结果
    """
    from qlib.data import D
    from qlib.contrib.eva.alpha import calc_ic

    try:
        # 一次性获取因子和标签数据
        fields = [factor_expr, 'Ref($close, -1)/$close - 1']
        df = D.features(
            instruments,
            fields=fields,
            start_time=start_time,
            end_time=end_time
        )

        if df is None or len(df) < 10:
            return None

        df.columns = ['factor', 'label']
        df = df.dropna()

        if len(df) < 10:
            return None

        # 使用Qlib官方calc_ic函数计算IC
        # calc_ic返回的是按日期分组的Series (每天一个IC值)
        ic_series, ric_series = calc_ic(df['factor'], df['label'])

        # 计算IC均值
        ic_mean = float(ic_series.mean())
        ric_mean = float(ric_series.mean())

        if pd.isna(ic_mean) or pd.isna(ric_mean):
            return None

        # 计算IC标准差和IR
        ic_std = float(ic_series.std())
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0

        return {
            'factor_name': factor_name,
            'ic_mean': ic_mean,
            'ic_std': ic_std,
            'ir': ic_ir,
            'valid_days': len(ic_series),
            'daily_ic': ic_series.tolist()
        }

    except Exception as e:
        print(f"[WARN] {factor_name} IC计算失败: {e}")
        return None


def run_ic_analysis(
    instruments,
    pool_name='csi300',
    start_time='2017-01-01',
    end_time='2020-12-31',
    ic_threshold=0.01
):
    """
    运行IC分析（MLflow集成版）

    Args:
        instruments: 股票代码列表
        pool_name: 股票池名称（csi300/csi500）
        start_time: 开始时间
        end_time: 结束时间
        ic_threshold: IC阈值（默认0.01）

    Returns:
        tuple: (ic_df, strong_factors, recorder_id)
    """
    from qlib.workflow import R
    import tempfile

    print("=" * 80)
    print("开始IC分析（MLflow集成版）")
    print("=" * 80)
    print(f"时间范围: {start_time} ~ {end_time}")
    print(f"股票池: {pool_name}")
    print(f"股票数量: {len(instruments)}")
    print(f"IC阈值: {ic_threshold}")
    print(f"实验名: ic_analysis\n")

    # 启动MLflow实验
    with R.start(experiment_name="ic_analysis"):
        # 1. 记录参数
        R.log_params(
            pool=pool_name,
            ic_threshold=ic_threshold,
            start_time=start_time,
            end_time=end_time,
            stock_count=len(instruments)
        )
        print("[OK] 参数已记录到MLflow\n")

        # 2. 加载因子
        all_features, all_names, all_libraries = load_all_factors()

        # 3. 计算每个因子的IC
        ic_results = []
        print("计算因子IC值（预计15-35分钟）...")
        for expr, name, lib in tqdm(
            zip(all_features, all_names, all_libraries),
            total=len(all_features),
            desc="IC计算进度"
        ):
            result = calculate_ic_for_factor(
                expr, name, instruments, start_time, end_time
            )

            if result is not None:
                result['library'] = lib
                result['expression'] = expr
                ic_results.append(result)

        # 4. 转换为DataFrame
        if not ic_results:
            raise ValueError(
                "[ERROR] 所有因子的IC计算都失败了！\n"
                "可能原因：\n"
                "1. 数据时间范围内没有数据\n"
                "2. 因子表达式语法错误\n"
                "3. instruments格式不正确\n"
                f"请检查：start_time={start_time}, end_time={end_time}, instruments数量={len(instruments)}"
            )

        ic_df = pd.DataFrame([
            {
                'factor_name': r['factor_name'],
                'library': r['library'],
                'ic_mean': r['ic_mean'],
                'ic_std': r['ic_std'],
                'ir': r['ir'],
                'valid_days': r['valid_days']
            }
            for r in ic_results
        ])

        # 筛选强因子
        strong_factors = ic_df[abs(ic_df['ic_mean']) > ic_threshold].copy()
        strong_factors = strong_factors.sort_values('ic_mean', ascending=False)

        # 5. 记录核心指标到MLflow
        R.log_metrics(
            ic_mean_all=float(ic_df['ic_mean'].mean()),
            ic_std_all=float(ic_df['ic_std'].mean()),
            ir_mean_all=float(ic_df['ir'].mean()),
            ic_mean_strong=float(strong_factors['ic_mean'].mean()),
            ic_max_strong=float(strong_factors['ic_mean'].max()),
            ic_min_strong=float(strong_factors['ic_mean'].min()),
            strong_factors_count=int(len(strong_factors)),
            total_factors_count=int(len(ic_df)),
            retention_rate=float(len(strong_factors) / len(ic_df))
        )
        print("[OK] 核心指标已记录到MLflow")

        # 6. 保存数据artifacts到MLflow
        R.save_objects(
            ic_analysis_full=ic_df,
            strong_factors_list=strong_factors
        )
        print("[OK] IC分析数据已保存到MLflow")

        # 7. 生成图表并保存到MLflow
        print("\n生成可视化图表...")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            generate_charts(ic_df, strong_factors, ic_results, tmp_path)

            # 保存图表到MLflow
            R.log_artifact(str(tmp_path / 'ic_distribution.png'))
            R.log_artifact(str(tmp_path / 'ic_timeseries_top5.png'))
            R.log_artifact(str(tmp_path / 'strong_factors_by_library.png'))
        print("[OK] 可视化图表已保存到MLflow")

        # 8. 获取recorder_id
        recorder_id = R.get_recorder().id

        # 统计报告
        print("\n" + "=" * 80)
        print("IC分析统计报告")
        print("=" * 80)
        print(f"\n总因子数: {len(ic_df)}")
        print(f"强因子数（|IC| > {ic_threshold}）: {len(strong_factors)}")
        print(f"筛选比例: {len(strong_factors) / len(ic_df) * 100:.1f}%")

        print(f"\n所有因子IC统计:")
        print(f"  - IC均值: {ic_df['ic_mean'].mean():.4f}")
        print(f"  - IC标准差: {ic_df['ic_std'].mean():.4f}")
        print(f"  - IR均值: {ic_df['ir'].mean():.2f}")

        print(f"\n强因子IC统计:")
        print(f"  - IC均值: {strong_factors['ic_mean'].mean():.4f}")
        print(f"  - IC最大值: {strong_factors['ic_mean'].max():.4f}")
        print(f"  - IC最小值: {strong_factors['ic_mean'].min():.4f}")

        print(f"\n按因子库统计:")
        for lib in ['Alpha158', 'AlphaFactors', 'ChinaMarketFactors']:
            lib_total = len(ic_df[ic_df['library'] == lib])
            lib_strong = len(strong_factors[strong_factors['library'] == lib])
            if lib_total > 0:
                print(f"  - {lib}: {lib_strong}/{lib_total} ({lib_strong/lib_total*100:.1f}%)")

        print(f"\n📊 MLflow记录ID: {recorder_id}")

        return ic_df, strong_factors, recorder_id


def generate_charts(ic_df, strong_factors, ic_results, output_dir):
    """
    生成可视化图表

    Args:
        ic_df: IC分析结果DataFrame
        strong_factors: 强因子DataFrame
        ic_results: 包含daily_ic的详细结果
        output_dir: 输出目录
    """
    print("\n生成可视化图表...")

    # 1. IC分布直方图
    plt.figure(figsize=(12, 6))
    plt.hist(ic_df['ic_mean'], bins=50, edgecolor='black', alpha=0.7)
    plt.axvline(x=0.01, color='r', linestyle='--', label='阈值 +0.01')
    plt.axvline(x=-0.01, color='r', linestyle='--', label='阈值 -0.01')
    plt.xlabel('IC均值')
    plt.ylabel('因子数量')
    plt.title('因子IC分布（所有因子）')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_dir / 'ic_distribution.png', dpi=150, bbox_inches='tight')
    print(f"[OK] 已生成: ic_distribution.png")
    plt.close()

    # 2. Top 5强因子的IC时间序列
    top5_factors = strong_factors.head(5)

    plt.figure(figsize=(14, 8))
    for i, (idx, row) in enumerate(top5_factors.iterrows()):
        factor_name = row['factor_name']

        # 找到对应的daily_ic数据
        daily_ic = None
        for r in ic_results:
            if r['factor_name'] == factor_name:
                daily_ic = r['daily_ic']
                break

        if daily_ic:
            plt.subplot(5, 1, i + 1)
            plt.plot(daily_ic, label=f"{factor_name} (IC={row['ic_mean']:.4f})")
            plt.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            plt.ylabel('IC值')
            plt.legend(loc='upper right')
            plt.grid(True, alpha=0.3)

    plt.xlabel('交易日')
    plt.suptitle('Top 5强因子的IC时间序列', fontsize=14, y=0.995)
    plt.tight_layout()
    plt.savefig(output_dir / 'ic_timeseries_top5.png', dpi=150, bbox_inches='tight')
    print(f"[OK] 已生成: ic_timeseries_top5.png")
    plt.close()

    # 3. 按因子库统计柱状图
    lib_stats = strong_factors.groupby('library').agg({
        'factor_name': 'count',
        'ic_mean': 'mean'
    })
    lib_stats.columns = ['数量', 'IC均值']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    # 强因子数量
    lib_stats['数量'].plot(kind='bar', ax=ax1, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
    ax1.set_title('强因子数量（按因子库）')
    ax1.set_ylabel('因子数量')
    ax1.set_xlabel('因子库')
    ax1.grid(True, alpha=0.3, axis='y')

    # IC均值
    lib_stats['IC均值'].plot(kind='bar', ax=ax2, color=['#1f77b4', '#ff7f0e', '#2ca02c'])
    ax2.set_title('强因子IC均值（按因子库）')
    ax2.set_ylabel('IC均值')
    ax2.set_xlabel('因子库')
    ax2.axhline(y=0.01, color='r', linestyle='--', alpha=0.5)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(output_dir / 'strong_factors_by_library.png', dpi=150, bbox_inches='tight')
    print(f"[OK] 已生成: strong_factors_by_library.png")
    plt.close()

    print("\n[OK] 所有图表生成完成")


def main():
    """主函数"""
    try:
        # 初始化Qlib
        initialize_qlib()

        # 加载股票池（默认csi300）
        instruments = load_stock_pool('csi300')

        # 运行IC分析（使用最近7年数据,覆盖完整牛熊周期）
        ic_df, strong_factors, recorder_id = run_ic_analysis(
            instruments=instruments,
            pool_name='csi300',
            start_time='2018-01-01',  # 覆盖2018-2025完整牛熊周期
            end_time='2025-11-14',    # 使用数据库最新日期
            ic_threshold=0.01
        )

        print("\n" + "=" * 80)
        print("[OK] IC分析完成！")
        print("=" * 80)
        print(f"\n📊 MLflow实验: ic_analysis")
        print(f"📝 Recorder ID: {recorder_id}")
        print(f"\n保存位置: mlruns/ic_analysis/")
        print(f"\n下一步:")
        print(f"  1. 查看结果: python scripts/21_use_ic_results.py")
        print(f"  2. 查看图表: mlflow ui (浏览器访问 http://localhost:5000)")
        print(f"  3. 使用强因子优化模型训练")

    except Exception as e:
        print(f"\n[ERROR] 执行失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
