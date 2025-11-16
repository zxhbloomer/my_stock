"""
自定义Handler使用示例

演示如何使用自定义Handler进行因子计算
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import qlib
from qlib.constant import REG_CN
from handlers.custom_handler import CustomAlphaHandler, SimpleAlphaHandler


def main():
    """主函数"""

    print("=" * 60)
    print("自定义Handler使用示例")
    print("=" * 60)

    # 初始化Qlib
    print("\n【步骤1】初始化Qlib")
    qlib.init(provider_uri="D:/Data/my_stock", region=REG_CN)
    print("✓ Qlib初始化成功")

    # 示例1：使用SimpleAlphaHandler（精简版，适合快速实验）
    print("\n【示例1】使用SimpleAlphaHandler")
    simple_handler = SimpleAlphaHandler(
        instruments="csi300",
        start_time="2020-01-01",
        end_time="2020-12-31",
        fit_start_time="2020-01-01",
        fit_end_time="2020-06-30"
    )

    # 获取所有列
    print(f"\n特征列数: {len(simple_handler.get_cols())}")

    # 获取特征数据
    print("\n获取特征数据...")
    feature_df = simple_handler.fetch(col_set="feature")
    print(f"特征数据形状: {feature_df.shape}")
    print("\n前5行数据:")
    print(feature_df.head())

    # 获取标签数据
    print("\n获取标签数据...")
    label_df = simple_handler.fetch(col_set="label")
    print(f"标签数据形状: {label_df.shape}")
    print("\n前5行标签:")
    print(label_df.head())

    # 示例2：使用CustomAlphaHandler（完整版，包含所有因子）
    print("\n\n【示例2】使用CustomAlphaHandler")
    custom_handler = CustomAlphaHandler(
        instruments="csi300",
        start_time="2020-01-01",
        end_time="2020-12-31",
        fit_start_time="2020-01-01",
        fit_end_time="2020-06-30"
    )

    print(f"\n特征列数: {len(custom_handler.get_cols())}")

    # 获取特征数据
    custom_feature_df = custom_handler.fetch(col_set="feature")
    print(f"特征数据形状: {custom_feature_df.shape}")

    print("\n✓ Handler使用成功！")


if __name__ == "__main__":
    main()
