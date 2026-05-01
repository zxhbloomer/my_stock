from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None  # None = today

FILTER_MIN_LIST_DAYS  = 365
FILTER_MIN_CIRC_MV    = 1_000_000  # 万元 = 100亿元
FILTER_MIN_AMOUNT     = 50_000     # 千元 = 5000万元

COMMISSION_BUY        = 0.0005
COMMISSION_SELL       = 0.0015
MIN_COMMISSION        = 5.0

INIT_CASH             = 100_000.0
N_WORKERS             = 4

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

# v2: BBI uses MA(5,10,20,60) instead of DB's MA(3,6,12,24)
BBI_PERIODS = (5, 10, 20, 60)

# v2: MACD momentum confirmation
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# v2: scale-in position management
PYRAMID_FIRST_RATIO  = 0.5   # initial buy: 50% of available cash
PYRAMID_ADD_TRIGGER  = 0.03  # add remaining 50% when profit >= 3%

# v2: ATR trailing stop
ATR_PERIOD     = 14
ATR_MULTIPLIER = 4.5   # v5d: widened from 3.5 → 4.5 to let trends run longer

# v2: minimum hold days before exit signals are evaluated
MIN_HOLD_DAYS  = 20    # v5d: extended from 10 → 20 days to filter short-term noise
# v2: hard stop loss — exit immediately regardless of hold period
HARD_STOP_LOSS = 0.08  # 8%

# v5d: chip distribution exit — winner_rate (Tushare 0-100 scale) above threshold
# signals too many profitable holders → selling pressure → exit early
CHIP_EXIT_THRESHOLD = 80.0  # winner_rate > 80 triggers exit

OUTPUT_DIR     = Path(__file__).parent / "output"
STOCK_DATA_DIR = OUTPUT_DIR / "stock_data"
KLINE_DATA_DIR = OUTPUT_DIR / "kline_data"
