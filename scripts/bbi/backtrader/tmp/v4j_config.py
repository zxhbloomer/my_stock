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

# v4j 市场过滤（比 v4i 更宽松）：
# 牛市：close > MA60                    → TOP_N=5（满仓）
# 熊市：close < MA60 AND MA20 < MA60    → TOP_N_BEAR=2（降仓）
# 正常：close < MA60 OR MA20 < MA60     → TOP_N=5（不降仓，只有双重确认才降）
# 注：v4i 的危机空仓（TOP_N=0）去掉，改为最多降到2只
INDEX_CODE = "000300.SH"
TOP_N_BEAR = 2

OUTPUT_DIR     = Path(__file__).parent / "v4j_output"
STOCK_DATA_DIR = Path(__file__).parent / "v4f_output" / "stock_data"

REAL_CASH = 500_000.0
