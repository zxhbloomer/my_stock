"""
run_all.py — 按顺序执行所有同步脚本
用法: python run_all.py
      python run_all.py --only 001 003 005   # 只跑指定编号
      python run_all.py --skip 036 037 038   # 跳过指定编号（耗时长的按股票循环脚本）

注意：
  036~044 为按股票循环的财务类接口，单次运行耗时较长（数小时），
  日常增量更新建议单独运行或用 --skip 跳过。
  063 stk_factor_pro 字段200+，按日期循环，耗时较长。
  137 idx_factor_pro 字段80+，按日期循环，耗时较长。
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

SCRIPTS = [
    # ── 基础数据 ──────────────────────────────────────────────
    "001_stock_basic.py",
    # "002_stk_premarket.py",  # PASS: 自定义HTTP服务不支持此接口
    "003_trade_cal.py",
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
    "041_dividend.py",
    "042_fina_indicator.py",
    "043_fina_audit.py",

    # ── 特色数据 ──────────────────────────────────────────────
    "061_cyq_perf.py",
    "062_cyq_chips.py",
    "063_stk_factor_pro.py",  # 200+字段，按日期循环，耗时长
    "066_hk_hold.py",
    "068_stk_auction_c.py",
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
    parser.add_argument("--only", nargs="+", help="只执行指定编号，如 001 003")
    parser.add_argument("--skip", nargs="+", help="跳过指定编号，如 009 010")
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
