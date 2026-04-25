"""
接口：trade_cal，可以通过数据工具调试和查看数据。
描述：获取各大交易所交易日历数据，默认提取的是上交所
限量：需2000积分
权限：2000积分
接口文档: https://tushare.pro/document/2?doc_id=26
本地文档: docs/tushare/tushare.pro/document/22614.html

同步策略：全删全插（交易日历为静态参考数据，按年份全量拉取）
表名：003_trade_cal
迁移说明：tushare schema 中无 trade_cal 表（存在 others_calendar），字段不同，无需迁移
用法: python 003_trade_cal.py [--start YYYYMMDD] [--end YYYYMMDD]
"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import *

TABLE         = "003_trade_cal"
DEFAULT_START = "20100729"
DEFAULT_END   = "20301231"
FIELDS = "exchange,cal_date,is_open,pretrade_date"
COLS   = FIELDS.split(",")

CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}."{TABLE}" (
    exchange      VARCHAR(10) NOT NULL,
    cal_date      DATE        NOT NULL,
    is_open       SMALLINT,
    pretrade_date DATE,
    update_time   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (exchange, cal_date)
);
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end",   default=DEFAULT_END)
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    all_dfs = []
    for exchange in ["SSE", "SZSE", "BSE"]:
        try:
            df = pro.trade_cal(exchange=exchange, start_date=args.start,
                               end_date=args.end, fields=FIELDS)
            if df is not None and not df.empty:
                all_dfs.append(df)
        except Exception as e:
            print(f"  [SKIP] {exchange}: {e}")
        time.sleep(0.3)

    if not all_dfs:
        print("[WARN] 返回空数据")
        return

    result = pd.concat(all_dfs, ignore_index=True)
    result["cal_date"]      = pd.to_datetime(result["cal_date"],      errors="coerce")
    result["pretrade_date"] = pd.to_datetime(result["pretrade_date"], errors="coerce")
    result["is_open"]       = pd.to_numeric(result["is_open"],        errors="coerce")

    rows = truncate_and_insert(engine, result, TABLE, COLS)
    print(f"[完成] {rows:,} 条")


if __name__ == "__main__":
    main()
