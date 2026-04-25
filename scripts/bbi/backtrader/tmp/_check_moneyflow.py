import pandas as pd
from sqlalchemy import create_engine, text

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
engine = create_engine(DB_URL)

with engine.connect() as conn:
    # 检查 moneyflow 表结构和数据量
    r = conn.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'tushare_v2'
          AND table_name LIKE '%moneyflow%'
        ORDER BY table_name, ordinal_position
    """))
    rows = r.fetchall()
    print("=== moneyflow 相关表字段 ===")
    cur_table = None
    for row in rows:
        print(f"  {row[0]} ({row[1]})")

    # 检查数据覆盖
    r2 = conn.execute(text("""
        SELECT
            MIN(trade_date) as min_date,
            MAX(trade_date) as max_date,
            COUNT(DISTINCT ts_code) as stock_count,
            COUNT(*) as total_rows
        FROM tushare_v2."067_moneyflow"
    """))
    row = r2.fetchone()
    if row:
        print(f"\n=== moneyflow 数据覆盖 ===")
        print(f"  日期范围: {row[0]} ~ {row[1]}")
        print(f"  股票数量: {row[2]}")
        print(f"  总行数: {row[3]}")

    # 看一条样本
    r3 = conn.execute(text("""
        SELECT ts_code, trade_date, buy_lg_vol, sell_lg_vol, buy_elg_vol, sell_elg_vol, net_mf_amount
        FROM tushare_v2."067_moneyflow"
        WHERE ts_code = '000001.SZ'
        ORDER BY trade_date DESC
        LIMIT 5
    """))
    rows3 = r3.fetchall()
    print(f"\n=== 000001.SZ 最近5条 moneyflow ===")
    for r in rows3:
        print(f"  {r[1]}: buy_lg={r[2]}, sell_lg={r[3]}, buy_elg={r[4]}, sell_elg={r[5]}, net_mf={r[6]}")

    # 检查与 stk_factor_pro 的日期对齐情况
    r4 = conn.execute(text("""
        SELECT COUNT(*) as matched
        FROM tushare_v2."063_stk_factor_pro" f
        JOIN tushare_v2."067_moneyflow" m
          ON f.ts_code = m.ts_code AND f.trade_date = m.trade_date
        WHERE f.ts_code = '000001.SZ'
          AND f.trade_date >= '2018-01-01'
    """))
    print(f"\n=== 000001.SZ 日期对齐行数 (2018+): {r4.fetchone()[0]} ===")
