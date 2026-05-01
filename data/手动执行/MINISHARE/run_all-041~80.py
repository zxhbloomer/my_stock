"""
run_all-041~80.py — 执行编号 041~080 的同步脚本
包含：财务数据后半段、特色数据、两融转融通、资金流向
用法: python run_all-041~80.py
      python run_all-041~80.py --only 041 042
      python run_all-041~80.py --skip 063
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = [
    # ── 财务数据后半段（按股票循环，耗时长）─────────────────
    "041_dividend.py",
    "042_fina_indicator.py",
    "043_fina_audit.py",

    # ── 特色数据 ──────────────────────────────────────────────
    "061_cyq_perf.py",
    "062_cyq_chips.py",
    "063_stk_factor_pro.py",  # 200+字段，按日期循环，耗时长
    "066_hk_hold.py",
    "069_stk_nineturn.py",

    # ── 两融及转融通 ──────────────────────────────────────────
    "073_margin.py",
    "074_margin_detail.py",
    "075_margin_secs.py",
    "076_slb_sec.py",
    "077_slb_len.py",
    "078_slb_sec_detail.py",

    # ── 资金流向 ──────────────────────────────────────────────
    "080_moneyflow.py",
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
    parser.add_argument("--only", nargs="+", help="只执行指定编号，如 041 042")
    parser.add_argument("--skip", nargs="+", help="跳过指定编号，如 063")
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
