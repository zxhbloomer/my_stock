"""
接口：index_daily，可以通过数据工具调试和查看数据
描述：获取指数每日行情，单次调取最多取8000行记录，可以设置start和end日期补全
权限：用户累积2000积分可调取，5000积分以上频次相对较高
接口文档: https://tushare.pro/document/2?doc_id=95
本地文档: docs/tushare/tushare.pro/document/21bda.html

输入参数：ts_code(str,Y,指数代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,close,open,high,low,pre_close,change,pct_chg,vol,amount

同步策略：默认按近期活跃指数代码增量（ts_code+trade_date 为主键，upsert）
          index_daily 要求 ts_code，无法按交易日全市场拉取；无参数运行会回看并避开全量代码池
表名：122_index_daily
迁移说明：tushare schema 中无此表，无需迁移
用法: python 122_index_daily.py [--start YYYYMMDD] [--end YYYYMMDD]
      [--lookback-days 7] [--active-window-days 45] [--full-scan]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "122_index_daily"
DEFAULT_START = "19910102"
DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_ACTIVE_WINDOW_DAYS = 45
NEW_CODE_DISCOVERY_DAYS = 30
INDEX_DAILY_MARKETS = ["CSI", "SSE", "SZSE", "OTH"]

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


def apply_lookback(start: str, lookback_days: int) -> str:
    if lookback_days <= 0:
        return start
    return (pd.Timestamp(start) - pd.Timedelta(days=lookback_days)).strftime("%Y%m%d")


def normalize_df(df):
    if df is None or df.empty:
        return df
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def fetch_recent_active_codes(engine, end: str, active_window_days: int) -> list[str]:
    """Return codes that recently had index_daily rows, avoiding the 121_index_basic full universe."""
    window_start = (pd.Timestamp(end) - pd.Timedelta(days=active_window_days)).strftime("%Y%m%d")
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT DISTINCT ts_code
                FROM {SCHEMA}."{TABLE}"
                WHERE trade_date >= CAST(:window_start AS date)
            """), {"window_start": window_start}).fetchall()
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def fetch_new_candidate_codes(engine, start: str, end: str) -> list[str]:
    """Discover recently listed index_basic codes for the markets covered by index_daily."""
    list_start = (pd.Timestamp(start) - pd.Timedelta(days=NEW_CODE_DISCOVERY_DAYS)).strftime("%Y%m%d")
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f"""
                SELECT ts_code
                FROM {SCHEMA}."121_index_basic"
                WHERE market = ANY(:markets)
                  AND COALESCE(exp_date, '') = ''
                  AND COALESCE(list_date, '') BETWEEN :list_start AND :end
            """), {
                "markets": INDEX_DAILY_MARKETS,
                "list_start": list_start,
                "end": end,
            }).fetchall()
        return [r[0] for r in rows if r and r[0]]
    except Exception:
        return []


def fetch_basic_candidate_codes(pro, engine, full_scan: bool) -> list[str]:
    """从 121_index_basic 获取 index_daily 候选指数；必要时回退到 API。"""
    try:
        with engine.connect() as conn:
            where = "" if full_scan else "AND market = ANY(:markets) AND COALESCE(exp_date, '') = ''"
            result = conn.execute(text(f"""
                SELECT ts_code
                FROM {SCHEMA}."121_index_basic"
                WHERE 1=1 {where}
            """), {"markets": INDEX_DAILY_MARKETS})
            codes = [r[0] for r in result if r[0]]
            if codes:
                return codes
    except Exception:
        pass

    codes = set(PRIORITY_CODES)
    markets = ["MSCI", "CSI", "SSE", "SZSE", "CICC", "SW", "OTH"] if full_scan else INDEX_DAILY_MARKETS
    for market in markets:
        try:
            df = pro.index_basic(market=market, fields="ts_code")
            if df is not None and not df.empty:
                codes.update(df["ts_code"].tolist())
        except Exception:
            pass
    return list(codes)


def fetch_index_codes(pro, engine, start: str, end: str, active_window_days: int, full_scan: bool) -> list[str]:
    codes = set(PRIORITY_CODES)
    if full_scan:
        codes.update(fetch_basic_candidate_codes(pro, engine, full_scan=True))
        return sorted(codes)

    active_codes = fetch_recent_active_codes(engine, end, active_window_days)
    codes.update(active_codes)
    codes.update(fetch_new_candidate_codes(engine, start, end))

    if len(codes) == len(PRIORITY_CODES):
        codes.update(fetch_basic_candidate_codes(pro, engine, full_scan=False))
    return sorted(codes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--active-window-days", type=int, default=DEFAULT_ACTIVE_WINDOW_DAYS)
    parser.add_argument("--full-scan", action="store_true")
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    raw_start = args.start or get_start(engine)
    start = raw_start if args.start else apply_lookback(raw_start, args.lookback_days)
    dates = get_trade_dates(pro, start, args.end)
    if not dates:
        print(f"[跳过] {start}~{args.end} 无交易日")
        return

    codes = fetch_index_codes(pro, engine, start, args.end, args.active_window_days, args.full_scan)
    print(f"共 {len(codes)} 个指数 | start={start} end={args.end} | full_scan={args.full_scan}")

    mark_sync(engine, f"{TABLE}.py", TABLE, dates[0], "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.index_daily(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                df = normalize_df(df)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        # time.sleep(0.2)

    mark_sync(engine, f"{TABLE}.py", TABLE, dates[-1], "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
