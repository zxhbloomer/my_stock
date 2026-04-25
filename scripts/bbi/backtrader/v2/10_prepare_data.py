# scripts/bbi/backtrader/10_prepare_data.py
import shutil
import datetime
import pandas as pd
from sqlalchemy import create_engine, text
from config import (
    DB_URL, START_DATE, END_DATE,
    FILTER_MIN_CIRC_MV, FILTER_MIN_AMOUNT,
    STOCK_DATA_DIR, OUTPUT_DIR,
    BBI_PERIODS,
)


def _query(conn, sql, params):
    result = conn.execute(sql, params)
    return pd.DataFrame(result.fetchall(), columns=result.keys())


def main():
    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")

    if STOCK_DATA_DIR.exists():
        shutil.rmtree(STOCK_DATA_DIR)
    STOCK_DATA_DIR.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_engine(DB_URL)

    # Step 1: basic filter — 用当前状态筛选，排除退市、ST、北交所
    sql_basic = text("""
        SELECT ts_code, name, list_date
        FROM tushare_v2."001_stock_basic"
        WHERE list_status = 'L'
          AND ts_code NOT LIKE '8%'
          AND name NOT LIKE '%ST%'
          AND name NOT LIKE '%退%'
    """)
    with engine.connect() as conn:
        df_basic = _query(conn, sql_basic, {})
    print(f"Step 1: {len(df_basic)} stocks after basic filter")

    # Step 2: 用最新20个交易日的数据筛选流动性（当前市值+成交额）
    sql_liq = text("""
        SELECT ts_code
        FROM (
            SELECT ts_code, circ_mv, amount,
                   ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) AS rn
            FROM tushare_v2."063_stk_factor_pro"
        ) sub
        WHERE rn <= 20
        GROUP BY ts_code
        HAVING AVG(circ_mv) >= :min_circ_mv
           AND AVG(amount)  >= :min_amount
    """)
    with engine.connect() as conn:
        df_liq = _query(conn, sql_liq, {
            "min_circ_mv": FILTER_MIN_CIRC_MV,
            "min_amount": FILTER_MIN_AMOUNT,
        })
    liquid_codes = set(df_liq["ts_code"])
    df_stocks = df_basic[df_basic["ts_code"].isin(liquid_codes)].reset_index(drop=True)
    print(f"Step 2: {len(df_stocks)} stocks after liquidity filter")

    # Step 3: fetch OHLCV + BBI per stock
    sql_data = text("""
        SELECT trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol
        FROM tushare_v2."063_stk_factor_pro"
        WHERE ts_code = :ts_code
          AND trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
        ORDER BY trade_date
    """)

    skipped = 0
    with engine.connect() as conn:
        for i, row in df_stocks.iterrows():
            ts_code = row["ts_code"]
            df = _query(conn, sql_data, {
                "ts_code": ts_code,
                "start_date": START_DATE,
                "end_date": end_date,
            })
            if len(df) < max(BBI_PERIODS) + 10:
                skipped += 1
                continue
            # Calculate BBI(5,10,20,60) in Python; DB bbi_qfq uses different formula
            for p in BBI_PERIODS:
                df[f'ma{p}'] = df['close_qfq'].rolling(p).mean()
            ma_cols = [f'ma{p}' for p in BBI_PERIODS]
            df['bbi_qfq'] = df[ma_cols].mean(axis=1)
            # keep ma60 as separate column for MA60 filter in strategy
            df = df.drop(columns=[f'ma{p}' for p in BBI_PERIODS if p != 60])
            df = df.dropna(subset=['bbi_qfq'])
            if len(df) < 10:
                skipped += 1
                continue
            df["name"] = row["name"]
            # 注意：若后续加入 moneyflow/cyq_perf 等盘后数据，必须在此处 shift(1)
            # 原因：这些数据在 T 日收盘后才可得，只能用于 T+1 日决策，直接用 T 日数据属于未来数据泄露
            # 示例：df['net_mf_amount'] = df['net_mf_amount'].shift(1)
            df.to_parquet(STOCK_DATA_DIR / f"{ts_code}.parquet", index=False)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(df_stocks)} done...")

    exported = len(df_stocks) - skipped
    print(f"Done. Exported {exported} parquet files ({skipped} skipped, < 60 rows).")

    df_stocks.to_csv(OUTPUT_DIR / "stock_list.csv", index=False)
    print(f"stock_list.csv saved ({len(df_stocks)} rows)")


if __name__ == "__main__":
    main()
