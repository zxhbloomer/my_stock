"""
05_view_recommend.py
查看历史推荐结果

用法:
    python scripts/bbi/05_view_recommend.py              # 查看最新一天
    python scripts/bbi/05_view_recommend.py --date 2026-04-19
    python scripts/bbi/05_view_recommend.py --list       # 列出所有历史日期
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = ROOT / "data/手动执行/推荐结果"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    csvs = sorted(OUTPUT_DIR.glob("*.csv"))
    if not csvs:
        print("暂无推荐结果，请先运行 04_daily_recommend.py")
        return

    if args.list:
        print("历史推荐日期：")
        for f in csvs:
            df = pd.read_csv(f)
            print(f"  {f.stem}  ({len(df)}只)")
        return

    if args.date:
        target = OUTPUT_DIR / f"{args.date}.csv"
    else:
        target = csvs[-1]

    if not target.exists():
        print(f"找不到 {target}")
        return

    df = pd.read_csv(target)
    print(f"\n=== 推荐结果 {target.stem} ===")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
