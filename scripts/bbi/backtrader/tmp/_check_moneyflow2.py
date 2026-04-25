from sqlalchemy import create_engine, text

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
engine = create_engine(DB_URL)

with engine.connect() as conn:
    # moneyflow 覆盖
    r = conn.execute(text("""
        SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT ts_code), COUNT(*)
        FROM tushare_v2."080_moneyflow"
    """))
    row = r.fetchone()
    print(f"moneyflow: {row[0]} ~ {row[1]}, {row[2]} stocks, {row[3]} rows")

    # cyq_perf 覆盖
    r2 = conn.execute(text("""
        SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT ts_code), COUNT(*)
        FROM tushare_v2."061_cyq_perf"
    """))
    row2 = r2.fetchone()
    print(f"cyq_perf:  {row2[0]} ~ {row2[1]}, {row2[2]} stocks, {row2[3]} rows")

    # 样本：000001.SZ 最近5条 moneyflow
    r3 = conn.execute(text("""
        SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol, net_mf_amount
        FROM tushare_v2."080_moneyflow"
        WHERE ts_code = '000001.SZ'
        ORDER BY trade_date DESC LIMIT 5
    """))
    print("\n000001.SZ moneyflow 最近5条:")
    for r in r3.fetchall():
        net = (r[2] or 0) - (r[3] or 0)
        print(f"  {r[1]}: buy_lg={r[2]}, sell_lg={r[3]}, net_lg={net}, net_mf={r[6]:.0f}")

    # 与 stk_factor_pro 对齐检查
    r4 = conn.execute(text("""
        SELECT COUNT(*) FROM tushare_v2."063_stk_factor_pro" f
        JOIN tushare_v2."080_moneyflow" m
          ON f.ts_code = m.ts_code AND f.trade_date = m.trade_date
        WHERE f.ts_code = '000001.SZ' AND f.trade_date >= '2018-01-01'
    """))
    print(f"\n000001.SZ 日期对齐行数(2018+): {r4.fetchone()[0]}")

    # cyq_perf 样本
    r5 = conn.execute(text("""
        SELECT ts_code, trade_date, winner_rate, weight_avg
        FROM tushare_v2."061_cyq_perf"
        WHERE ts_code = '000001.SZ'
        ORDER BY trade_date DESC LIMIT 3
    """))
    print("\n000001.SZ cyq_perf 最近3条:")
    for r in r5.fetchall():
        print(f"  {r[1]}: winner_rate={r[2]}, weight_avg={r[3]}")
