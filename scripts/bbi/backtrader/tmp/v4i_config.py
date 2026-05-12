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
ATR_MULTIPLIER      = 3.0   # v4h 收紧
HARD_STOP_LOSS      = 0.06  # v4h 收紧
CHIP_EXIT_THRESHOLD = 80.0
MIN_HOLD_DAYS       = 10    # v4h 收紧

# v4i 新增：市场级别仓位控制
# 用沪深300指数判断市场趋势，动态调整最大持仓数
INDEX_CODE = "000300.SH"
# 大盘 close > MA60：正常持仓 TOP_N=5
# 大盘 MA20 < MA60 且 close < MA60：降仓，最多持 TOP_N_BEAR=2
# 大盘 close < MA60 且 MA20 < MA60 且 MA20 下降：空仓
TOP_N_BEAR   = 2   # 熊市降仓
TOP_N_CRISIS = 0   # 危机空仓

OUTPUT_DIR     = Path(__file__).parent / "v4i_output"
STOCK_DATA_DIR = Path(__file__).parent / "v4f_output" / "stock_data"

REAL_CASH = 500_000.0
