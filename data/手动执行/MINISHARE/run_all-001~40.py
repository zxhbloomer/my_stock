"""
run_all-001~40.py — 执行编号 001~040 的同步脚本
包含：基础数据、行情数据、财务数据前半段
用法: python run_all-001~40.py
      python run_all-001~40.py --only 001 003
      python run_all-001~40.py --skip 036 037
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = [
    # ── 基础数据（003_trade_cal 必须第一个，B类脚本依赖它确定交易日）──
    "003_trade_cal.py",
    "001_stock_basic.py",
    # "002_stk_premarket.py",  # PASS: 自定义HTTP服务不支持此接口
    "004_stock_st.py",
    "005_st.py",
    # "006_stock_hsgt.py",  # PASS: 自定义HTTP服务不支持此接口
    # "007_namechange.py",  # PASS: 不需要此接口
    "008_stock_company.py",
    # "009_stk_managers.py",  # PASS: 不需要此接口
    # "010_stk_rewards.py",   # PASS: 不需要此接口

    # ── 行情数据 ──────────────────────────────────────────────
    "014_daily.py",
    "018_weekly.py",
    "019_monthly.py",
    "023_adj_factor.py",
    "027_daily_basic.py",
    "029_stk_limit.py",
    "030_suspend_d.py",
    "031_hsgt_top10.py",
    "032_ggt_top10.py",

    # ── 财务数据（按股票循环，耗时长）────────────────────────
    "036_income.py",
    "037_balancesheet.py",
    "038_cashflow.py",
    "039_forecast.py",
    "040_express.py",
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
    parser.add_argument("--only", nargs="+", help="只执行指定编号，如 001 003")
    parser.add_argument("--skip", nargs="+", help="跳过指定编号，如 036 037")
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
