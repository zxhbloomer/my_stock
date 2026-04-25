from sqlalchemy import create_engine, text

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
engine = create_engine(DB_URL)

with engine.connect() as conn:
    r = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'tushare_v2'
          AND table_name ILIKE '%money%'
        ORDER BY table_name
    """))
    print("moneyflow 相关表：")
    for row in r.fetchall():
        print(f"  {row[0]}")

    r2 = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'tushare_v2'
          AND table_name ILIKE '%cyq%'
        ORDER BY table_name
    """))
    print("cyq 相关表：")
    for row in r2.fetchall():
        print(f"  {row[0]}")
