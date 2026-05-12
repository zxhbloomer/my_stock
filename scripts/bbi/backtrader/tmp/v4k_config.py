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
ATR_MULTIPLIER      = 3.0
HARD_STOP_LOSS      = 0.06
CHIP_EXIT_THRESHOLD = 80.0
MIN_HOLD_DAYS       = 10

INDEX_CODE = "000300.SH"
TOP_N_BEAR = 2

# 涨跌停过滤阈值（主板10%，创业板/科创板20%，统一用9.5%保守判断）
LIMIT_UP_THRESHOLD   = 0.095
LIMIT_DOWN_THRESHOLD = -0.095

OUTPUT_DIR     = Path(__file__).parent / "v4k_output"
STOCK_DATA_DIR = Path(__file__).parent / "v4f_output" / "stock_data"

REAL_CASH = 500_000.0
