"""
接口：hk_hold，可以通过数据工具调试和查看数据
描述：获取沪深港股通持股明细，数据来源港交所
      说明：交易所于从2024年8月20开始停止发布日度北向资金数据，改为季度披露
限量：单次最多提取3800条记录，可循环调取，总量不限制
积分：用户积120积分可调取试用，2000积分可正常使用
接口文档: https://tushare.pro/document/2?doc_id=188
本地文档: docs/tushare/tushare.pro/document/20f4f.html

输入参数：code(str,N,交易所代码), ts_code(str,N,TS股票代码),
          trade_date(str,N,交易日期), start_date(str,N,开始日期),
          end_date(str,N,结束日期), exchange(str,N,类型SH/SZ/HK)
输出字段：code,trade_date,ts_code,name,vol,ratio,exchange

同步策略：按交易所+短日期窗口分页增量（trade_date+ts_code+exchange 为主键，upsert）
实测说明：
  - 官方文档支持 start_date/end_date/exchange，单次最多3800条，可循环调取。
  - 不带 exchange 做日期范围调用会触发3800条截断，容易漏日期。
  - 20160628 及之前实测为空；20160629 起已有 SH 数据，20161205 起有 SH/SZ。
  - 早期存在真实空交易日，例如 20160701 单日返回0条，不能按所有SSE交易日强制补齐。
  - 2024-08-20 起交易所停止发布日度北向持股，接口仍返回 HK 南向持股。
表名：066_hk_hold
迁移说明：tushare schema 中无此表，无需迁移
用法: python 066_hk_hold.py [--start YYYYMMDD] [--end YYYYMMDD] [--window-days N] [--page-size N]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "066_hk_hold"
DEFAULT_START = "20160629"  # 实测 hk_hold 从 20160629 开始有 SH 数据；20160628 及更早接口为空
FIELDS = "code,trade_date,ts_code,name,vol,ratio,exchange"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "exchange"]
EXCHANGES = ("SH", "SZ", "HK")
DEFAULT_PAGE_SIZE = 3800
DEFAULT_WINDOW_DAYS = 4

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    code        VARCHAR(20),
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    name        TEXT,
    vol         BIGINT,
    ratio       FLOAT,
    exchange    VARCHAR(5)  NOT NULL,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, exchange)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def trade_date_windows(trade_dates, window_days):
    if window_days <= 0:
        raise ValueError("window_days must be > 0")
    for i in range(0, len(trade_dates), window_days):
        chunk = trade_dates[i:i + window_days]
        if chunk:
            yield chunk[0], chunk[-1]


def fetch_exchange_range_pages(pro, start_date, end_date, exchange, page_size):
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    offset = 0
    while True:
        df = pro.hk_hold(
            start_date=start_date,
            end_date=end_date,
            exchange=exchange,
            fields=FIELDS,
            limit=page_size,
            offset=offset,
        )
        if df is None or df.empty:
            break
        yield df
        if len(df) < page_size:
            break
        offset += page_size


def normalize_hk_hold_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    for col in COLS:
        if col not in df.columns:
            df[col] = None
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    if "vol" in df.columns:
        df["vol"] = pd.to_numeric(df["vol"], errors="coerce").astype("Int64")
    if "ratio" in df.columns:
        df["ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def sync_range(pro, engine, dates, window_days, page_size):
    total_rows, t0 = 0, datetime.now()
    windows = list(trade_date_windows(dates, window_days))
    for i, (window_start, window_end) in enumerate(windows, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, window_start, "ing")
        window_rows = 0
        for exchange in EXCHANGES:
            for page_no, df in enumerate(fetch_exchange_range_pages(
                pro, window_start, window_end, exchange, page_size
            ), 1):
                df = normalize_hk_hold_df(df)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
                window_rows += rows
                elapsed = (datetime.now() - t0).seconds
                print(
                    f"  [{i:4d}/{len(windows)}] {window_start}-{window_end} "
                    f"{exchange} 第{page_no:03d}页 {rows}条  累计{total_rows}条  "
                    f"{elapsed//60}分{elapsed%60}秒",
                    flush=True,
                )
        mark_sync(engine, f"{TABLE}.py", TABLE, window_end, "ok")
        if window_rows == 0:
            elapsed = (datetime.now() - t0).seconds
            print(
                f"  [{i:4d}/{len(windows)}] {window_start}-{window_end} 0条  "
                f"{elapsed//60}分{elapsed%60}秒",
                flush=True,
            )
    return total_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
                        help="每次按交易日切分的窗口大小，默认4个交易日")
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE,
                        help="hk_hold 单页大小，官方单次最多3800")
    args = parser.parse_args()
    if args.window_days <= 0:
        parser.error("--window-days 必须大于 0")
    if args.page_size <= 0 or args.page_size > DEFAULT_PAGE_SIZE:
        parser.error("--page-size 必须在 1~3800 之间")

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    dates = get_trade_dates(pro, start, args.end)

    total_rows = sync_range(pro, engine, dates, args.window_days, args.page_size)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
