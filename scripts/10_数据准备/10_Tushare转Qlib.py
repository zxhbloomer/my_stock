#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tushare数据转Qlib二进制格式转换工具

功能:
1. 从PostgreSQL读取Tushare格式股票数据（2008-01-01起）
2. 转换为Qlib标准二进制格式(.bin文件)
3. 智能增量更新(自动检测上次转换时间)
4. 元数据跟踪(.metadata.yaml)
5. 进度显示和完整日志

作者: Claude Code
创建时间: 2025-11-14
数据范围: 2008-01-01 至最新交易日
"""

import argparse
import sys
import time
import yaml
import logging
import psycopg2
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from typing import Optional, Dict, List


# ==================== 配置类 ====================

class Config:
    """配置管理类"""

    # PostgreSQL配置
    PG_HOST = "127.0.0.1"
    PG_PORT = 5432
    PG_DATABASE = "my_stock"
    PG_USER = "root"
    PG_PASSWORD = "123456"

    # 数据起始日期（用户指定）
    START_DATE = "2008-01-01"

    # Qlib数据路径
    QLIB_DIR = Path(r"D:\Data\my_stock")

    # 临时目录
    TEMP_DIR = Path(__file__).parent.parent / "temp_qlib_data"

    # 元数据文件
    METADATA_FILE = ".metadata.yaml"

    # 日志配置
    LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
    LOG_LEVEL = logging.INFO


# ==================== 日志配置 ====================

def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else Config.LOG_LEVEL

    # 确保日志目录存在
    Config.QLIB_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=level,
        format=Config.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                Config.QLIB_DIR / "tushare_to_qlib.log",
                mode='a',
                encoding='utf-8'
            )
        ]
    )
    return logging.getLogger(__name__)


# ==================== 数据库操作 ====================

class DatabaseManager:
    """PostgreSQL数据库管理器"""

    def __init__(self, logger):
        self.logger = logger
        self.conn = None

    def connect(self):
        """连接数据库"""
        try:
            self.conn = psycopg2.connect(
                host=Config.PG_HOST,
                port=Config.PG_PORT,
                database=Config.PG_DATABASE,
                user=Config.PG_USER,
                password=Config.PG_PASSWORD
            )
            self.logger.info(f"✅ 数据库连接成功: {Config.PG_HOST}:{Config.PG_PORT}/{Config.PG_DATABASE}")
        except Exception as e:
            self.logger.error(f"❌ 数据库连接失败: {e}")
            raise

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.logger.info("数据库连接已关闭")

    def get_latest_trade_date(self) -> Optional[str]:
        """获取最新交易日期"""
        sql = f"""
        SELECT MAX(trade_date)
        FROM tushare.stock_daily
        WHERE trade_date >= '{Config.START_DATE}'
        """
        with self.conn.cursor() as cur:
            cur.execute(sql)
            result = cur.fetchone()
            return str(result[0]) if result and result[0] else None

    def get_listed_stocks(self) -> pd.DataFrame:
        """获取上市股票列表(排除退市股票)"""
        sql = """
        SELECT
            ts_code,
            list_date,
            COALESCE(delist_date, '2099-12-31') as delist_date
        FROM tushare.stock_basic
        WHERE list_status = 'L'
        ORDER BY ts_code
        """
        return pd.read_sql(sql, self.conn)

    def export_daily_data(self, last_date: Optional[str] = None) -> pd.DataFrame:
        """
        导出日线数据（从2008-01-01开始）

        Args:
            last_date: 上次更新日期,如果为None则导出全部数据
        """
        # 增量模式：last_date之后的数据
        # 全量模式：2008-01-01之后的所有数据
        if last_date:
            date_filter = f"AND d.trade_date > '{last_date}'"
        else:
            date_filter = ""

        sql = f"""
        SELECT
            d.ts_code,
            d.trade_date as date,
            d.open,
            d.high,
            d.low,
            d.close,
            d.volume,
            d.amount,
            f.adj_factor as factor
        FROM tushare.stock_daily d
        INNER JOIN tushare.stock_basic b ON d.ts_code = b.ts_code
        LEFT JOIN tushare.stock_adjfactor f
            ON d.ts_code = f.ts_code AND d.trade_date = f.trade_date
        WHERE b.list_status = 'L'
          AND d.trade_date >= '{Config.START_DATE}'
          {date_filter}
        ORDER BY d.ts_code, d.trade_date
        """

        mode_desc = f"增量: > {last_date}" if last_date else f"全量: >= {Config.START_DATE}"
        self.logger.info(f"开始导出股票数据... ({mode_desc})")

        df = pd.read_sql(sql, self.conn)
        self.logger.info(f"✅ 股票数据导出完成: {len(df):,} 条记录")

        return df

    def export_index_daily_data(self, last_date: Optional[str] = None) -> pd.DataFrame:
        """
        导出指数日线数据（从2008-01-01开始）

        Args:
            last_date: 上次更新日期,如果为None则导出全部数据
        """
        if last_date:
            date_filter = f"AND trade_date > '{last_date}'"
        else:
            date_filter = ""

        sql = f"""
        SELECT
            ts_code,
            trade_date as date,
            open,
            high,
            low,
            close,
            volume,
            amount,
            1.0 as factor
        FROM tushare.index_daily
        WHERE trade_date >= '{Config.START_DATE}'
          {date_filter}
        ORDER BY ts_code, trade_date
        """

        mode_desc = f"增量: > {last_date}" if last_date else f"全量: >= {Config.START_DATE}"
        self.logger.info(f"开始导出指数数据... ({mode_desc})")

        df = pd.read_sql(sql, self.conn)
        self.logger.info(f"✅ 指数数据导出完成: {len(df):,} 条记录")

        return df

    def get_trading_calendar(self, last_date: Optional[str] = None) -> List[str]:
        """
        获取交易日历（从2008-01-01开始）

        Args:
            last_date: 上次更新日期,如果为None则获取全部交易日
        """
        if last_date:
            date_filter = f"AND cal_date > '{last_date}'"
        else:
            date_filter = ""

        sql = f"""
        SELECT DISTINCT cal_date
        FROM tushare.others_calendar
        WHERE is_open = 1
          AND exchange = 'SSE'
          AND cal_date >= '{Config.START_DATE}'
          {date_filter}
        ORDER BY cal_date
        """

        with self.conn.cursor() as cur:
            cur.execute(sql)
            return [str(row[0]) for row in cur.fetchall()]

    def get_index_constituents(self, index_code: str) -> tuple:
        """
        获取指数成分股列表（最新日期）

        Args:
            index_code: 指数代码（如 000300.SH）

        Returns:
            (股票代码列表, 成分股日期)
        """
        # 获取最新日期
        sql_date = f"""
        SELECT MAX(trade_date)
        FROM tushare.index_weight
        WHERE index_code = '{index_code}'
        """

        with self.conn.cursor() as cur:
            cur.execute(sql_date)
            latest_date = cur.fetchone()[0]

        if not latest_date:
            return [], None

        # 获取成分股
        sql = f"""
        SELECT DISTINCT con_code
        FROM tushare.index_weight
        WHERE index_code = '{index_code}'
          AND trade_date = '{latest_date}'
        ORDER BY con_code
        """

        with self.conn.cursor() as cur:
            cur.execute(sql)
            stocks = [row[0] for row in cur.fetchall()]

        return stocks, str(latest_date)


# ==================== 股票代码转换 ====================

def convert_ts_code_to_qlib(ts_code: str) -> str:
    """
    转换Tushare代码为Qlib格式（支持股票和指数）

    Args:
        ts_code: Tushare格式代码 (如 000001.SZ, 600000.SH, 000300.SH)

    Returns:
        Qlib格式代码 (如 SZ000001, SH600000, SH000300)

    Examples:
        >>> convert_ts_code_to_qlib('000001.SZ')
        'SZ000001'
        >>> convert_ts_code_to_qlib('600000.SH')
        'SH600000'
        >>> convert_ts_code_to_qlib('000300.SH')
        'SH000300'
    """
    if '.' not in ts_code:
        return ts_code

    symbol, exchange = ts_code.split('.')
    return f"{exchange}{symbol}"


# ==================== 元数据管理 ====================

class MetadataManager:
    """元数据管理器"""

    def __init__(self, qlib_dir: Path, logger):
        self.qlib_dir = qlib_dir
        self.metadata_file = qlib_dir / Config.METADATA_FILE
        self.logger = logger

    def read(self) -> Optional[Dict]:
        """读取元数据"""
        if not self.metadata_file.exists():
            return None

        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.logger.warning(f"读取元数据失败: {e}")
            return None

    def write(self, metadata: Dict):
        """写入元数据"""
        try:
            self.qlib_dir.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                yaml.dump(metadata, f, allow_unicode=True, default_flow_style=False)
            self.logger.info(f"✅ 元数据已保存: {self.metadata_file}")
        except Exception as e:
            self.logger.error(f"❌ 元数据保存失败: {e}")

    def determine_mode(self, force_rebuild: bool, latest_db_date: str) -> str:
        """
        判断转换模式

        Returns:
            'full': 全量转换
            'incremental': 增量转换
            'skip': 无需转换
        """
        if force_rebuild:
            self.logger.info("🔄 强制重建模式")
            return 'full'

        metadata = self.read()
        if not metadata:
            self.logger.info("🆕 首次转换,执行全量转换")
            return 'full'

        last_update_date = metadata.get('last_update_date')
        if not last_update_date:
            self.logger.warning("元数据缺少last_update_date,执行全量转换")
            return 'full'

        if latest_db_date <= last_update_date:
            self.logger.info(f"✅ 数据已是最新(DB: {latest_db_date}, 上次: {last_update_date})")
            return 'skip'

        self.logger.info(f"📈 检测到新数据: {last_update_date} → {latest_db_date}")
        return 'incremental'


# ==================== 数据转换 ====================

class DataConverter:
    """数据转换器 - 直接写入Qlib二进制格式"""

    def __init__(self, logger, qlib_dir: Path):
        self.logger = logger
        self.qlib_dir = qlib_dir
        self.calendars_dir = qlib_dir / "calendars"
        self.instruments_dir = qlib_dir / "instruments"
        self.features_dir = qlib_dir / "features"

    def prepare_directories(self):
        """准备Qlib目录结构 - 每次全新创建"""
        import shutil

        # 删除旧的数据目录
        if self.features_dir.exists():
            self.logger.info(f"🗑️ 删除旧的features目录...")
            shutil.rmtree(self.features_dir)

        if self.calendars_dir.exists():
            self.logger.info(f"🗑️ 删除旧的calendars目录...")
            shutil.rmtree(self.calendars_dir)

        if self.instruments_dir.exists():
            self.logger.info(f"🗑️ 删除旧的instruments目录...")
            shutil.rmtree(self.instruments_dir)

        # 重新创建目录
        self.qlib_dir.mkdir(parents=True, exist_ok=True)
        self.calendars_dir.mkdir(parents=True, exist_ok=True)
        self.instruments_dir.mkdir(parents=True, exist_ok=True)
        self.features_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(f"✅ Qlib目录结构已创建: {self.qlib_dir}")

    def save_calendar(self, dates: List[str]):
        """保存交易日历"""
        calendar_file = self.calendars_dir / "day.txt"
        with open(calendar_file, 'w') as f:
            f.write('\n'.join(dates))
        self.logger.info(f"✅ 交易日历已保存: {len(dates)} 个交易日")

    def save_instruments(self, df: pd.DataFrame):
        """
        保存股票列表

        Args:
            df: 包含symbol, earliest_date, latest_date的DataFrame
        """
        instruments_file = self.instruments_dir / "all.txt"

        lines = []
        for _, row in df.iterrows():
            # 格式: symbol\tstart_date\tend_date
            lines.append(f"{row['symbol']}\t{row['earliest_date']}\t{row['latest_date']}")

        with open(instruments_file, 'w') as f:
            f.write('\n'.join(lines))

        self.logger.info(f"✅ 股票列表已保存: {len(lines)} 只股票")

    def save_market_files(self, db: 'DatabaseManager'):
        """
        保存市场文件（指数成分股）- 每次全量重新生成
        格式：symbol\tstart_date\tend_date（与all.txt保持一致）

        Args:
            db: 数据库管理器
        """
        # 指数映射：文件名 -> 指数代码
        index_mapping = {
            'csi300': '000300.SH',  # 沪深300
            'csi500': '000905.SH',  # 中证500
        }

        self.logger.info("生成市场文件...")

        # 读取all.txt获取每只股票的起止日期
        all_file = self.instruments_dir / "all.txt"
        stock_dates = {}
        if all_file.exists():
            with open(all_file, 'r') as f:
                for line in f:
                    parts = line.strip().split('\t')
                    if len(parts) == 3:
                        stock_dates[parts[0]] = (parts[1], parts[2])

        for market_name, index_code in index_mapping.items():
            # 获取成分股
            stocks, constituent_date = db.get_index_constituents(index_code)

            if not stocks:
                self.logger.warning(f"  ⚠️ {market_name} ({index_code}) 无成分股数据")
                continue

            # 转换为Qlib格式并获取日期范围
            lines = []
            for ts_code in stocks:
                qlib_code = convert_ts_code_to_qlib(ts_code)

                # 从all.txt获取该股票的起止日期
                if qlib_code in stock_dates:
                    start_date, end_date = stock_dates[qlib_code]
                    lines.append(f"{qlib_code}\t{start_date}\t{end_date}")
                else:
                    # 如果在all.txt中找不到（理论上不应该），使用默认值
                    self.logger.warning(f"  ⚠️ {qlib_code} 不在all.txt中，使用默认日期范围")
                    lines.append(f"{qlib_code}\t{Config.START_DATE}\t2099-12-31")

            # 写入文件（3列格式：symbol\tstart_date\tend_date）
            market_file = self.instruments_dir / f"{market_name}.txt"
            with open(market_file, 'w') as f:
                f.write('\n'.join(lines))

            self.logger.info(f"  ✅ {market_name}.txt: {len(lines)}只股票 (成分股日期: {constituent_date})")

    def write_bin_file(self, symbol: str, field: str, dates_index: Dict[str, int],
                       data: pd.Series, all_dates: List[str]):
        """
        写入单个字段的二进制文件

        Args:
            symbol: 股票代码
            field: 字段名
            dates_index: 日期到索引的映射
            data: 数据Series (index=date, value=数值)
            all_dates: 所有交易日列表
        """
        # 创建股票目录
        stock_dir = self.features_dir / symbol.lower()
        stock_dir.mkdir(parents=True, exist_ok=True)

        # 二进制文件路径
        bin_file = stock_dir / f"{field.lower()}.day.bin"

        # 准备数据数组
        n_dates = len(all_dates)
        arr = np.full(n_dates, np.nan, dtype=np.float32)

        # 填充数据
        for date_str, value in data.items():
            if date_str in dates_index:
                idx = dates_index[date_str]
                arr[idx] = value

        # 写入二进制文件（Qlib格式：第一个float是起始索引）
        if not np.all(np.isnan(arr)):
            # 找到第一个非NaN的位置
            valid_indices = np.where(~np.isnan(arr))[0]
            if len(valid_indices) > 0:
                start_idx = valid_indices[0]
                end_idx = valid_indices[-1] + 1

                # 写入格式：[start_index, data...]
                with open(bin_file, 'wb') as f:
                    np.array([start_idx], dtype=np.float32).tofile(f)
                    arr[start_idx:end_idx].astype(np.float32).tofile(f)

    def convert_to_qlib(self, df: pd.DataFrame, all_dates: List[str]):
        """
        转换为Qlib二进制格式

        Args:
            df: 完整数据DataFrame
            all_dates: 所有交易日列表
        """
        if df.empty:
            self.logger.warning("⚠️ 数据为空，跳过转换")
            return

        # 转换股票代码
        df['symbol'] = df['ts_code'].apply(convert_ts_code_to_qlib)
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')

        # 创建日期索引映射
        dates_index = {date: idx for idx, date in enumerate(all_dates)}

        # 字段列表
        fields = ['open', 'high', 'low', 'close', 'volume', 'amount', 'factor']

        # 按股票分组处理
        stock_groups = df.groupby('symbol')
        stock_count = len(stock_groups)

        self.logger.info(f"开始转换为Qlib二进制格式...")

        with tqdm(total=stock_count, desc="转换股票数据") as pbar:
            for symbol, group in stock_groups:
                # 为每个字段写入二进制文件
                for field in fields:
                    if field in group.columns:
                        data = group.set_index('date')[field]
                        self.write_bin_file(symbol, field, dates_index, data, all_dates)

                pbar.update(1)

        self.logger.info(f"✅ Qlib转换完成: {stock_count} 只股票")

        # 保存股票列表
        instruments_df = df.groupby('symbol')['date'].agg(['min', 'max']).reset_index()
        instruments_df.columns = ['symbol', 'earliest_date', 'latest_date']
        self.save_instruments(instruments_df)


# ==================== 主流程 ====================

def main():
    """主函数"""

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description='Tushare数据转Qlib格式转换工具（每次全量重建）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 默认全量转换
  python 00_tushare_to_qlib.py

  # 指定输出路径
  python 00_tushare_to_qlib.py --output D:\\Data\\my_stock

  # 显示详细日志
  python 00_tushare_to_qlib.py --verbose
        """
    )

    parser.add_argument(
        '--output',
        type=str,
        default=str(Config.QLIB_DIR),
        help=f'输出目录 (默认: {Config.QLIB_DIR})'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='显示详细日志'
    )

    args = parser.parse_args()

    # 设置日志
    logger = setup_logging(args.verbose)

    # 开始转换
    start_time = time.time()
    logger.info("=" * 70)
    logger.info("Tushare → Qlib 数据转换工具（全量重建模式）")
    logger.info(f"数据范围: {Config.START_DATE} 至最新交易日")
    logger.info(f"输出路径: {args.output}")
    logger.info("=" * 70)

    qlib_dir = Path(args.output)
    db = None
    converter = None

    try:
        # 1. 连接数据库
        db = DatabaseManager(logger)
        db.connect()

        # 2. 获取最新交易日期
        latest_db_date = db.get_latest_trade_date()
        logger.info(f"📅 数据库最新交易日: {latest_db_date}")

        # 3. 准备转换（每次全量重建）
        converter = DataConverter(logger, qlib_dir)
        converter.prepare_directories()

        # 4. 获取交易日历
        logger.info("获取交易日历...")
        all_dates = db.get_trading_calendar(last_date=None)  # 全部交易日
        converter.save_calendar(all_dates)

        # 5. 导出股票数据（全量）
        logger.info(f"开始导出股票数据... (全量: >= {Config.START_DATE})")
        df_stock = db.export_daily_data(last_date=None)

        # 6. 导出指数数据（全量）
        logger.info(f"开始导出指数数据... (全量: >= {Config.START_DATE})")
        df_index = db.export_index_daily_data(last_date=None)

        # 7. 合并股票和指数数据
        df = pd.concat([df_stock, df_index], ignore_index=True)

        if df.empty:
            logger.warning("⚠️ 无数据可转换")
            return

        logger.info(f"✅ 合并数据: 股票{len(df_stock):,}条 + 指数{len(df_index):,}条 = 总计{len(df):,}条")

        # 8. 转换为Qlib格式（会生成all.txt）
        converter.convert_to_qlib(df, all_dates)

        # 9. 生成市场文件（依赖all.txt，必须在convert_to_qlib之后）
        converter.save_market_files(db)

        # 10. 更新元数据
        metadata_mgr = MetadataManager(qlib_dir, logger)
        metadata = {
            'version': '1.0',
            'start_date': Config.START_DATE,
            'last_update_date': latest_db_date,
            'last_update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'conversion_mode': 'full',
            'total_stocks': df_stock['ts_code'].nunique() if not df_stock.empty else 0,
            'total_indices': df_index['ts_code'].nunique() if not df_index.empty else 0,
            'total_instruments': df['ts_code'].nunique(),
            'total_records': len(df),
            'earliest_date': df['date'].min(),
            'latest_date': df['date'].max(),
        }
        metadata_mgr.write(metadata)

        # 11. 完成
        elapsed = time.time() - start_time
        logger.info("=" * 70)
        logger.info(f"✅ 转换完成!")
        logger.info(f"📊 统计:")
        logger.info(f"  - 股票数量: {metadata['total_stocks']:,}")
        logger.info(f"  - 指数数量: {metadata['total_indices']:,}")
        logger.info(f"  - 总工具数: {metadata['total_instruments']:,}")
        logger.info(f"  - 记录数量: {metadata['total_records']:,}")
        logger.info(f"  - 日期范围: {metadata['earliest_date']} ~ {metadata['latest_date']}")
        logger.info(f"  - 耗时: {elapsed/60:.1f} 分钟")
        logger.info("=" * 70)

    except KeyboardInterrupt:
        logger.warning("\n⚠️ 用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 转换失败: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # 清理资源
        if db:
            db.close()


if __name__ == '__main__':
    main()
