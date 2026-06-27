"""
接口：pledge_stat，可以通过数据工具调试和查看数据
描述：获取股票质押统计数据
限量：单次最大1000
权限：用户需要至少2000积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=110
本地文档: docs/tushare/tushare.pro/document/21eac.html

输入参数：ts_code(str,N,股票代码), end_date(str,N,截止日期)
输出字段：ts_code,end_date,pledge_count,unrest_pledge,rest_pledge,total_share,pledge_ratio

同步策略：按截止日期分页增量（ts_code+end_date 为主键，upsert）
表名：051_pledge_stat
迁移说明：tushare schema 中无此表，无需迁移
用法: python 051_pledge_stat.py [--start YYYYMMDD] [--end YYYYMMDD] [--page-size 3000]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "051_pledge_stat"
DEFAULT_START = "20100101"
FIELDS = "ts_code,end_date,pledge_count,unrest_pledge,rest_pledge,total_share,pledge_ratio"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "end_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code        VARCHAR(15) NOT NULL,
    end_date       DATE        NOT NULL,
    pledge_count   INT,
    unrest_pledge  FLOAT,
    rest_pledge    FLOAT,
    total_share    FLOAT,
    pledge_ratio   FLOAT,
    update_time    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, end_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (end_date);
"""

INT_COLS   = ["pledge_count"]
FLOAT_COLS = ["unrest_pledge", "rest_pledge", "total_share", "pledge_ratio"]


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def fetch_end_date_pages(pro, end_date: str, page_size: int) -> pd.DataFrame:
    frames = []
    offset = 0
    while True:
        df = pro.pledge_stat(
            end_date=end_date,
            fields=FIELDS,
            limit=page_size,
            offset=offset,
        )
        if df is None or df.empty:
            break
        frames.append(df)
        if len(df) < page_size:
            break
        offset += page_size
    if not frames:
        return pd.DataFrame(columns=COLS)
    return pd.concat(frames, ignore_index=True)


def normalize_df(df):
    if df is None or df.empty:
        return df
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--page-size", type=int, default=3000)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    dates = pd.date_range(pd.to_datetime(start), pd.to_datetime(args.end), freq="D").strftime("%Y%m%d").tolist()

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, end_date in enumerate(dates, 1):
        try:
            df = fetch_end_date_pages(pro, end_date, args.page_size)
            if df is not None and not df.empty:
                df = normalize_df(df)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] end_date={end_date}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
