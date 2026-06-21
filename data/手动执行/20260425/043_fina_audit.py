"""
接口：fina_audit，可以通过数据工具调试和查看数据
描述：获取上市公司定期财务审计意见数据
限量：不限制
权限：用户需要至少2000积分才可以调取
接口文档: https://tushare.pro/document/2?doc_id=80
本地文档: docs/tushare/tushare.pro/document/22145.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          start_date(str,N,公告开始日期), end_date(str,N,公告结束日期),
          period(str,N,报告期)
输出字段：ts_code,ann_date,end_date,audit_result,audit_fees,audit_agency,audit_sign

同步策略：低频慢表。默认交易日跳过，非交易日按股票循环刷新近期公告窗口
表名：043_fina_audit
迁移说明：tushare schema 中无此表，无需迁移
用法: python 043_fina_audit.py [--start YYYYMMDD] [--end YYYYMMDD] [--force] [--include-inactive]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "043_fina_audit"
DEFAULT_START = "20100101"
FIELDS = "ts_code,ann_date,end_date,audit_result,audit_fees,audit_agency,audit_sign"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "ann_date", "end_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code       VARCHAR(15) NOT NULL,
    ann_date      DATE        NOT NULL,
    end_date      DATE        NOT NULL,
    audit_result  VARCHAR(50),
    audit_fees    FLOAT,
    audit_agency  VARCHAR(100),
    audit_sign    VARCHAR(100),
    update_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, ann_date, end_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

DATE_COLS  = ["ann_date", "end_date"]
FLOAT_COLS = ["audit_fees"]


def is_report_season(value: str) -> bool:
    dt = pd.Timestamp(value)
    mmdd = dt.month * 100 + dt.day
    return 301 <= mmdd <= 430 or 701 <= mmdd <= 831 or 1001 <= mmdd <= 1031


def auto_start(end: str) -> str:
    days = 120 if is_report_season(end) else 60
    return (pd.Timestamp(end) - pd.Timedelta(days=days)).strftime("%Y%m%d")


def is_open_trade_date(engine, target_date: str) -> bool:
    try:
        with engine.connect() as conn:
            row = conn.execute(text(f"""
                SELECT is_open
                FROM {SCHEMA}."003_trade_cal"
                WHERE exchange='SSE' AND cal_date=:d
            """), {"d": target_date}).fetchone()
        if row is not None:
            return bool(row[0] == 1)
    except Exception as e:
        print(f"[WARN] 查询 003_trade_cal 失败，使用 weekday 兜底: {e}")
    return pd.Timestamp(target_date).weekday() < 5


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--force", action="store_true", help="交易日也强制执行")
    parser.add_argument("--full", action="store_true", help="从 DEFAULT_START 开始刷新")
    parser.add_argument("--include-inactive", action="store_true", help="同时刷新 D/P 股票")
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    if is_open_trade_date(engine, args.end) and not args.force:
        print(f"[跳过] {args.end} 是交易日，{TABLE} 为低频慢表，仅非交易日自动刷新。需要强制执行请加 --force")
        return

    if args.start:
        start = args.start
    elif args.full:
        start = DEFAULT_START
    else:
        start = auto_start(args.end)
    print(f"[窗口] {TABLE} {start} ~ {args.end}")

    codes = []
    statuses = ["L", "D", "P"] if args.include_inactive else ["L"]
    for status in statuses:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")
    print(f"[股票池] list_status={','.join(statuses)} 共 {len(codes)} 只")

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.fina_audit(ts_code=code, start_date=start, end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                for col in DATE_COLS:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.dropna(subset=PK).drop_duplicates(subset=PK)
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

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
