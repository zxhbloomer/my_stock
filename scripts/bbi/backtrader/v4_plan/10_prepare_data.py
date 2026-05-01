# v4_plan/10_prepare_data.py
# 准备轮动策略所需的 parquet 数据
# 与 v3 相同的数据准备逻辑，输出到 output/stock_data/
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

    from sqlalchemy.pool import NullPool
    engine = create_engine(DB_URL, poolclass=NullPool)

    # Step 1: 基础过滤 — 排除退市、ST、北交所
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

    # Step 2: 流动性过滤（最近20日均值）
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

    # Step 3: 批量加载 moneyflow 和 cyq_perf
    print("Loading moneyflow data...")
    sql_mf = text("""
        SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol
        FROM tushare_v2."080_moneyflow"
        WHERE trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
    """)
    with engine.connect() as conn:
        df_mf = _query(conn, sql_mf, {"start_date": START_DATE, "end_date": end_date})
    df_mf['trade_date'] = pd.to_datetime(df_mf['trade_date'])
    df_mf['lg_net_vol'] = df_mf['buy_lg_vol'] - df_mf['sell_lg_vol']
    df_mf = df_mf[['ts_code', 'trade_date', 'lg_net_vol']]
    mf_dict = {code: grp.drop(columns='ts_code') for code, grp in df_mf.groupby('ts_code')}
    del df_mf

    print("Loading cyq_perf data...")
    sql_cyq = text("""
        SELECT ts_code, trade_date, winner_rate
        FROM tushare_v2."061_cyq_perf"
        WHERE trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
    """)
    with engine.connect() as conn:
        df_cyq = _query(conn, sql_cyq, {"start_date": START_DATE, "end_date": end_date})
    df_cyq['trade_date'] = pd.to_datetime(df_cyq['trade_date'])
    cyq_dict = {code: grp.drop(columns='ts_code') for code, grp in df_cyq.groupby('ts_code')}
    del df_cyq

    # Step 4: 逐股获取 OHLCV + BBI，合并 moneyflow + cyq_perf
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
                    print(f"  SKIP {ts_code} after 3 attempts: {e}")
                    df = pd.DataFrame()
                    break
        if df.empty or len(df) < max(BBI_PERIODS) + 10:
            skipped += 1
            continue

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
        if ts_code in mf_dict:
            df = df.merge(mf_dict[ts_code], on='trade_date', how='left')
        else:
            df['lg_net_vol'] = float('nan')
        if ts_code in cyq_dict:
            df = df.merge(cyq_dict[ts_code], on='trade_date', how='left')
        else:
            df['winner_rate'] = float('nan')

        # 盘后数据 T-1 shift，防止未来数据泄露
        df['lg_net_vol']  = df['lg_net_vol'].shift(1)
        df['winner_rate'] = df['winner_rate'].shift(1)

        df["name"] = row["name"]
        df.to_parquet(STOCK_DATA_DIR / f"{ts_code}.parquet", index=False)
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(df_stocks)} done...")

    exported = len(df_stocks) - skipped
    print(f"Done. Exported {exported} parquet files ({skipped} skipped).")

    df_stocks.to_csv(OUTPUT_DIR / "stock_list.csv", index=False)
    print(f"stock_list.csv saved ({len(df_stocks)} rows)")


if __name__ == "__main__":
    main()
