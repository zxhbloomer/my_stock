"""查询所有脚本对应表的最新数据日期"""
from _check_status import SCRIPT_TABLE_MAP
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SCHEMA, get_engine
from sqlalchemy import text


def main():
    engine = get_engine()
    print(f"{'脚本名称':<32} {'表名称':<26} {'最新数据':<12} {'数据条数':>12}")
    print("-" * 90)

    with engine.connect() as conn:
        all_tables = {r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"
        ), {"schema": SCHEMA}).fetchall()}

        for script, table, date_col in SCRIPT_TABLE_MAP:
            if table not in all_tables:
                print(f"{script:<32} {table:<26} {'表不存在':<12} {'-':>12}")
                continue
            cnt = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')).fetchone()[0]
            if date_col and cnt > 0:
                max_d = conn.execute(text(
                    f'SELECT MAX("{date_col}") FROM {SCHEMA}."{table}"'
                )).fetchone()[0]
                max_d = str(max_d)[:10] if max_d else "NULL"
            elif cnt == 0:
                max_d = "空表"
            else:
                max_d = "N/A"
            print(f"{script:<32} {table:<26} {max_d:<12} {cnt:>12,}")

        print(f"\nsync_status 表存在: {'sync_status' in all_tables}")


if __name__ == "__main__":
    main()

