"""查询每个表最新2个日期的数据条数，用于验证数据完整性"""
from _check_status import SCRIPT_TABLE_MAP
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from _common import SCHEMA, get_engine
from sqlalchemy import text


def main():
    engine = get_engine()
    dated_tables = [(s, t, d) for s, t, d in SCRIPT_TABLE_MAP if d is not None]

    print(f"{'脚本':<32} {'表名':<26} {'日期1':<12} {'条数1':>10}  {'日期2':<12} {'条数2':>10}")
    print("-" * 110)

    with engine.connect() as conn:
        all_tables = {r[0] for r in conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema=:schema"
        ), {"schema": SCHEMA}).fetchall()}

        for script, table, date_col in dated_tables:
            if table not in all_tables:
                print(f"{script:<32} {table:<26} {'表不存在'}")
                continue

            dates = conn.execute(text(
                f'SELECT DISTINCT "{date_col}" FROM {SCHEMA}."{table}" '
                f'ORDER BY "{date_col}" DESC LIMIT 2'
            )).fetchall()
            if not dates:
                print(f"{script:<32} {table:<26} {'空表'}")
                continue

            results = []
            for (d,) in dates:
                cnt = conn.execute(text(
                    f'SELECT COUNT(*) FROM {SCHEMA}."{table}" WHERE "{date_col}"=:d'
                ), {"d": d}).fetchone()[0]
                results.append((str(d)[:10], cnt))

            while len(results) < 2:
                results.append(("-", "-"))

            d1, c1 = results[0]
            d2, c2 = results[1]
            c1 = f"{c1:,}" if isinstance(c1, int) else c1
            c2 = f"{c2:,}" if isinstance(c2, int) else c2
            print(f"{script:<32} {table:<26} {d1:<12} {c1:>10}  {d2:<12} {c2:>10}")


if __name__ == "__main__":
    main()

