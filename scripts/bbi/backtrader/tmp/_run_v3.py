import subprocess, sys
result = subprocess.run(
    [r"C:\Users\Administrator\miniconda3\envs\mystock\python.exe", "-X", "utf8",
     r"D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp\20_run_backtest_v3.py"],
    capture_output=True, text=True, encoding='utf-8',
    cwd=r"D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\tmp"
)
print("STDOUT:", result.stdout[-3000:] if len(result.stdout) > 3000 else result.stdout)
print("STDERR:", result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)
print("Return code:", result.returncode)
