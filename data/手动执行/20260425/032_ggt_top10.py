"""
接口：ggt_top10，可以通过数据工具调试和查看数据
描述：获取港股通每日成交数据，其中包括沪市、深市详细数据，每天18~20点之间完成当日更新
限量：无限制
权限：无特殊权限要求
接口文档: https://tushare.pro/document/2?doc_id=48
本地文档: docs/tushare/tushare.pro/document/22643.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期),
          market_type(str,N,市场类型)
输出字段：trade_date,ts_code,name,close,p_change,rank,market_type,amount,net_amount,
          sh_amount,sh_net_amount,sh_buy,sh_sell,sz_amount,sz_net_amount,sz_buy,sz_sell

同步策略：按日期范围分页增量（trade_date 为主键维度，upsert）
表名：032_ggt_top10
迁移说明：tushare schema 中无此表，无需迁移
用法: python 032_ggt_top10.py [--start YYYYMMDD] [--end YYYYMMDD] [--page-size 300]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "032_ggt_top10"
DEFAULT_START = "20141117"  # 港股通（沪）开通日期；港股通（深）2016-12-05开通
FIELDS = "trade_date,ts_code,name,close,p_change,rank,market_type,amount,net_amount,sh_amount,sh_net_amount,sh_buy,sh_sell,sz_amount,sz_net_amount,sz_buy,sz_sell"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "market_type"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date     DATE        NOT NULL,
    ts_code        VARCHAR(15) NOT NULL,
    name           VARCHAR(50),
    close          FLOAT,
    p_change       FLOAT,
    rank           INTEGER,
    market_type    VARCHAR(5)  NOT NULL,
    amount         FLOAT,
    net_amount     FLOAT,
    sh_amount      FLOAT,
    sh_net_amount  FLOAT,
    sh_buy         FLOAT,
    sh_sell        FLOAT,
    sz_amount      FLOAT,
    sz_net_amount  FLOAT,
    sz_buy         FLOAT,
    sz_sell        FLOAT,
    update_time    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, market_type)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

FLOAT_COLS = ["close","p_change","amount","net_amount","sh_amount","sh_net_amount",
              "sh_buy","sh_sell","sz_amount","sz_net_amount","sz_buy","sz_sell"]


def month_ranges(start, end):
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts > end_ts:
        return []
    ranges = []
    cur = start_ts
    while cur <= end_ts:
        month_end = cur + pd.offsets.MonthEnd(0)
        range_end = min(month_end, end_ts)
        ranges.append((cur.strftime("%Y%m%d"), range_end.strftime("%Y%m%d")))
        cur = range_end + pd.Timedelta(days=1)
    return ranges


def normalize_ggt_top10_df(df):
    if df is None or df.empty:
        return pd.DataFrame(columns=COLS)
    df = df.copy()
    for col in COLS:
        if col not in df.columns:
            df[col] = None
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "rank" in df.columns:
        df["rank"] = pd.to_numeric(df["rank"], errors="coerce").astype("Int64")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def fetch_range_pages(pro, start_date, end_date, fields, page_size):
    if page_size <= 0:
        raise ValueError("page_size must be > 0")
    offset = 0
    while True:
        df = pro.ggt_top10(
            start_date=start_date,
            end_date=end_date,
            limit=page_size,
            offset=offset,
            fields=fields,
        )
        if df is None or df.empty:
            break
        yield df
        if len(df) < page_size:
            break
        offset += page_size


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def sync_range(pro, engine, start, end, page_size):
    total_rows, t0 = 0, datetime.now()
    ranges = month_ranges(start, end)
    for range_no, (range_start, range_end) in enumerate(ranges, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, range_end, "ing")
        range_rows = 0
        for page_no, df in enumerate(fetch_range_pages(pro, range_start, range_end, FIELDS, page_size), 1):
            df = normalize_ggt_top10_df(df)
            rows = upsert_df(engine, df, TABLE, COLS, PK)
            total_rows += rows
            range_rows += rows
            elapsed = (datetime.now() - t0).seconds
            print(
                f"  [{range_no:3d}/{len(ranges)}] {range_start}-{range_end} "
                f"第{page_no:03d}页 {rows}条  累计{total_rows}条  {elapsed//60}分{elapsed%60}秒",
                flush=True,
            )
        mark_sync(engine, f"{TABLE}.py", TABLE, range_end, "ok")
        if range_rows == 0:
            elapsed = (datetime.now() - t0).seconds
            print(
                f"  [{range_no:3d}/{len(ranges)}] {range_start}-{range_end} 0条  "
                f"{elapsed//60}分{elapsed%60}秒",
                flush=True,
            )
    return total_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--page-size", type=int, default=300,
                        help="ggt_top10 日期范围分页大小")
    args = parser.parse_args()
    if args.page_size <= 0:
        parser.error("--page-size 必须大于 0")

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    total_rows = sync_range(pro, engine, start, args.end, args.page_size)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
