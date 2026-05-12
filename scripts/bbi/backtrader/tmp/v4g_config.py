from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None  # None = today

FILTER_MIN_CIRC_MV = 1_000_000  # 万元 = 100亿元
FILTER_MIN_AMOUNT  = 50_000     # 千元 = 5000万元

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

BBI_PERIODS = (5, 10, 20, 60)

INIT_CASH = 500_000.0
TOP_N     = 5
COMM_BUY  = 0.0005
COMM_SELL = 0.0015
MIN_COMM  = 5.0
RISK_FREE = 0.02

ATR_PERIOD          = 14
ATR_MULTIPLIER      = 4.5
HARD_STOP_LOSS      = 0.08
CHIP_EXIT_THRESHOLD = 80.0
MIN_HOLD_DAYS       = 20

# v4g 趋势过滤：close > MA60 AND MA20 > MA60
# 比 v4f 的 MA5>MA20 更稳定，减少熊市底部的假信号
MA20_PERIOD = 20
MA60_PERIOD = 60

# 复用 v4f 的 stock_data（parquet 已含 ma20/ma60 列）
OUTPUT_DIR     = Path(__file__).parent / "v4g_output"
STOCK_DATA_DIR = Path(__file__).parent / "v4f_output" / "stock_data"

REAL_CASH = 500_000.0
