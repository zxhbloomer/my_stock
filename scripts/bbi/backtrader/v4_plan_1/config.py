from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None  # None = today

FILTER_MIN_LIST_DAYS  = 365
FILTER_MIN_CIRC_MV    = 1_000_000  # 万元 = 100亿元
FILTER_MIN_AMOUNT     = 50_000     # 千元 = 5000万元

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

BBI_PERIODS = (5, 10, 20, 60)

# 轮动策略参数
INIT_CASH   = 500_000.0   # 初始资金 50万
TOP_N       = 5           # 每周持仓只数
COMM_BUY    = 0.0005
COMM_SELL   = 0.0015
MIN_COMM    = 5.0
RISK_FREE   = 0.02

# 止损参数（从 v3 移植）
ATR_PERIOD          = 14
ATR_MULTIPLIER      = 4.5    # peak_close - 4.5 * ATR14
HARD_STOP_LOSS      = 0.08   # 亏损 8% 硬止损
CHIP_EXIT_THRESHOLD = 80.0   # winner_rate > 80 触发筹码止损
MIN_HOLD_DAYS       = 20     # 信号类止损最小持仓天数

OUTPUT_DIR     = Path(__file__).parent / "output"
STOCK_DATA_DIR = OUTPUT_DIR / "stock_data"
