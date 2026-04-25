"""
接口：slb_sec_detail，可以通过数据工具调试和查看数据
描述：转融券交易明细（注：该接口已停止更新）
限量：单次最大可以提取5000行数据，可循环获取所有历史
权限：2000积分每分钟请求200次，5000积分500次请求
接口文档: https://tushare.pro/document/2?doc_id=333
本地文档: docs/tushare/tushare.pro/document/2e287.html

输入参数：trade_date(str,N,交易日期), ts_code(str,N,股票代码),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：trade_date,ts_code,name,tenor,fee_rate,lent_qnt

同步策略：按交易日增量（trade_date+ts_code+tenor 为主键，upsert）
          注意：该接口已停止更新，历史数据仍可获取
表名：078_slb_sec_detail
迁移说明：tushare schema 中无此表，无需迁移
用法: python 078_slb_sec_detail.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "078_slb_sec_detail"
DEFAULT_START = "20130201"
LOOKBACK_DAYS = 3

FIELDS = "trade_date,ts_code,name,tenor,fee_rate,lent_qnt"
COLS   = FIELDS.split(",")
PK     = ["trade_date", "ts_code", "tenor"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    trade_date  DATE        NOT NULL,
    ts_code     VARCHAR(15) NOT NULL,
    name        VARCHAR(50),
    tenor       VARCHAR(20) NOT NULL,
    fee_rate    FLOAT,
    lent_qnt    FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (trade_date, ts_code, tenor)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_ts ON {SCHEMA}."{TABLE}" (ts_code);
"""

FLOAT_COLS = ["fee_rate","lent_qnt"]


def get_start(engine):
    max_d = get_max_date(engine, TABLE)
    if max_d:
        start = (pd.Timestamp(max_d) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        print(f"[增量] {TABLE} 最新={max_d}，从 {start} 开始")
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
    cal = pro.trade_cal(exchange="SSE", start_date=start, end_date=args.end,
                        is_open="1", fields="cal_date")
    dates = sorted(cal["cal_date"].tolist())

    total_rows, t0 = 0, datetime.now()
    for i, d in enumerate(dates, 1):
        try:
            df = pro.slb_sec_detail(trade_date=d, fields=FIELDS)
            if df is not None and not df.empty:
                df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                for col in FLOAT_COLS:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                # tenor可能为None，需要填充默认值
                if "tenor" in df.columns:
                    df["tenor"] = df["tenor"].fillna("").astype(str)
                df = df.dropna(subset=["trade_date","ts_code"]).drop_duplicates(subset=PK)
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception as e:
            print(f"  [SKIP] {d}: {e}")
            rows = 0
        elapsed = (datetime.now() - t0).seconds
        if rows > 0 or i % 50 == 0:
            print(f"  [{i:4d}/{len(dates)}] {d}  {rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)
        time.sleep(0.3)

    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
