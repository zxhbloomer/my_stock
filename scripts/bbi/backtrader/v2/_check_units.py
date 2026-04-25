import psycopg2
conn = psycopg2.connect('postgresql://root:123456@localhost:5432/my_stock')
cur = conn.cursor()

# 用最新一个交易日的数据，统计不同市值门槛下的股票数量
cur.execute("""
WITH latest AS (
    SELECT MAX(trade_date) as max_date FROM tushare_v2."027_daily_basic"
)
SELECT
    COUNT(*) FILTER (WHERE circ_mv >= 1000000)  as "100亿以上",
    COUNT(*) FILTER (WHERE circ_mv >= 500000)   as "50亿以上",
    COUNT(*) FILTER (WHERE circ_mv >= 200000)   as "20亿以上",
    COUNT(*) FILTER (WHERE circ_mv >= 100000)   as "10亿以上",
    COUNT(*)                                     as "全部"
FROM tushare_v2."027_daily_basic"
WHERE trade_date = (SELECT max_date FROM latest)
""")
row = cur.fetchone()
print(f"最新交易日股票数量统计：")
print(f"  流通市值 > 100亿：{row[0]} 只")
print(f"  流通市值 >  50亿：{row[1]} 只")
print(f"  流通市值 >  20亿：{row[2]} 只")
print(f"  流通市值 >  10亿：{row[3]} 只")
print(f"  全部：{row[4]} 只")
conn.close()
