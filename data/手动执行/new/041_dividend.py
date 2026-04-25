"""
接口：dividend，可以通过数据工具调试和查看数据
描述：分红送股数据
限量：用户需要至少2000积分才可以调取
权限：2000积分以上可以调取
接口文档: https://tushare.pro/document/2?doc_id=103
本地文档: docs/tushare/tushare.pro/document/2668c.html

输入参数：ts_code(str,Y,股票代码), ann_date(str,N,公告日期),
          record_date(str,N,股权登记日), ex_date(str,N,除权除息日),
          imp_ann_date(str,N,实施公告日)
输出字段：ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,
          cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,
          imp_ann_date,base_date,base_share

同步策略：按股票循环增量（ts_code+end_date+ann_date 为主键，upsert）
表名：041_dividend
迁移说明：tushare.tushare_stock_dividend 有少量数据（385行），建议重新从API拉取
用法: python 041_dividend.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "041_dividend"
DEFAULT_START = "20100101"
LOOKBACK_DAYS = 90
FIELDS = "ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,imp_ann_date,base_date,base_share"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "end_date", "ann_date"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code       VARCHAR(15) NOT NULL,
    end_date      DATE        NOT NULL,
    ann_date      DATE        NOT NULL,
    div_proc      VARCHAR(20),
    stk_div       FLOAT,
    stk_bo_rate   FLOAT,
    stk_co_rate   FLOAT,
    cash_div      FLOAT,
    cash_div_tax  FLOAT,
    record_date   DATE,
    ex_date       DATE,
    pay_date      DATE,
    div_listdate  DATE,
    imp_ann_date  DATE,
    base_date     DATE,
    base_share    FLOAT,
    update_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, end_date, ann_date)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

DATE_COLS  = ["end_date","ann_date","record_date","ex_date","pay_date",
              "div_listdate","imp_ann_date","base_date"]
FLOAT_COLS = ["stk_div","stk_bo_rate","stk_co_rate","cash_div","cash_div_tax","base_share"]


def get_start(engine):
    max_d = get_max_date(engine, TABLE, date_col="ann_date")
    if max_d:
        start = (pd.Timestamp(max_d) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        print(f"[增量] {TABLE} 最新ann_date={max_d}，从 {start} 开始")
        return start
    return DEFAULT_START


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)

    codes = []
    for status in ["L", "D", "P"]:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")

    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        try:
            df = pro.dividend(ts_code=code, ann_date=None, start_date=start, end_date=args.end, fields=FIELDS)
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
        time.sleep(0.2)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
