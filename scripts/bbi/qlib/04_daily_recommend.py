"""
04_daily_recommend.py
每日收盘后运行，输出今日推荐股票列表

前提：
  1. 03_backtest.py验证IC均值 > 0.02
  2. 数据库当日数据已更新
  3. 先运行 python scripts/bbi/01_data_to_qlib.py --incremental

用法:
    python scripts/bbi/04_daily_recommend.py
    python scripts/bbi/04_daily_recommend.py --date 2026-04-19
    python scripts/bbi/04_daily_recommend.py --topn 20
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import yaml
from sqlalchemy import create_engine, text

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    import qlib
except ImportError:
    sys.path.insert(0, "D:/2026_project/99_github/qlib-main/qlib")
    import qlib

from qlib.config import REG_CN
from qlib.workflow import R

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
QLIB_DIR = CFG["qlib_data"]["output_dir"]
EXP_NAME = CFG["mlflow"]["experiment_name"]
OUTPUT_DIR = ROOT / "data/手动执行/推荐结果"


def get_conn():
    return create_engine(CFG["database"]["url"]).connect()



def get_stock_names(conn, ts_codes: list) -> dict:
    schema = CFG["database"]["schema"]
    codes_str = "','".join(ts_codes)
    df = pd.read_sql(
        text(f"SELECT ts_code, name FROM {schema}.\"001_stock_basic\" WHERE ts_code IN ('{codes_str}')"),
        conn
    )
    return dict(zip(df["ts_code"], df["name"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.today().strftime("%Y-%m-%d"))
    parser.add_argument("--topn", type=int, default=CFG["model"]["topk"])
    parser.add_argument("--recorder-id", default=None)
    args = parser.parse_args()

    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)

    exp = R.get_exp(experiment_name=EXP_NAME)
    if args.recorder_id:
        recorder = R.get_recorder(recorder_id=args.recorder_id, experiment_name=EXP_NAME)
    else:
        recorders = exp.list_recorders()
        recorder = sorted(recorders.values(), key=lambda r: r.info["start_time"])[-1]

    pred = recorder.load_object("pred.pkl")

    target_date = pd.Timestamp(args.date)
    available = pred.index.get_level_values("datetime").unique().sort_values()
    candidates = available[available <= target_date]
    if len(candidates) == 0:
        print(f"[04_daily_recommend] 没有 {args.date} 之前的预测数据")
        return
    target_date = candidates[-1]
    if str(target_date.date()) != args.date:
        print(f"[04_daily_recommend] {args.date} 无数据，使用最近日期 {target_date.date()}")

    day_pred = pred.xs(target_date, level="datetime").sort_values("score", ascending=False)
    top_stocks = day_pred.head(args.topn)

    conn = get_conn()
    # qlib格式 600282sh → 数据库格式 600282.SH
    def to_db_code(c):
        if c.endswith("sh"):
            return c[:-2].upper() + ".SH"
        elif c.endswith("sz"):
            return c[:-2].upper() + ".SZ"
        return c
    db_codes = [to_db_code(c) for c in top_stocks.index.tolist()]
    name_map_db = get_stock_names(conn, db_codes)
    # 反转回 qlib 格式的 key
    name_map = {c: name_map_db.get(to_db_code(c), "") for c in top_stocks.index.tolist()}
    conn.close()

    result = top_stocks.reset_index()
    result.columns = ["ts_code", "score"]
    result["rank"] = range(1, len(result) + 1)
    result["name"] = result["ts_code"].map(name_map).fillna("")
    result["date"] = str(target_date.date())
    result = result[["date", "ts_code", "name", "score", "rank"]]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{target_date.date()}.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"\n=== 推荐股票 {target_date.date()} Top{args.topn} ===")
    print(result.to_string(index=False))
    print(f"\n[04_daily_recommend] 结果已保存: {out_path}")


if __name__ == "__main__":
    main()
