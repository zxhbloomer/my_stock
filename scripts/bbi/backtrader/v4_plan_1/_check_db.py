from sqlalchemy import create_engine, text
engine = create_engine('postgresql://root:123456@localhost:5432/my_stock')
with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT COUNT(*) FROM tushare_v2."001_stock_basic"
        WHERE ts_code NOT LIKE '8%'
          AND name NOT LIKE '%ST%'
          AND name NOT LIKE '%退%'
          AND delist_date IS NULL
    """))
    print('After delist_date IS NULL filter:', r.scalar())
