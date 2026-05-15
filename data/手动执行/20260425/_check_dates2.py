"""查询每个表最新5个日期的数据条数"""
from _check_status import SCRIPT_TABLE_MAP
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SCHEMA, get_engine
from sqlalchemy import text


def main():
    engine = get_engine()

    with engine.connect() as conn:
        all_tables = {r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"
        ), {"schema": SCHEMA}).fetchall()}

        for script, table, date_col in SCRIPT_TABLE_MAP:
            print(f"\n{'=' * 60}")
            print(f"脚本: {script}  表: {table}")

            if table not in all_tables:
                print("  表不存在")
                continue

            total = conn.execute(text(f'SELECT COUNT(*) FROM {SCHEMA}."{table}"')).fetchone()[0]
            print(f"  总行数: {total:,}")

            if date_col is None:
                print("  无日期列（A类全量表）")
                continue

            if total == 0:
                print("  空表")
                continue

            dates = conn.execute(text(
                f'SELECT DISTINCT "{date_col}" FROM {SCHEMA}."{table}" '
                f'ORDER BY "{date_col}" DESC LIMIT 5'
            )).fetchall()

            print(f"  {'日期':<12} {'条数':>10}")
            print(f"  {'-' * 24}")
            for (d,) in dates:
                cnt = conn.execute(text(
                    f'SELECT COUNT(*) FROM {SCHEMA}."{table}" WHERE "{date_col}"=:d'
                ), {"d": d}).fetchone()[0]
                print(f"  {str(d)[:10]:<12} {cnt:>10,}")


if __name__ == "__main__":
    main()

