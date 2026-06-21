"""
接口：stk_holdernumber，可以通过数据工具调试和查看数据
描述：获取上市公司股东户数数据，数据不定期公布
限量：单次最大3000，总量不限制
权限：600积分可调取，基础积分每分钟调取100次，5000积分以上频次相对较高
接口文档: https://tushare.pro/document/2?doc_id=166
本地文档: docs/tushare/tushare.pro/document/2cab6.html

输入参数：ts_code(str,N,TS股票代码), ann_date(str,N,公告日期),
          enddate(str,N,截止日期), start_date(str,N,公告开始日期),
          end_date(str,N,公告结束日期)
输出字段：ts_code,ann_date,end_date,holder_num

同步策略：按公告日期范围分页增量（ts_code+ann_date+end_date 为主键，upsert）
表名：058_stk_holdernumber
迁移说明：tushare schema 中无此表，无需迁移
用法: python 058_stk_holdernumber.py [--start YYYYMMDD] [--end YYYYMMDD] [--page-size 3000]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "058_stk_holdernumber"
DEFAULT_START = "20100101"
FIELDS = "ts_code,ann_date,end_date,holder_num"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "ann_date", "end_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code      VARCHAR(15) NOT NULL,
    ann_date     DATE        NOT NULL,
    end_date     DATE        NOT NULL,
    holder_num   BIGINT,
    update_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, ann_date, end_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ann_date ON {SCHEMA}."{TABLE}" (ann_date);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

DATE_COLS = ["ann_date", "end_date"]
INT_COLS  = ["holder_num"]


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def fetch_ann_date_pages(pro, start_date: str, end_date: str, page_size: int) -> pd.DataFrame:
    frames = []
    offset = 0
    while True:
        df = pro.stk_holdernumber(
            start_date=start_date,
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
    for col in DATE_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
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

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    try:
        df = fetch_ann_date_pages(pro, start, args.end, args.page_size)
        if df is not None and not df.empty:
            df = normalize_df(df)
            rows = upsert_df(engine, df, TABLE, COLS, PK)
            total_rows += rows
        else:
            rows = 0
    except Exception:
        raise
    elapsed = (datetime.now() - t0).seconds
    print(f"  [1/1] ann_date={start}~{args.end}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
