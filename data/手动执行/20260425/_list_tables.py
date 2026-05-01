"""列出 tushare_v2 下所有表及其数据情况"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _common import get_engine, SCHEMA
from sqlalchemy import text

engine = get_engine()

with engine.connect() as conn:
    # 获取所有表
    tables = [r[0] for r in conn.execute(text(
        f"SELECT table_name FROM information_schema.tables "
        f"WHERE table_schema='{SCHEMA}' ORDER BY table_name"
    )).fetchall()]

    print(f"{'表名':<30} {'行数':>12}")
    print("-" * 45)
    for t in tables:
        try:
            cnt = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{t}"')).fetchone()[0]
            print(f"{t:<30} {cnt:>12,}")
        except Exception as e:
            print(f"{t:<30} {'ERR':>12}")
