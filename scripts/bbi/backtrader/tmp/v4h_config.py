from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None

FILTER_MIN_CIRC_MV = 1_000_000
FILTER_MIN_AMOUNT  = 50_000

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
# v4h 收紧止损：ATR倍数从4.5降到3.0，硬止损从8%降到6%
ATR_MULTIPLIER      = 3.0
HARD_STOP_LOSS      = 0.06
CHIP_EXIT_THRESHOLD = 80.0
MIN_HOLD_DAYS       = 10  # 最短持仓从20天降到10天，更灵活

# 复用 v4f 的 stock_data
OUTPUT_DIR     = Path(__file__).parent / "v4h_output"
STOCK_DATA_DIR = Path(__file__).parent / "v4f_output" / "stock_data"

REAL_CASH = 500_000.0
