"""
run_all-81~139.py — 执行编号 081~139 的同步脚本
包含：资金流向续、指数专题
用法: python run_all-81~139.py
      python run_all-81~139.py --only 081 087
      python run_all-81~139.py --skip 137
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = [
    # ── 资金流向（续）────────────────────────────────────────
    "081_moneyflow_ths.py",
    "087_moneyflow_hsgt.py",

    # ── 指数专题 ──────────────────────────────────────────────
    "121_index_basic.py",
    "122_index_daily.py",
    "129_index_dailybasic.py",
    "134_ci_index_member.py",
    "135_ci_daily.py",
    "137_idx_factor_pro.py",  # 80+字段，按日期循环，耗时长
    "138_daily_info.py",
    "139_sz_daily_info.py",
]

HERE = Path(__file__).parent


def run_script(script: str) -> bool:
    print(f"\n{'='*60}")
    print(f"[RUN] {script}  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    result = subprocess.run(
        [sys.executable, str(HERE / script)],
        cwd=str(HERE),
    )
    if result.returncode != 0:
        print(f"[ERROR] {script} 退出码={result.returncode}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+", help="只执行指定编号，如 081 087")
    parser.add_argument("--skip", nargs="+", help="跳过指定编号，如 137")
    args = parser.parse_args()

    to_run = SCRIPTS
    if args.only:
        to_run = [s for s in SCRIPTS if any(s.startswith(n) for n in args.only)]
    if args.skip:
        to_run = [s for s in to_run if not any(s.startswith(n) for n in args.skip)]

    print(f"计划执行 {len(to_run)} 个脚本: {[s[:3] for s in to_run]}")
    t0 = datetime.now()
    failed = []

    for script in to_run:
        ok = run_script(script)
        if not ok:
            failed.append(script)
        time.sleep(1)

    elapsed = (datetime.now() - t0).seconds
    print(f"\n{'='*60}")
    print(f"[完成] 耗时 {elapsed//60}分{elapsed%60}秒")
    if failed:
        print(f"[失败] {failed}")
        sys.exit(1)
    else:
        print("[全部成功]")


if __name__ == "__main__":
    main()
