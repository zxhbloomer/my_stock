"""
run_all-041~139.py - 执行编号 041~139 的同步脚本
用法: python -X utf8 run_all-041~139.py
      python -X utf8 run_all-041~139.py --only 041 080 121
      python -X utf8 run_all-041~139.py --skip 063 137

注意：
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
    # -- 财务数据后段（按股票循环，耗时长）--
    "041_dividend.py",
    "042_fina_indicator.py",
    "043_fina_audit.py",

    # -- 特色数据 --
    "061_cyq_perf.py",
    "062_cyq_chips.py",
    "063_stk_factor_pro.py",  # 200+字段，按日期循环，耗时长
    "066_hk_hold.py",
    "069_stk_nineturn.py",

    # -- 两融及转融通 --
    "073_margin.py",
    "074_margin_detail.py",
    "075_margin_secs.py",
    "076_slb_sec.py",
    "077_slb_len.py",
    "078_slb_sec_detail.py",

    # -- 资金流向 --
    "080_moneyflow.py",
    "081_moneyflow_ths.py",
    "082_moneyflow_dc.py",
    "083_moneyflow_cnt_ths.py",
    "084_moneyflow_ind_ths.py",
    "085_moneyflow_ind_dc.py",
    "086_moneyflow_mkt_dc.py",
    "087_moneyflow_hsgt.py",

    # -- 打板专题数据 --
    "088_top_list.py",
    "089_top_inst.py",
    "091_limit_list_d.py",
    "092_limit_step.py",

    # -- 指数专题 --
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
    parser.add_argument("--only", nargs="+", help="只执行指定编号，如 041 080 121")
    parser.add_argument("--skip", nargs="+", help="跳过指定编号，如 063 137")
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
