"""
Tushare数据采集器
"""
import time
import pandas as pd
from typing import Optional
from pathlib import Path
from .base_collector import BaseCollector, BaseNormalize, BaseRun


class TushareCollector(BaseCollector):
    """Tushare数据采集器"""

    def __init__(self, token: str, source_dir: str, start_date: str, end_date: str,
                 interval: str = "1d", delay: float = 0.5):
        """
        初始化Tushare采集器

        Args:
            token: Tushare API token
            source_dir: 数据存储目录
            start_date: 开始日期 (YYYYMMDD)
            end_date: 结束日期 (YYYYMMDD)
            interval: 数据间隔 (1d)
            delay: 请求延迟（秒）
        """
        super().__init__(source_dir, start_date, end_date, interval, delay)
        try:
            import tushare as ts
            ts.set_token(token)
            self.pro = ts.pro_api()
            print("Tushare API 初始化成功")
        except ImportError:
            raise ImportError("请安装 tushare: pip install tushare")

    def get_instrument_list(self, market: str = "主板") -> list:
        """
        获取股票列表

        Args:
            market: 市场类型（主板/创业板/科创板）

        Returns:
            股票代码列表
        """
        df = self.pro.stock_basic(
            exchange='',
            list_status='L',
            market=market,
            fields='ts_code,symbol,name,market'
        )
        print(f"获取到 {len(df)} 只股票")
        return df['ts_code'].tolist()

    def download_data(self, symbols: Optional[list] = None):
        """
        下载日线数据

        Args:
            symbols: 股票代码列表，None表示下载主板所有股票
        """
        if symbols is None:
            symbols = self.get_instrument_list()

        print(f"开始下载 {len(symbols)} 只股票数据")
        print(f"时间范围: {self.start_date} 至 {self.end_date}")

        for i, symbol in enumerate(symbols, 1):
            try:
                # 下载日线数据
                df = self.pro.daily(
                    ts_code=symbol,
                    start_date=self.start_date,
                    end_date=self.end_date,
                    fields='trade_date,open,high,low,close,vol,amount'
                )

                # 下载复权因子
                adj_df = self.pro.adj_factor(
                    ts_code=symbol,
                    start_date=self.start_date,
                    end_date=self.end_date
                )

                if df is not None and not df.empty:
                    # 合并数据
                    df = df.merge(adj_df[['trade_date', 'adj_factor']], on='trade_date', how='left')

                    # 重命名列以匹配Qlib格式
                    df = df.rename(columns={
                        'trade_date': 'date',
                        'vol': 'volume',
                        'adj_factor': 'factor'
                    })

                    # 添加股票代码
                    df['symbol'] = symbol

                    # 排序
                    df = df.sort_values('date')

                    # 保存
                    self.save_to_csv(df, symbol)

                    print(f"[{i}/{len(symbols)}] {symbol}: {len(df)} 条记录")
                else:
                    print(f"[{i}/{len(symbols)}] {symbol}: 无数据")

                time.sleep(self.delay)

            except Exception as e:
                print(f"[{i}/{len(symbols)}] {symbol} 下载失败: {e}")
                continue

        print("数据下载完成")


class TushareNormalize(BaseNormalize):
    """Tushare数据标准化"""

    def normalize_data(self, qlib_data_1d_dir: Optional[str] = None):
        """
        标准化数据为Qlib格式

        标准格式：
            date,instrument,open,close,high,low,volume,factor
        """
        print("开始标准化数据...")
        csv_files = list(self.source_dir.glob("*.csv"))
        print(f"找到 {len(csv_files)} 个CSV文件")

        for i, csv_file in enumerate(csv_files, 1):
            try:
                df = pd.read_csv(csv_file)

                # 确保必需列存在
                required_cols = ['date', 'symbol', 'open', 'close', 'high', 'low', 'volume']
                if not all(col in df.columns for col in required_cols):
                    print(f"[{i}/{len(csv_files)}] {csv_file.name}: 缺少必需列，跳过")
                    continue

                # 处理复权因子
                if 'factor' not in df.columns or df['factor'].isna().all():
                    df['factor'] = 1.0

                # 填充缺失的复权因子
                df['factor'] = df['factor'].fillna(method='ffill').fillna(1.0)

                # 应用复权
                price_cols = ['open', 'close', 'high', 'low']
                for col in price_cols:
                    df[col] = df[col] * df['factor']

                # 重命名symbol为instrument
                df = df.rename(columns={'symbol': 'instrument'})

                # 选择最终列
                df = df[['date', 'instrument', 'open', 'close', 'high', 'low', 'volume', 'factor']]

                # 按日期排序
                df = df.sort_values('date')

                # 保存标准化数据
                output_file = self.normalize_dir / csv_file.name
                df.to_csv(output_file, index=False, encoding='utf-8')

                print(f"[{i}/{len(csv_files)}] {csv_file.name}: {len(df)} 条记录")

            except Exception as e:
                print(f"[{i}/{len(csv_files)}] {csv_file.name} 标准化失败: {e}")
                continue

        print("数据标准化完成")


class Run(BaseRun):
    """命令行运行类"""

    def __init__(self, token: str):
        super().__init__()
        self.token = token

    def download(self, source_dir: str, start_date: str, end_date: str,
                 interval: str = "1d", delay: float = 0.5, symbols: Optional[list] = None):
        """执行下载"""
        self.collector = TushareCollector(
            token=self.token,
            source_dir=source_dir,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
            delay=delay
        )
        self.collector.download_data(symbols=symbols)

    def normalize(self, source_dir: str, normalize_dir: str, interval: str = "1d"):
        """执行标准化"""
        self.normalize = TushareNormalize(
            source_dir=source_dir,
            normalize_dir=normalize_dir,
            interval=interval
        )
        self.normalize.normalize_data()


if __name__ == "__main__":
    # 示例用法
    TOKEN = "your_tushare_token"

    runner = Run(token=TOKEN)

    # 下载数据
    runner.download(
        source_dir="~/.qlib/stock_data/source/tushare",
        start_date="20200101",
        end_date="20231231",
        interval="1d",
        delay=0.5
    )

    # 标准化数据
    runner.normalize(
        source_dir="~/.qlib/stock_data/source/tushare",
        normalize_dir="~/.qlib/stock_data/normalized/tushare",
        interval="1d"
    )
