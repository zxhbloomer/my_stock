from sqlalchemy import create_engine, text

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
engine = create_engine(DB_URL)

with engine.connect() as conn:
    # 只查日期范围，不做全表 COUNT
    for tbl, label in [("080_moneyflow", "moneyflow"), ("061_cyq_perf", "cyq_perf")]:
        r = conn.execute(text(f'SELECT MIN(trade_date), MAX(trade_date) FROM tushare_v2."{tbl}"'))
        row = r.fetchone()
        print(f"{label}: {row[0]} ~ {row[1]}")

    # 样本
    r3 = conn.execute(text("""
        SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, net_mf_amount
        FROM tushare_v2."080_moneyflow"
        WHERE ts_code = '000001.SZ'
        ORDER BY trade_date DESC LIMIT 3
    """))
    print("\n000001.SZ moneyflow:")
    for r in r3.fetchall():
        print(f"  {r[1]}: buy_lg={r[2]}, sell_lg={r[3]}, net_mf={r[4]}")

    r5 = conn.execute(text("""
        SELECT ts_code, trade_date, winner_rate, weight_avg
        FROM tushare_v2."061_cyq_perf"
        WHERE ts_code = '000001.SZ'
        ORDER BY trade_date DESC LIMIT 3
    """))
    print("\n000001.SZ cyq_perf:")
    for r in r5.fetchall():
        print(f"  {r[1]}: winner_rate={r[2]}, weight_avg={r[3]}")
