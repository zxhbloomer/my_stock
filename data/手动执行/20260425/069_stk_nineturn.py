"""
接口：stk_nineturn，可以通过数据工具调试和查看数据
描述：神奇九转（又称"九转序列"）是一种基于技术分析的股票趋势反转指标，
      通过识别股价连续9天的特定走势来判断潜在反转点，数据从20230101开始
      每天21点更新（涉及分钟数据）
限量：单次提取最大返回10000行数据，可通过股票代码和日期循环获取全部数据
权限：达到6000积分可以调用
接口文档: https://tushare.pro/document/2?doc_id=364
本地文档: docs/tushare/tushare.pro/document/2e625.html

输入参数：ts_code(str,N,股票代码), trade_date(str,N,交易日期),
          freq(str,N,频率daily), start_date(str,N,开始时间),
          end_date(str,N,结束时间)
输出字段：ts_code,trade_date,freq,open,high,low,close,vol,amount,
          up_count,down_count,nine_up_turn,nine_down_turn

同步策略：按交易日区间分页增量（ts_code+trade_date+freq 为主键，upsert）
表名：069_stk_nineturn
迁移说明：tushare schema 中无此表，无需迁移
用法: python 069_stk_nineturn.py [--start YYYYMMDD] [--end YYYYMMDD] [--page-size 10000]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "069_stk_nineturn"
DEFAULT_START = "20230101"  # 数据从2023年开始

FIELDS = "ts_code,trade_date,freq,open,high,low,close,vol,amount,up_count,down_count,nine_up_turn,nine_down_turn"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date", "freq"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code        VARCHAR(15) NOT NULL,
    trade_date     DATE        NOT NULL,
    freq           VARCHAR(10) NOT NULL,
    open           FLOAT,
    high           FLOAT,
    low            FLOAT,
    close          FLOAT,
    vol            FLOAT,
    amount         FLOAT,
    up_count       INT,
    down_count     INT,
    nine_up_turn   VARCHAR(10),
    nine_down_turn VARCHAR(10),
    update_time    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date, freq)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

INT_COLS   = ["up_count", "down_count"]
FLOAT_COLS = ["open","high","low","close","vol","amount"]


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def normalize_df(df):
    if df is None or df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def fetch_range_pages(pro, start_date, end_date, page_size):
    frames = []
    offset = 0
    while True:
        df = pro.stk_nineturn(
            freq="daily",
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--page-size", type=int, default=10000)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)

    dates = get_trade_dates(pro, start, args.end)
    if not dates:
        print(f"[跳过] {start}~{args.end} 无交易日")
        return

    total_rows, t0 = 0, datetime.now()
    for i, trade_date in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, trade_date, "ing")
        try:
            df = fetch_range_pages(pro, trade_date, trade_date, args.page_size)
            if df is not None and not df.empty:
                df = normalize_df(df)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
            mark_sync(engine, f"{TABLE}.py", TABLE, trade_date, "ok")
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        print(f"  [{i:4d}/{len(dates)}] {trade_date}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
