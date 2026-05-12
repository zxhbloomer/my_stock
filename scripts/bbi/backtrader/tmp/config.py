from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None

FILTER_MIN_LIST_DAYS  = 365
FILTER_MIN_CIRC_MV    = 1_000_000
FILTER_MIN_AMOUNT     = 50_000

COMMISSION_BUY        = 0.0005
COMMISSION_SELL       = 0.0015
MIN_COMMISSION        = 5.0

INIT_CASH             = 100_000.0
N_WORKERS             = 4

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

BBI_PERIODS = (5, 10, 20, 60)

MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# v3_enhanced: full position entry (no pyramid)
PYRAMID_FIRST_RATIO  = 1.0

ATR_PERIOD     = 14
ATR_MULTIPLIER = 4.5

MIN_HOLD_DAYS  = 20
HARD_STOP_LOSS = 0.08

CHIP_EXIT_THRESHOLD = 80.0

OUTPUT_DIR     = Path(__file__).parent / "output"
STOCK_DATA_DIR = Path(__file__).parent.parent / "v3" / "output" / "stock_data"

# v3_enhanced 新增参数
MA60_SLOPE_LOOKBACK = 10   # MA60 斜率回看天数
FLOW_WINDOW         = 3    # 大单净量累计窗口（天）
FLOW_THRESHOLD      = 0    # 大单净量阈值（>0 即可）
