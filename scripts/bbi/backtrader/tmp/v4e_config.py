from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None

FILTER_MIN_LIST_DAYS  = 365
FILTER_MIN_CIRC_MV    = 1_000_000
FILTER_MIN_AMOUNT     = 50_000

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

BBI_PERIODS = (5, 10, 20, 60)

INIT_CASH   = 500_000.0
TOP_N       = 5
COMM_BUY    = 0.0005
COMM_SELL   = 0.0015
MIN_COMM    = 5.0
RISK_FREE   = 0.02

ATR_PERIOD          = 14
ATR_MULTIPLIER      = 4.5
HARD_STOP_LOSS      = 0.08
CHIP_EXIT_THRESHOLD = 80.0
MIN_HOLD_DAYS       = 20

# 数据目录：复用 v4_plan_1 的 parquet 数据
OUTPUT_DIR     = Path(__file__).parent / "v4e_output"
STOCK_DATA_DIR = Path(__file__).parent.parent / "v4_plan_1" / "output" / "stock_data"

# === v4_enhanced 新增参数 ===
MA60_SLOPE_LOOKBACK  = 10      # MA60 斜率回看天数
RISK_PER_STOCK_PCT   = 0.02    # 每只股票风险预算占总资产比例
ATR_POSITION_MULT    = 2.0     # ATR 仓位乘数
ATR_SMOOTH_DAYS      = 5       # ATR 平滑天数
MAX_EXPOSURE         = 0.95    # 最大总仓位比例
MIN_POSITION_PCT     = 0.10    # 单只最小仓位比例
MAX_POSITION_PCT     = 0.35    # 单只最大仓位比例
