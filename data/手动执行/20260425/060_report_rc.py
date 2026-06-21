"""
接口：report_rc，可以通过数据工具调试和查看数据
描述：获取券商（卖方）每天研报的盈利预测数据，数据从2010年开始，每晚19~22点更新当日数据
限量：单次最大3000条，可分页和循环提取所有数据
权限：120积分可以试用，正式权限需8000积分
接口文档: https://tushare.pro/document/2?doc_id=292
本地文档: docs/tushare/tushare.pro/document/2aeb4.html

输入参数：ts_code(str,N,股票代码), report_date(str,N,报告日期),
          start_date(str,N,报告开始日期), end_date(str,N,报告结束日期)
输出字段：ts_code,name,report_date,report_title,report_type,classify,org_name,
          author_name,quarter,op_rt,op_pr,tp,np,eps,pe,rd,roe,ev_ebitda,
          rating,max_price,min_price,imp_dg,create_time

同步策略：按报告日分页增量；表使用数据库自增主键，按 report_date 整日删除后重插
表名：060_report_rc
迁移说明：tushare schema 中无此表，无需迁移
用法: python 060_report_rc.py [--start YYYYMMDD] [--end YYYYMMDD] [--page-size 3000]
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "060_report_rc"
DEFAULT_START = "20100101"
FIELDS = "ts_code,name,report_date,report_title,report_type,classify,org_name,author_name,quarter,op_rt,op_pr,tp,np,eps,pe,rd,roe,ev_ebitda,rating,max_price,min_price,imp_dg,create_time"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "report_date", "report_title", "org_name", "author_name", "quarter"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    id            BIGSERIAL PRIMARY KEY,
    ts_code       VARCHAR(15) NOT NULL,
    name          VARCHAR(50),
    report_date   DATE        NOT NULL,
    report_title  TEXT,
    report_type   VARCHAR(50),
    classify      VARCHAR(50),
    org_name      VARCHAR(100),
    author_name   VARCHAR(100),
    quarter       VARCHAR(20),
    op_rt         FLOAT,
    op_pr         FLOAT,
    tp            FLOAT,
    np            FLOAT,
    eps           FLOAT,
    pe            FLOAT,
    rd            FLOAT,
    roe           FLOAT,
    ev_ebitda     FLOAT,
    rating        VARCHAR(50),
    max_price     FLOAT,
    min_price     FLOAT,
    imp_dg        VARCHAR(50),
    create_time   TIMESTAMP,
    update_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date_ts ON {SCHEMA}."{TABLE}" (report_date, ts_code);
"""

FLOAT_COLS = ["op_rt", "op_pr", "tp", "np", "eps", "pe", "rd", "roe", "ev_ebitda",
              "max_price", "min_price"]


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def effective_end_date(end: str, explicit_end: bool) -> str:
    if explicit_end or end != TODAY:
        return end
    if datetime.now().hour < 19:
        adjusted = (pd.Timestamp(end) - pd.Timedelta(days=1)).strftime("%Y%m%d")
        print(f"[更新窗口] report_rc 每晚19~22点更新，当前未到19点，end 从 {end} 调整为 {adjusted}")
        return adjusted
    return end


def fetch_report_date_pages(pro, report_date, page_size):
    frames = []
    offset = 0
    while True:
        df = pro.report_rc(
            report_date=report_date,
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
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce")
    if "create_time" in df.columns:
        df["create_time"] = pd.to_datetime(df["create_time"], errors="coerce")
    for col in FLOAT_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["ts_code", "report_date"])


def replace_report_date_df(engine, df, report_date):
    if isinstance(report_date, str):
        report_date = pd.Timestamp(report_date)
    date_value = report_date.date() if hasattr(report_date, "date") else report_date

    tmp = f"_tmp_{TABLE}"
    with engine.begin() as conn:
        conn.execute(text(f'DELETE FROM {SCHEMA}."{TABLE}" WHERE "report_date" = :d'), {"d": date_value})
        if df is None or df.empty:
            return 0
        df[COLS].to_sql(tmp, conn, schema=SCHEMA, if_exists="replace",
                        index=False, method="multi", chunksize=5000)
        conn.execute(text(f"""
            INSERT INTO {SCHEMA}."{TABLE}" ({','.join('"' + c + '"' for c in COLS)})
            SELECT {','.join('"' + c + '"' for c in COLS)} FROM {SCHEMA}."{tmp}"
        """))
        conn.execute(text(f'DROP TABLE IF EXISTS {SCHEMA}."{tmp}"'))
    return len(df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--page-size", type=int, default=3000)
    args = parser.parse_args()
    explicit_end = "--end" in sys.argv

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS, allow_extra_cols={"id"})

    start = args.start or get_start(engine)
    end = effective_end_date(args.end, explicit_end)
    if pd.Timestamp(start) > pd.Timestamp(end):
        print(f"[跳过] {TABLE} start={start} > end={end}")
        return
    dates = pd.date_range(pd.to_datetime(start), pd.to_datetime(end), freq="D").strftime("%Y%m%d").tolist()

    total_rows, t0 = 0, datetime.now()
    for i, report_date in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, report_date, "ing")
        try:
            df = fetch_report_date_pages(pro, report_date, args.page_size)
            if df is not None and not df.empty:
                df = normalize_df(df)
            rows = replace_report_date_df(engine, df, report_date)
            total_rows += rows
            mark_sync(engine, f"{TABLE}.py", TABLE, report_date, "ok")
        except Exception:
            raise
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {report_date}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    print(f"\n[完成] replace {total_rows:,} 条")


if __name__ == "__main__":
    main()
