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
N_WORKERS             = 8

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

OUTPUT_DIR     = Path(__file__).parent / "output"
STOCK_DATA_DIR = OUTPUT_DIR / "stock_data"
KLINE_DATA_DIR = OUTPUT_DIR / "kline_data"
