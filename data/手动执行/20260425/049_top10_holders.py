"""
接口：top10_holders，可以通过数据工具调试和查看数据
描述：获取上市公司前十大股东数据，包括持有数量和比例等信息
权限：需2000积分以上才可以调取，5000积分以上频次会更高
接口文档: https://tushare.pro/document/2?doc_id=61
本地文档: docs/tushare/tushare.pro/document/229d8.html

输入参数：ts_code(str,Y,TS代码), period(str,N,报告期),
          ann_date(str,N,公告日期), start_date(str,N,公告开始日期),
          end_date(str,N,报告期结束日期)
输出字段：ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio,
          hold_float_ratio,hold_change,holder_type

同步策略：按报告期分页刷新全市场（ts_code+ann_date+end_date+holder_name 为主键，upsert）
表名：049_top10_holders
迁移说明：tushare schema 中无此表，无需迁移
用法: python 049_top10_holders.py [--start YYYYMMDD] [--end YYYYMMDD] [--quarters N] [--page-size 6000]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "049_top10_holders"
DEFAULT_START = "20100101"
FIELDS = "ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio,hold_float_ratio,hold_change,holder_type"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "ann_date", "end_date", "holder_name"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code          VARCHAR(15)  NOT NULL,
    ann_date         DATE         NOT NULL,
    end_date         DATE         NOT NULL,
    holder_name      TEXT         NOT NULL,
    hold_amount      FLOAT,
    hold_ratio       FLOAT,
    hold_float_ratio FLOAT,
    hold_change      FLOAT,
    holder_type      VARCHAR(50),
    update_time      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, ann_date, end_date, holder_name)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ann_date ON {SCHEMA}."{TABLE}" (ann_date);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

DATE_COLS  = ["ann_date", "end_date"]
FLOAT_COLS = ["hold_amount", "hold_ratio", "hold_float_ratio", "hold_change"]


def recent_report_period_window(end_date: str, quarters: int = 6) -> tuple[str, str]:
    current = datetime.strptime(str(end_date), "%Y%m%d")
    quarter_month = ((current.month - 1) // 3) * 3 + 3
    quarter_end = datetime(current.year, quarter_month, 1)
    if quarter_month == 3:
        quarter_end = datetime(current.year, 3, 31)
    elif quarter_month == 6:
        quarter_end = datetime(current.year, 6, 30)
    elif quarter_month == 9:
        quarter_end = datetime(current.year, 9, 30)
    else:
        quarter_end = datetime(current.year, 12, 31)

    if current < quarter_end:
        if quarter_month == 3:
            quarter_end = datetime(current.year - 1, 12, 31)
        elif quarter_month == 6:
            quarter_end = datetime(current.year, 3, 31)
        elif quarter_month == 9:
            quarter_end = datetime(current.year, 6, 30)
        else:
            quarter_end = datetime(current.year, 9, 30)

    periods = []
    year = quarter_end.year
    month = quarter_end.month
    for _ in range(max(1, quarters)):
        day = 31 if month in {3, 12} else 30
        periods.append(datetime(year, month, day))
        month -= 3
        if month <= 0:
            month += 12
            year -= 1

    return periods[-1].strftime("%Y%m%d"), periods[0].strftime("%Y%m%d")


def get_period_window(args):
    if args.start or args.end != TODAY:
        start = args.start or DEFAULT_START
        end = args.end
        print(f"[报告期] {TABLE} 手动范围 {start} ~ {end}")
        return start, end

    start, end = recent_report_period_window(args.end, args.quarters)
    print(f"[报告期] {TABLE} 滚动刷新最近 {args.quarters} 个报告期 {start} ~ {end}")
    return start, end


def report_periods(start: str, end: str) -> list[str]:
    periods = []
    cur = pd.Timestamp(start)
    last = pd.Timestamp(end)
    for year in range(cur.year, last.year + 1):
        for value in (f"{year}0331", f"{year}0630", f"{year}0930", f"{year}1231"):
            if start <= value <= end:
                periods.append(value)
    return periods


def fetch_period_pages(pro, period: str, page_size: int) -> pd.DataFrame:
    frames = []
    offset = 0
    while True:
        df = pro.top10_holders(
            period=period,
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
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--quarters", type=int, default=6, help="默认滚动刷新的最近报告期数量")
    parser.add_argument("--page-size", type=int, default=6000)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start, end = get_period_window(args)
    periods = report_periods(start, end)
    if not periods:
        print(f"[WARN] {TABLE} 范围内无报告期: {start} ~ {end}")
        return

    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, period in enumerate(periods, 1):
        try:
            df = fetch_period_pages(pro, period, args.page_size)
            if df is not None and not df.empty:
                df = normalize_df(df)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        print(f"  [{i:3d}/{len(periods)}] period={period}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    if total_rows == 0:
        with engine.connect() as conn:
            existing_rows = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{TABLE}"')).fetchone()[0]
        if existing_rows == 0:
            raise RuntimeError(f"{TABLE} 空表且本次未获取到数据，未标记同步成功")
        print(f"[WARN] {TABLE} 本次未获取到新数据，保留历史数据并标记运行日期")

    mark_sync(engine, f"{TABLE}.py", TABLE, TODAY, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
