"""
数据采集示例

演示如何使用Tushare采集器下载和标准化数据
"""
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data.collectors.tushare_collector import Run


def main():
    """主函数"""

    # 配置Tushare token
    # 请替换为你的Tushare token
    TOKEN = "your_tushare_token_here"

    print("=" * 60)
    print("Tushare 数据采集示例")
    print("=" * 60)

    # 创建运行器
    runner = Run(token=TOKEN)

    # 第一步：下载数据
    print("\n【步骤1】下载原始数据")
    runner.download(
        source_dir="~/.qlib/stock_data/source/tushare",
        start_date="20200101",      # 开始日期（YYYYMMDD格式）
        end_date="20231231",        # 结束日期
        interval="1d",              # 数据间隔（日线）
        delay=0.5,                  # 请求延迟（秒）
        symbols=None                # None表示下载所有主板股票
    )

    # 第二步：标准化数据
    print("\n【步骤2】标准化数据")
    runner.normalize(
        source_dir="~/.qlib/stock_data/source/tushare",
        normalize_dir="~/.qlib/stock_data/normalized/tushare",
        interval="1d"
    )

    # 第三步：转换为Qlib二进制格式
    print("\n【步骤3】转换为Qlib格式")
    print("请运行以下命令：")
    print("python scripts/dump_bin.py dump_all \\")
    print("    --data_path ~/.qlib/stock_data/normalized/tushare \\")
    print("    --qlib_dir ~/.qlib/qlib_data/cn_data \\")
    print("    --freq day \\")
    print("    --include_fields open,close,high,low,volume,factor")

    print("\n数据采集完成！")


if __name__ == "__main__":
    main()
