"""
使用IC分析结果的实用工具
提供查看、筛选、导出强因子的功能

作者：Claude Code
日期：2025-11-15
"""
import pandas as pd
import qlib
from qlib.workflow import R
from pathlib import Path


def initialize_qlib():
    """初始化Qlib环境"""
    provider_uri = 'D:/Data/my_stock'
    region = 'cn'
    qlib.init(provider_uri=provider_uri, region=region)


def load_latest_ic_results():
    """加载最新的IC分析结果"""
    print("=" * 80)
    print("加载最新IC分析结果")
    print("=" * 80)

    # 获取最新的IC分析实验
    exp = R.get_exp(experiment_name="ic_analysis")
    recorders = exp.list_recorders()

    if not recorders:
        print("[ERROR] 没有找到IC分析记录")
        return None, None

    # recorders是字典，key是recorder_id
    recorder_ids = list(recorders.keys())
    if not recorder_ids:
        print("[ERROR] 没有找到IC分析记录")
        return None, None

    # 获取最新的recorder（第一个）
    recorder_id = recorder_ids[0]

    print(f"\n最新记录ID: {recorder_id}")

    # 加载IC分析结果
    recorder = R.get_recorder(recorder_id=recorder_id, experiment_name="ic_analysis")

    ic_df = recorder.load_object("ic_analysis_full")
    strong_factors = recorder.load_object("strong_factors_list")

    print(f"\n总因子数: {len(ic_df)}")
    print(f"强因子数: {len(strong_factors)}")

    return ic_df, strong_factors


def show_top_factors(ic_df, n=20):
    """显示Top N强因子"""
    print("\n" + "=" * 80)
    print(f"Top {n} 强因子（按IC绝对值排序）")
    print("=" * 80)

    # 按IC绝对值排序
    top_factors = ic_df.copy()
    top_factors['ic_abs'] = top_factors['ic_mean'].abs()
    top_factors = top_factors.sort_values('ic_abs', ascending=False).head(n)

    # 格式化输出
    print(f"\n{'排名':<4} {'因子名称':<30} {'IC均值':<10} {'IC标准差':<10} {'IR':<8} {'因子库':<20}")
    print("-" * 100)

    for i, (idx, row) in enumerate(top_factors.iterrows(), 1):
        print(f"{i:<4} {row['factor_name']:<30} {row['ic_mean']:>9.4f} {row['ic_std']:>9.4f} {row['ir']:>7.2f} {row['library']:<20}")


def show_library_stats(ic_df):
    """按因子库统计"""
    print("\n" + "=" * 80)
    print("因子库统计")
    print("=" * 80)

    stats = ic_df.groupby('library').agg({
        'factor_name': 'count',
        'ic_mean': ['mean', 'std'],
        'ir': 'mean'
    }).round(4)

    stats.columns = ['因子数', 'IC均值', 'IC标准差', 'IR均值']
    print("\n", stats)


def export_strong_factors(strong_factors, output_path='强因子列表.csv'):
    """导出强因子到CSV"""
    print("\n" + "=" * 80)
    print("导出强因子")
    print("=" * 80)

    # 选择关键列
    export_df = strong_factors[[
        'factor_name', 'library', 'ic_mean', 'ic_std', 'ir', 'valid_days'
    ]].copy()

    export_df = export_df.sort_values('ic_mean', key=abs, ascending=False)

    output_file = Path(output_path)
    export_df.to_csv(output_file, index=False, encoding='utf-8-sig')

    print(f"\n✅ 已导出 {len(export_df)} 个强因子到: {output_file}")
    print(f"文件路径: {output_file.absolute()}")


def generate_factor_config(strong_factors, top_n=50):
    """生成因子配置（用于模型训练）"""
    print("\n" + "=" * 80)
    print(f"生成Top {top_n}因子配置")
    print("=" * 80)

    # 按IC绝对值排序，取Top N
    top_factors = strong_factors.copy()
    top_factors['ic_abs'] = top_factors['ic_mean'].abs()
    top_factors = top_factors.sort_values('ic_abs', ascending=False).head(top_n)

    print(f"\n选中因子分布:")
    print(top_factors['library'].value_counts())

    # 读取原始因子表达式
    factor_list = []
    for idx, row in top_factors.iterrows():
        # 从ic_df中获取因子表达式
        factor_list.append({
            'name': row['factor_name'],
            'library': row['library'],
            'ic': row['ic_mean'],
            'ir': row['ir']
        })

    print(f"\n✅ 生成了 {len(factor_list)} 个因子的配置")
    print("\n下一步:")
    print("  1. 使用这些因子重新训练模型")
    print("  2. 对比使用全部因子 vs Top因子的模型性能")

    return factor_list


def main():
    """主函数"""
    # 0. 初始化Qlib
    initialize_qlib()

    # 1. 加载最新结果
    ic_df, strong_factors = load_latest_ic_results()

    if ic_df is None:
        return

    # 2. 显示Top 20强因子
    show_top_factors(ic_df, n=20)

    # 3. 按因子库统计
    show_library_stats(ic_df)

    # 4. 导出强因子
    export_strong_factors(strong_factors)

    # 5. 生成Top 50因子配置
    factor_config = generate_factor_config(strong_factors, top_n=50)

    print("\n" + "=" * 80)
    print("✅ IC结果分析完成")
    print("=" * 80)


if __name__ == '__main__':
    main()
