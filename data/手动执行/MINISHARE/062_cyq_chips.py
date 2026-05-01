"""
接口：cyq_chips，可以通过数据工具调试和查看数据
描述：获取A股每日的筹码分布情况，提供各价位占比，数据从2018年开始，每天18~19点之间更新当日数据
来源：Tushare社区
限量：单次最大2000条，可以按股票代码和日期循环提取
积分：5000积分每天20000次，10000积分每天200000次，15000积分每天不限总量
接口文档: https://tushare.pro/document/2?doc_id=294
本地文档: docs/tushare/tushare.pro/document/2cecc.html

输入参数：ts_code(str,Y,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,price,percent

同步策略：按股票+按年分段循环增量（ts_code+trade_date+price 为主键，upsert）
          注意：每只股票每天有多行（每个价位一行），每天约4个价位档
          单次限2000条，按年分段确保不超限（250天×4档=1000条/年）
表名：062_cyq_chips
迁移说明：tushare.stock_chips 字段不同（缺少price/percent，有cost_*字段），无法直接迁移
用法: python 062_cyq_chips.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "062_cyq_chips"
DEFAULT_START = "20180101"  # 数据从2018年开始

FIELDS = "ts_code,trade_date,price,percent"
COLS   = FIELDS.split(",")
PK     = ["ts_code", "trade_date", "price"]

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    ts_code     VARCHAR(15) NOT NULL,
    trade_date  DATE        NOT NULL,
    price       FLOAT       NOT NULL,
    percent     FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date, price)
);
CREATE INDEX IF NOT EXISTS idx_{TABLE}_date ON {SCHEMA}."{TABLE}" (trade_date);
"""


def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start


def year_segments(start: str, end: str):
    """将日期范围按年切分，返回 [(seg_start, seg_end), ...]"""
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    segments = []
    cur = s
    while cur <= e:
        seg_end = min(pd.Timestamp(f"{cur.year}1231"), e)
        segments.append((cur.strftime("%Y%m%d"), seg_end.strftime("%Y%m%d")))
        cur = pd.Timestamp(f"{cur.year + 1}0101")
    return segments


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
    segments = year_segments(start, args.end)

    # 获取股票列表
    codes = get_stock_codes(pro)

    print(f"共 {len(codes)} 只股票，{len(segments)} 个年段")
    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        code_rows = 0
        for seg_start, seg_end in segments:
            try:
                df = pro.cyq_chips(ts_code=code, start_date=seg_start,
                                   end_date=seg_end, fields=FIELDS)
                if df is not None and not df.empty:
                    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
                    df["price"]   = pd.to_numeric(df["price"],   errors="coerce")
                    df["percent"] = pd.to_numeric(df["percent"], errors="coerce")
                    df = df.dropna(subset=PK).drop_duplicates(subset=PK)
                    rows = upsert_df(engine, df, TABLE, COLS, PK)
                    code_rows += rows
                    total_rows += rows
            except Exception as e:
                print(f"  [SKIP] {code} {seg_start}-{seg_end}: {e}")

        elapsed = (datetime.now() - t0).seconds
        if code_rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {code_rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
