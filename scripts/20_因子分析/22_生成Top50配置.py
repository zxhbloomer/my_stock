"""
使用IC分析筛选的Top因子进行模型训练

基于IC分析结果，只使用Top 50强因子训练模型
预期效果：训练速度提升3-5倍，模型性能相当或更优

作者：Claude Code
日期：2025-11-16
"""
import sys
import pandas as pd
import qlib
from qlib.workflow import R
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_top_factors(n=50):
    """从最新IC分析中加载Top N因子"""
    # 初始化Qlib
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')

    # 加载IC分析结果
    exp = R.get_exp(experiment_name="ic_analysis")
    recorder_ids = list(exp.list_recorders().keys())

    if not recorder_ids:
        print("[ERROR] 没有找到IC分析记录，请先运行: python scripts/20_ic_analysis.py")
        sys.exit(1)

    recorder = R.get_recorder(recorder_id=recorder_ids[0], experiment_name="ic_analysis")
    ic_df = recorder.load_object("ic_analysis_full")

    # 按IC绝对值排序，取Top N
    ic_df['ic_abs'] = ic_df['ic_mean'].abs()
    top_factors = ic_df.nlargest(n, 'ic_abs')

    print(f"[OK] 加载Top {n}因子:")
    print(f"   - ChinaMarketFactors: {len(top_factors[top_factors['library']=='ChinaMarketFactors'])}")
    print(f"   - AlphaFactors: {len(top_factors[top_factors['library']=='AlphaFactors'])}")
    print(f"   - Alpha158: {len(top_factors[top_factors['library']=='Alpha158'])}")

    return top_factors


def generate_handler_config(top_factors):
    """生成Handler配置（用于workflow_config）"""

    # 从因子名映射回表达式（需要重新加载原始因子）
    from qlib.contrib.data.handler import Alpha158DL
    from factors.alpha_factors import AlphaFactors
    from factors.china_market_factors import ChinaMarketFactors

    # 加载所有因子表达式
    alpha158_conf = {
        "kbar": {},
        "price": {"windows": [0, 1, 2, 3, 4], "feature": ["OPEN", "HIGH", "LOW", "CLOSE", "VWAP"]},
        "volume": {"windows": [0, 1, 2, 3, 4]},
        "rolling": {"windows": [5, 10, 20, 30, 60]},
    }
    alpha158_result = Alpha158DL.get_feature_config(alpha158_conf)
    alpha158_features = alpha158_result[0]

    alpha_features = AlphaFactors.get_all_features()
    alpha_names = AlphaFactors.get_feature_names()

    china_features = ChinaMarketFactors.get_all_features()
    china_names = ChinaMarketFactors.get_feature_names()

    # 创建因子名到表达式的映射
    factor_map = {}

    for i, expr in enumerate(alpha158_features, 1):
        factor_map[f"Alpha158_{i}"] = expr

    for expr, name in zip(alpha_features, alpha_names):
        factor_map[f"AlphaFactor_{name}"] = expr

    for expr, name in zip(china_features, china_names):
        factor_map[f"ChinaFactor_{name}"] = expr

    # 提取Top因子的表达式
    selected_features = []
    seen_expressions = set()  # 用于去重

    for _, row in top_factors.iterrows():
        factor_name = row['factor_name']
        if factor_name in factor_map:
            expr = factor_map[factor_name]
            # 去重：同一个表达式只保留一次
            if expr not in seen_expressions:
                selected_features.append(expr)
                seen_expressions.add(expr)

    print(f"\n[OK] 生成 {len(selected_features)} 个因子表达式（已去重）")

    # 生成handler配置（使用DataHandlerLP + QlibDataLoader方式）
    handler_config = {
        "class": "DataHandlerLP",
        "module_path": "qlib.contrib.data.handler",
        "kwargs": {
            "start_time": "2008-01-01",
            "end_time": "2025-11-14",        # 更新为最新数据日期
            "instruments": "csi300",
            "data_loader": {
                "class": "QlibDataLoader",
                "kwargs": {
                    "config": {
                        "feature": selected_features,  # Top 50因子表达式
                        "label": ["Ref($close, -2)/Ref($close, -1) - 1"]
                    },
                    "freq": "day"
                }
            },
            "infer_processors": [
                {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True, "fit_start_time": "2015-01-01", "fit_end_time": "2022-12-31"}},
                {"class": "Fillna", "kwargs": {"fields_group": "feature"}}
            ],
            "learn_processors": [
                {"class": "DropnaLabel"},
                {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}}
            ]
        }
    }

    return handler_config, selected_features


def save_optimized_config(top_factors, output_path='configs/workflow_config_top50.yaml'):
    """保存优化后的workflow配置"""
    import yaml

    # 生成handler配置
    handler_config, selected_features = generate_handler_config(top_factors)

    # 读取原始配置作为模板
    with open('configs/workflow_config_lightgbm_Alpha158.yaml', 'r', encoding='utf-8') as f:
        base_config = yaml.safe_load(f)

    # 修改为Top50因子配置
    base_config['task']['dataset']['kwargs']['handler'] = handler_config

    # 保存新配置
    output_file = Path(output_path)
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(base_config, f, allow_unicode=True, sort_keys=False)

    print(f"\n[OK] 优化配置已保存: {output_file}")
    print(f"\n运行命令:")
    print(f"  python run_workflow.py {output_file}")

    return output_file


def main():
    """主函数"""
    print("=" * 80)
    print("基于IC分析生成优化的模型训练配置")
    print("=" * 80)

    # 1. 加载Top 50因子
    top_factors = load_top_factors(n=50)

    # 2. 保存优化配置
    config_path = save_optimized_config(top_factors)

    print("\n" + "=" * 80)
    print("[OK] 配置生成完成")
    print("=" * 80)
    print("\n下一步:")
    print("  1. 运行优化模型: python scripts/30_运行工作流.py configs/workflow_config_top50.yaml")
    print("  2. 对比性能: 原始255因子 vs Top50因子")
    print("  3. 查看回测结果: python view_results.py")


if __name__ == '__main__':
    main()
