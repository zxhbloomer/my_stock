"""
接口：index_daily，可以通过数据工具调试和查看数据
描述：获取指数每日行情，单次调取最多取8000行记录，可以设置start和end日期补全
权限：用户累积2000积分可调取，5000积分以上频次相对较高
接口文档: https://tushare.pro/document/2?doc_id=95
本地文档: docs/tushare/tushare.pro/document/21bda.html

输入参数：ts_code(str,Y,指数代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount

同步策略：按指数代码循环增量（ts_code+trade_date 为主键，upsert）
          注意：需先从 121_index_basic 获取指数列表，按代码循环拉取
表名：122_index_daily
迁移说明：tushare schema 中无此表，无需迁移
用法: python 122_index_daily.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "122_index_daily"
DEFAULT_START = "19910102"

FIELDS = "ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(20) NOT NULL,
    trade_date  DATE        NOT NULL,
    close       FLOAT,
    open        FLOAT,
    high        FLOAT,
    low         FLOAT,
    pre_close   FLOAT,
    change      FLOAT,
    pct_chg     FLOAT,
    vol         FLOAT,
    amount      FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""

FLOAT_COLS = ["close","open","high","low","pre_close","change","pct_chg","vol","amount"]

# 常用大盘指数，优先同步
PRIORITY_CODES = [
    "000001.SH","000300.SH","000905.SH","000016.SH","000852.SH",
    "399001.SZ","399006.SZ","399300.SZ","399005.SZ","399016.SZ",
]


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def fetch_index_codes(pro, engine):
    """从 121_index_basic 获取指数列表，若表不存在则用优先列表"""
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text(f'SELECT ts_code FROM {SCHEMA}."121_index_basic"')
            )
            codes = [r[0] for r in result]
            if codes:
                return codes
    except Exception:
        pass
    # 回退：直接从API获取
    codes = set(PRIORITY_CODES)
    for market in ["SSE","SZSE","CSI","SW","CICC","OTH"]:
        try:
            df = pro.index_basic(market=market, fields="ts_code")
            if df is not None and not df.empty:
                codes.update(df["ts_code"].tolist())
        except Exception:
            pass
    return list(codes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    codes = fetch_index_codes(pro, engine)
    print(f"共 {len(codes)} 个指数")

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.index_daily(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception as e:
            print(f"  [SKIP] {code}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        time.sleep(0.2)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
