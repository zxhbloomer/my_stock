# tmp/10_prepare_data_fast.py
# 快速版：只取流动性最好的100只股票，用于 v5e vs v5f 快速对比
# 数据时序规则：winner_rate shift(1) 防未来数据泄露
import shutil
import datetime
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool
from pathlib import Path
import sys
import importlib.util
_v3_config_path = Path(__file__).parent.parent / 'v3' / 'config.py'
_spec = importlib.util.spec_from_file_location('v3_config', _v3_config_path)
_v3_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v3_cfg)
DB_URL             = _v3_cfg.DB_URL
START_DATE         = _v3_cfg.START_DATE
END_DATE           = _v3_cfg.END_DATE
FILTER_MIN_CIRC_MV = _v3_cfg.FILTER_MIN_CIRC_MV
FILTER_MIN_AMOUNT  = _v3_cfg.FILTER_MIN_AMOUNT
BBI_PERIODS        = _v3_cfg.BBI_PERIODS

FAST_STOCK_DATA_DIR = Path(__file__).parent / "output" / "stock_data_fast"
OUTPUT_DIR          = Path(__file__).parent / "output"
TOP_N               = 200   # 取流动性最好的200只


def _query(conn, sql, params):
    result = conn.execute(sql, params)
    return pd.DataFrame(result.fetchall(), columns=result.keys())


def main():
    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")

    if FAST_STOCK_DATA_DIR.exists():
        shutil.rmtree(FAST_STOCK_DATA_DIR)
    FAST_STOCK_DATA_DIR.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_engine(DB_URL, poolclass=NullPool)

    # Step 1: basic filter
    sql_basic = text("""
        SELECT ts_code, name, list_date
        FROM tushare_v2."001_stock_basic"
        WHERE ts_code NOT LIKE '8%'
          AND name NOT LIKE '%ST%'
          AND name NOT LIKE '%退%'
          AND name NOT LIKE '%PT%'
    """)
    with engine.connect() as conn:
        df_basic = _query(conn, sql_basic, {})
    print(f"Step 1: {len(df_basic)} stocks after basic filter")

    # Step 2: 取流动性最好的 TOP_N 只
    sql_liq = text("""
        SELECT ts_code, AVG(circ_mv) as avg_circ_mv, AVG(amount) as avg_amount
        FROM (
            SELECT ts_code, circ_mv, amount,
                   ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
            FROM tushare_v2."063_stk_factor_pro"
        ) sub
        WHERE rn <= 20
        GROUP BY ts_code
        HAVING AVG(circ_mv) >= :min_circ_mv
           AND AVG(amount)  >= :min_amount
        ORDER BY AVG(amount) DESC
        LIMIT :top_n
    """)
    with engine.connect() as conn:
        df_liq = _query(conn, sql_liq, {
            "min_circ_mv": FILTER_MIN_CIRC_MV,
            "min_amount": FILTER_MIN_AMOUNT,
            "top_n": TOP_N,
        })
    liquid_codes = set(df_liq["ts_code"])
    df_stocks = df_basic[df_basic["ts_code"].isin(liquid_codes)].reset_index(drop=True)
    print(f"Step 2: {len(df_stocks)} stocks (top {TOP_N} by liquidity)")

    # Step 3: batch-load cyq_perf
    print("Loading cyq_perf data...")
    sql_cyq = text("""
        SELECT ts_code, trade_date, winner_rate
        FROM tushare_v2."061_cyq_perf"
        WHERE trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
          AND ts_code = ANY(:codes)
    """)
    codes_list = list(df_stocks["ts_code"])
    with engine.connect() as conn:
        df_cyq = _query(conn, sql_cyq, {
            "start_date": START_DATE,
            "end_date": end_date,
            "codes": codes_list,
        })
    df_cyq['trade_date'] = pd.to_datetime(df_cyq['trade_date'])
    cyq_dict = {code: grp.drop(columns='ts_code') for code, grp in df_cyq.groupby('ts_code')}
    del df_cyq
    print(f"  cyq_perf loaded for {len(cyq_dict)} stocks")

    # Step 4: fetch OHLCV per stock
    sql_data = text("""
        SELECT trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol
        FROM tushare_v2."063_stk_factor_pro"
        WHERE ts_code = :ts_code
          AND trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
        ORDER BY trade_date
    """)

    skipped = 0
    for i, row in df_stocks.iterrows():
        ts_code = row["ts_code"]
        for attempt in range(3):
            try:
                with engine.connect() as conn:
                    df = _query(conn, sql_data, {
                        "ts_code": ts_code,
                        "start_date": START_DATE,
                        "end_date": end_date,
                    })
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  SKIP {ts_code}: {e}")
                    df = pd.DataFrame()
                    break

        if df.empty or len(df) < max(BBI_PERIODS) + 10:
            skipped += 1
            continue

        # BBI(5,10,20,60)
        for p in BBI_PERIODS:
            df[f'ma{p}'] = df['close_qfq'].rolling(p).mean()
        ma_cols = [f'ma{p}' for p in BBI_PERIODS]
        df['bbi_qfq'] = df[ma_cols].mean(axis=1)
        df = df.drop(columns=[f'ma{p}' for p in BBI_PERIODS if p != 60])
        df = df.dropna(subset=['bbi_qfq'])
        if len(df) < 10:
            skipped += 1
            continue

        df['trade_date'] = pd.to_datetime(df['trade_date'])
        if ts_code in cyq_dict:
            df = df.merge(cyq_dict[ts_code], on='trade_date', how='left')
        else:
            df['winner_rate'] = float('nan')

        # T-1 shift: 防未来数据泄露
        df['winner_rate'] = df['winner_rate'].shift(1)

        df["name"] = row["name"]
        df.to_parquet(FAST_STOCK_DATA_DIR / f"{ts_code}.parquet", index=False)

        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(df_stocks)} done...")

    exported = len(df_stocks) - skipped
    print(f"Done. Exported {exported} parquet files ({skipped} skipped).")


if __name__ == "__main__":
    main()
