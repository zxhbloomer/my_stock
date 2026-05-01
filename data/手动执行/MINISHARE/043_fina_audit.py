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

同步策略：按股票循环增量（ts_code+ann_date+end_date 为主键，upsert）
表名：043_fina_audit
迁移说明：tushare schema 中无此表，无需迁移
用法: python 043_fina_audit.py [--start YYYYMMDD] [--end YYYYMMDD]
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


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start



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

    codes = get_stock_codes(pro)

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
        except Exception as e:
            print(f"  [SKIP] {code}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
