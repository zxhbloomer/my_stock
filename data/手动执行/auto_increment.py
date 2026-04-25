"""
自动增量同步脚本
================
按顺序执行所有增量脚本，一个失败不影响其他
用法: python auto_increment.py
"""
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

INC_DIR = Path(__file__).parent / "增量"

SCRIPTS = [
    "inc_01_stock_daily.py",
    "inc_02_stock_dailybasic.py",
    "inc_03_moneyflow.py",
    "inc_04_stock_chips.py",
    "inc_05_stock_adjfactor.py",
    "inc_06_fina_indicator.py",
    "inc_07_fina_forecast.py",
    "inc_08_fina_express.py",
    "inc_09_index_swdaily.py",
    "inc_10_index_swmember.py",
    "inc_11_moneyflow_hsgt.py",
    "inc_12_stock_basic.py",
]


def run_script(script_path: Path) -> tuple[bool, float]:
    start = time.time()
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False,
        text=True,
    )
    elapsed = time.time() - start
    return result.returncode == 0, elapsed


def main():
    print("=" * 60)
    print(f"  自动增量同步  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = []
    total_start = time.time()

    for i, script in enumerate(SCRIPTS, 1):
        path = INC_DIR / script
        if not path.exists():
            print(f"\n[{i:2d}/{len(SCRIPTS)}] {script} — 文件不存在，跳过")
            results.append((script, False, 0))
            continue

        print(f"\n{'='*60}")
        print(f"[{i:2d}/{len(SCRIPTS)}] 开始: {script}")
        print(f"{'='*60}")

        ok, elapsed = run_script(path)
        status = "✓ 成功" if ok else "✗ 失败"
        print(f"\n>>> {script} {status}  耗时 {elapsed:.0f}秒")
        results.append((script, ok, elapsed))

    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  汇总报告  总耗时 {total_elapsed/60:.1f} 分钟")
    print(f"{'='*60}")
    for script, ok, elapsed in results:
        status = "✓" if ok else "✗"
        print(f"  {status} {script:<40} {elapsed:6.0f}秒")

    failed = [s for s, ok, _ in results if not ok]
    if failed:
        print(f"\n[警告] {len(failed)} 个脚本失败: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"\n[完成] 全部 {len(SCRIPTS)} 个增量脚本执行成功")


if __name__ == "__main__":
    main()
