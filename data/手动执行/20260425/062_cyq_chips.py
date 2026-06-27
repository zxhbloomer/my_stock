"""
接口：cyq_chips，可以通过数据工具调试和查看数据
描述：获取A股每日的筹码分布情况，提供各价位占比，数据从2018年开始，每天18~19点之间更新当日数据
来源：Tushare社区
限量：官方 Web 当前为单次最大6000条，本地旧文档为2000条，可以按股票代码和日期循环提取
积分：5000积分每天20000次，10000积分每天200000次，15000积分每天不限总量
接口文档: https://tushare.pro/document/2?doc_id=294
本地文档: docs/tushare/tushare.pro/document/2cecc.html

输入参数：ts_code(str,Y,股票代码), trade_date(str,N,交易日期),
          start_date(str,N,开始日期), end_date(str,N,结束日期)
输出字段：ts_code,trade_date,price,percent

同步策略：按股票+交易日窗口+分页增量（ts_code+trade_date+price 为主键，upsert）
          注意：每只股票每天有多行（每个价位一行），真实验证常见每天约百行。
          例如 600000.SH 在 2022-01-01~2022-04-29 超过6000行，不分页会静默截断。
表名：062_cyq_chips
迁移说明：tushare.stock_chips 字段不同（缺少price/percent，有cost_*字段），无法直接迁移
用法: python 062_cyq_chips.py [--start YYYYMMDD] [--end YYYYMMDD] [--window-days 50] [--page-size 6000]
      [--start-code 300070.SZ] [--end-code 300999.SZ]
"""
import argparse, sys
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


def trade_date_windows(trade_dates: list[str], window_days: int):
    """按交易日数量切分窗口，返回 [(seg_start, seg_end), ...]。"""
    if window_days <= 0:
        raise ValueError("--window-days 必须大于 0")
    return [
        (chunk[0], chunk[-1])
        for chunk in (trade_dates[i:i + window_days] for i in range(0, len(trade_dates), window_days))
        if chunk
    ]


def fetch_segment_pages(pro, code: str, seg_start: str, seg_end: str, page_size: int):
    if page_size <= 0:
        raise ValueError("--page-size 必须大于 0")
    frames = []
    offset = 0
    while True:
        df = pro.cyq_chips(
            ts_code=code,
            start_date=seg_start,
            end_date=seg_end,
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
        return pd.DataFrame(columns=COLS)
    df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["percent"] = pd.to_numeric(df["percent"], errors="coerce")
    return df.dropna(subset=PK).drop_duplicates(subset=PK)


def filter_codes(codes: list[str], start_code: str | None, end_code: str | None) -> list[str]:
    if start_code:
        codes = [code for code in codes if code >= start_code]
    if end_code:
        codes = [code for code in codes if code <= end_code]
    return codes


def upsert_with_reconnect(engine, df, max_attempts: int = 3):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            return upsert_df(engine, df, TABLE, COLS, PK)
        except Exception as exc:
            last_error = exc
            print(f"  [WARN] 数据库写入失败，尝试 {attempt}/{max_attempts}: {exc}", flush=True)
            try:
                engine.dispose()
            except Exception:
                pass
            if attempt == max_attempts:
                raise
    raise last_error


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None)
    parser.add_argument("--end",   default=TODAY)
    parser.add_argument("--window-days", type=int, default=50)
    parser.add_argument("--page-size", type=int, default=6000)
    parser.add_argument("--start-code", default=None, help="从指定股票代码开始续跑，例如 300070.SZ")
    parser.add_argument("--end-code", default=None, help="跑到指定股票代码结束")
    args = parser.parse_args()

    pro    = init_tushare()
    engine = get_engine()
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)

    start = args.start or get_start(engine)
    trade_dates = get_trade_dates(pro, start, args.end)
    segments = trade_date_windows(trade_dates, args.window_days)

    # 获取股票列表
    codes = []
    for status in ["L", "D", "P"]:
        s = pro.stock_basic(list_status=status, fields="ts_code")
        if s is not None and not s.empty and "ts_code" in s.columns:
            codes.extend(s["ts_code"].tolist())
    codes = sorted(set(codes))
    codes = filter_codes(codes, args.start_code, args.end_code)
    if not codes:
        raise RuntimeError("stock_basic 返回异常，未获取到任何股票代码")

    print(f"共 {len(codes)} 只股票，{len(segments)} 个交易日窗口")
    if args.start_code or args.end_code:
        print(f"[续跑] 股票范围 {args.start_code or '-'} ~ {args.end_code or '-'}")
    if not segments:
        print("\n[完成] 扫描区间内没有 SSE 交易日")
        return

    # sync_status 只能记录脚本级日期，不能表达“股票+窗口”的内部进度。
    # 因此开始时标记 start=ing；若中断，下次从 start 重跑，避免跳过未完成历史。
    mark_sync(engine, f"{TABLE}.py", TABLE, start, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
        code_rows = 0
        for seg_start, seg_end in segments:
            df = normalize_df(fetch_segment_pages(pro, code, seg_start, seg_end, args.page_size))
            if df is not None and not df.empty:
                rows = upsert_with_reconnect(engine, df)
                code_rows += rows
                total_rows += rows

        elapsed = (datetime.now() - t0).seconds
        if code_rows > 0 or i % 200 == 0:
            print(f"  [{i:4d}/{len(codes)}] {code}  {code_rows}条  {elapsed//60}分{elapsed%60}秒", flush=True)

    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")


if __name__ == "__main__":
    main()
