# tmp/10_prepare_data_v5.py
# 在 v2 基础上加入 moneyflow（大单净流入）和 cyq_perf（筹码胜率）
# 数据时序规则：moneyflow/cyq_perf 是盘后数据，必须 shift(1)，避免未来数据泄露
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

V5_STOCK_DATA_DIR = OUTPUT_DIR / "stock_data_v5"


def _query(conn, sql, params):
    result = conn.execute(sql, params)
    return pd.DataFrame(result.fetchall(), columns=result.keys())


def main():
    end_date = END_DATE or datetime.date.today().strftime("%Y-%m-%d")

    if V5_STOCK_DATA_DIR.exists():
        shutil.rmtree(V5_STOCK_DATA_DIR)
    V5_STOCK_DATA_DIR.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_engine(DB_URL)

    # Step 1: basic filter
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

    # Step 2: liquidity filter
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

    # Step 3: 批量拉 moneyflow 和 cyq_perf 到内存，再在 Python 里 merge
    # 避免逐股 SQL JOIN 导致连接超时
    print("Loading moneyflow data into memory...")
    sql_mf = text("""
        SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, net_mf_amount
        FROM tushare_v2."080_moneyflow"
        WHERE trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
    """)
    print("Loading cyq_perf data into memory...")
    sql_cyq = text("""
        SELECT ts_code, trade_date, winner_rate, weight_avg
        FROM tushare_v2."061_cyq_perf"
        WHERE trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
    """)
    with engine.connect() as conn:
        df_mf  = _query(conn, sql_mf,  {"start_date": START_DATE, "end_date": end_date})
        df_cyq = _query(conn, sql_cyq, {"start_date": START_DATE, "end_date": end_date})
    df_mf['trade_date']  = pd.to_datetime(df_mf['trade_date'])
    df_cyq['trade_date'] = pd.to_datetime(df_cyq['trade_date'])
    print(f"  moneyflow: {len(df_mf)} rows, cyq_perf: {len(df_cyq)} rows")

    # Step 4: fetch OHLCV per stock, merge in Python
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

            df['trade_date'] = pd.to_datetime(df['trade_date'])

            # Python-side merge（避免 SQL JOIN 超时）
            mf_stock  = df_mf[df_mf['ts_code'] == ts_code][['trade_date','buy_lg_vol','sell_lg_vol','net_mf_amount']]
            cyq_stock = df_cyq[df_cyq['ts_code'] == ts_code][['trade_date','winner_rate','weight_avg']]
            df = df.merge(mf_stock,  on='trade_date', how='left')
            df = df.merge(cyq_stock, on='trade_date', how='left')

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

            # 盘后数据 shift(1)：T 日的 moneyflow/cyq_perf 在收盘后才可得
            # shift 后，策略在 T 日看到的是 T-1 日的数据，符合实际交易时序
            for col in ['buy_lg_vol', 'sell_lg_vol', 'net_mf_amount', 'winner_rate', 'weight_avg']:
                df[col] = df[col].shift(1)

            # 派生：大单净流入量（买入大单 - 卖出大单，已是 T-1 数据）
            df['lg_net_vol'] = df['buy_lg_vol'] - df['sell_lg_vol']

            df["name"] = row["name"]
            df.to_parquet(V5_STOCK_DATA_DIR / f"{ts_code}.parquet", index=False)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(df_stocks)} done...")

    exported = len(df_stocks) - skipped
    print(f"Done. Exported {exported} parquet files to {V5_STOCK_DATA_DIR}")
    print(f"  ({skipped} skipped)")


if __name__ == "__main__":
    main()
