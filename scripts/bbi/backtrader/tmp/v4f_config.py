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

# v4f 新增：条件B趋势过滤
# 买入条件：close > MA60 AND MA5 > MA20（短期均线在中期均线上方）
MA5_PERIOD  = 5
MA20_PERIOD = 20
MA60_PERIOD = 60

OUTPUT_DIR     = Path(__file__).parent / "v4f_output"
STOCK_DATA_DIR = OUTPUT_DIR / "stock_data"

REAL_CASH = 500_000.0
