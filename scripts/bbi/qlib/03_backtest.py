"""
03_backtest.py
基于02_train_predict.py生成的预测score，运行回测并输出IC分析报告

用法:
    python scripts/bbi/03_backtest.py
    python scripts/bbi/03_backtest.py --recorder-id <id>
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    import qlib
except ImportError:
    sys.path.insert(0, "D:/2026_project/99_github/qlib-main/qlib")
    import qlib

import yaml
from qlib.config import REG_CN
from qlib.contrib.evaluate import backtest_daily, risk_analysis
from qlib.contrib.eva.alpha import calc_ic
from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
from qlib.workflow import R

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
QLIB_DIR = CFG["qlib_data"]["output_dir"]
EXP_NAME = CFG["mlflow"]["experiment_name"]
TEST_START, TEST_END = CFG["segments"]["test"]
BENCHMARK = CFG["market"]["benchmark"]
TOPK = CFG["model"]["topk"]
N_DROP = CFG["model"]["n_drop"]
BC = CFG["backtest"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recorder-id", default=None)
    args = parser.parse_args()

    qlib.init(provider_uri=QLIB_DIR, region=REG_CN, kernels=8)

    exp = R.get_exp(experiment_name=EXP_NAME)
    if args.recorder_id:
        recorder = R.get_recorder(recorder_id=args.recorder_id, experiment_name=EXP_NAME)
    else:
        recorders = exp.list_recorders()
        recorder = sorted(recorders.values(), key=lambda r: r.info["start_time"])[-1]

    print(f"[03_backtest] Using recorder: {recorder.id}")

    pred = recorder.load_object("pred.pkl")
    label = recorder.load_object("label.pkl")

    print("\n=== IC Analysis ===")
    pred_s = pred.iloc[:, 0] if hasattr(pred, "columns") else pred
    label_s = label.iloc[:, 0] if hasattr(label, "columns") else label
    ic, ric = calc_ic(pred_s, label_s, dropna=True)
    ic_mean = float(ic.mean())
    icir = float(ic.mean() / ic.std())
    rank_ic = float(ric.mean())
    print(f"IC Mean: {ic_mean:.4f}")
    print(f"ICIR:    {icir:.4f}")
    print(f"Rank IC: {rank_ic:.4f}")

    strategy = TopkDropoutStrategy(
        signal=pred,
        topk=TOPK,
        n_drop=N_DROP,
    )

    report_normal, positions_normal = backtest_daily(
        start_time=TEST_START,
        end_time=TEST_END,
        strategy=strategy,
        executor={
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
                "verbose": False,
            },
        },
        account=1_000_000,
        benchmark=BENCHMARK,
        exchange_kwargs={
            "limit_threshold": BC["limit_threshold"],
            "deal_price": BC["deal_price"],
            "open_cost": BC["open_cost"],
            "close_cost": BC["close_cost"],
            "min_cost": BC["min_cost"],
        },
    )

    print("\n=== Backtest Report ===")
    analysis = risk_analysis(report_normal["return"])
    print(analysis)
    print("\n=== Benchmark Report ===")
    bench_analysis = risk_analysis(report_normal["bench"])
    print(bench_analysis)

    excess = report_normal["return"] - report_normal["bench"]
    print("\n=== Excess Return ===")
    print(risk_analysis(excess))

    recorder.log_metrics(**{
        "ic_mean": ic_mean,
        "icir": icir,
        "rank_ic": rank_ic,
    })

    # 生成每日换仓清单
    _save_trade_log(positions_normal)
    print(f"\n[03_backtest] Done! View: mlflow ui --backend-store-uri {ROOT}/mlruns")


def _save_trade_log(positions_normal):
    """提取每笔交易的买入/卖出价格、收益率，按股票维度汇总"""
    import pandas as pd
    from qlib.data import D
    from sqlalchemy import create_engine, text

    # 1. 提取每只股票的买入/卖出日期
    open_trades = {}   # ts_code -> buy_date
    trades = []        # 已平仓交易列表

    for dt in sorted(positions_normal.keys()):
        pos = positions_normal[dt]
        curr_set = set(pos.get_stock_list())
        prev_set = set(open_trades.keys())

        # 新买入
        for s in curr_set - prev_set:
            open_trades[s] = dt

        # 卖出（平仓）
        for s in prev_set - curr_set:
            trades.append({
                "ts_code": s,
                "buy_date": open_trades.pop(s),
                "sell_date": dt,
            })

    # 最后一天仍持仓的视为未平仓，记录为持有中
    last_date = max(positions_normal.keys())
    for s, buy_dt in open_trades.items():
        trades.append({
            "ts_code": s,
            "buy_date": buy_dt,
            "sell_date": last_date,
            "open": True,
        })

    if not trades:
        print("[trade_log] No trades found.")
        return

    df = pd.DataFrame(trades)
    df["open"] = df.get("open", False).fillna(False)

    # 2. 批量查收盘价
    all_codes = df["ts_code"].unique().tolist()
    min_date = df["buy_date"].min()
    max_date = df["sell_date"].max()

    price_df = D.features(all_codes, ["$close"], start_time=min_date, end_time=max_date, freq="day")
    price_df.columns = ["close"]
    price_df = price_df.reset_index()
    price_df.columns = ["ts_code", "date", "close"]
    price_map = price_df.set_index(["ts_code", "date"])["close"]

    def get_price(ts_code, dt):
        try:
            return float(price_map.loc[(ts_code, dt)])
        except KeyError:
            return float("nan")

    df["buy_price"] = df.apply(lambda r: get_price(r["ts_code"], r["buy_date"]), axis=1)
    df["sell_price"] = df.apply(lambda r: get_price(r["ts_code"], r["sell_date"]), axis=1)
    df["return_pct"] = (df["sell_price"] - df["buy_price"]) / df["buy_price"] * 100
    df["hold_days"] = (df["sell_date"] - df["buy_date"]).dt.days

    # 3. 查股票名称
    try:
        cfg = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
        engine = create_engine(cfg["database"]["url"])
        schema = cfg["database"]["schema"]

        def to_db_code(c):
            if c.endswith("sh"): return c[:-2].upper() + ".SH"
            if c.endswith("sz"): return c[:-2].upper() + ".SZ"
            return c

        db_codes = [to_db_code(c) for c in all_codes]
        codes_str = "','".join(db_codes)
        with engine.connect() as conn:
            name_df = pd.read_sql(
                text(f"SELECT ts_code, name FROM {schema}.\"001_stock_basic\" WHERE ts_code IN ('{codes_str}')"),
                conn
            )
        name_map = {r["ts_code"]: r["name"] for _, r in name_df.iterrows()}
        df["name"] = df["ts_code"].apply(lambda c: name_map.get(to_db_code(c), ""))
    except Exception:
        df["name"] = ""

    # 过滤ST/*ST股票（名称含ST的全部剔除）
    st_mask = df["name"].str.contains("ST", na=False)
    if st_mask.any():
        print(f"[trade_log] 过滤ST股票: {st_mask.sum()} 笔交易 ({df.loc[st_mask,'ts_code'].nunique()} 只)")
        df = df[~st_mask].reset_index(drop=True)

    # 4. 整理输出列
    df["buy_date"] = df["buy_date"].dt.date.astype(str)
    df["sell_date"] = df["sell_date"].dt.date.astype(str)
    df["status"] = df["open"].map({True: "持有中", False: "已平仓"})
    out = df[["ts_code", "name", "buy_date", "buy_price", "sell_date", "sell_price",
              "return_pct", "hold_days", "status"]].copy()
    out["buy_price"] = out["buy_price"].round(3)
    out["sell_price"] = out["sell_price"].round(3)
    out["return_pct"] = out["return_pct"].round(2)

    out_dir = ROOT / "data/手动执行/推荐结果"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 5. 保存交易明细
    detail_path = out_dir / "trade_detail.csv"
    out.to_csv(detail_path, index=False, encoding="utf-8-sig")

    # 6. 按股票汇总
    closed = out[out["status"] == "已平仓"]
    summary = closed.groupby(["ts_code", "name"]).agg(
        交易次数=("return_pct", "count"),
        平均收益率=("return_pct", "mean"),
        总收益率=("return_pct", "sum"),
        胜率=("return_pct", lambda x: (x > 0).mean() * 100),
        平均持有天数=("hold_days", "mean"),
    ).round(2).sort_values("总收益率", ascending=False).reset_index()

    summary_path = out_dir / "trade_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # 7. 打印汇总
    closed_count = len(closed)
    win_rate = (closed["return_pct"] > 0).mean() * 100
    avg_ret = closed["return_pct"].mean()
    print(f"\n=== 交易汇总 ===")
    print(f"总交易笔数: {closed_count}  胜率: {win_rate:.1f}%  平均收益率: {avg_ret:.2f}%")
    print(f"\n收益最高的10只股票:")
    print(summary.head(10).to_string(index=False))
    print(f"\n交易明细已保存: {detail_path}")
    print(f"股票汇总已保存: {summary_path}")


if __name__ == "__main__":
    main()
