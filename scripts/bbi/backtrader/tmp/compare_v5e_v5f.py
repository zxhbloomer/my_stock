# compare_v5e_v5f.py — 对比 v5e（基准）vs v5f（BBI死叉N日确认）
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent / "output"


def load(version):
    p = BASE / version / "stats_summary.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    return df


def summarize(df, label):
    return {
        "version": label,
        "stocks": len(df),
        "avg_annual_ret%": round(df["annual_return_pct"].mean(), 2),
        "median_annual%": round(df["annual_return_pct"].median(), 2),
        "pct_positive": round((df["annual_return_pct"] > 0).mean() * 100, 1),
        "avg_calmar": round(df["calmar_ratio"].mean(), 4),
        "avg_win%": round(df["win_rate"].mean() * 100, 1),
        "avg_maxdd%": round(df["max_drawdown_pct"].mean(), 2),
        "avg_hold_d": round(df["avg_hold_days"].mean(), 1),
        "avg_trades": round(df["trade_count"].mean(), 1),
        "avg_pl_ratio": round(df["profit_loss_ratio"].mean(), 3),
    }


def main():
    v5e   = load("v5e_fast")
    v5f   = load("v5f")
    v5g   = load("v5g")
    v5h   = load("v5h")
    v5h_b = load("v5h_b")
    v5i   = load("v5i")
    v5k   = load("v5k")

    v5L   = load("v5L")

    v5M   = load("v5M")

    versions = []
    if v5e   is not None: versions.append((v5e,   "v5e (baseline)"))
    if v5L   is not None: versions.append((v5L,   "v5L (dynPos)"))
    if v5M   is not None: versions.append((v5M,   "v5M (dynPos+ADX)"))

    if not versions:
        print("No data found")
        return

    rows = [summarize(df, label) for df, label in versions]
    result = pd.DataFrame(rows).set_index("version").T
    print("\n=== 版本对比 ===")
    print(result.to_string())

    # 相对 v5e 的变化
    if v5e is not None and len(rows) > 1:
        print("\n=== 相对 v5e (baseline) 的变化 ===")
        base = rows[0]
        for row in rows[1:]:
            print(f"\n  [{row['version']}]")
            for col in ["avg_annual_ret%", "median_annual%", "pct_positive",
                        "avg_calmar", "avg_win%", "avg_maxdd%", "avg_hold_d", "avg_trades"]:
                b_val = base[col]
                n_val = row[col]
                delta = n_val - b_val
                sign  = "+" if delta >= 0 else ""
                print(f"    {col:20s}: {b_val:8.3f} → {n_val:8.3f}  ({sign}{delta:.3f})")

    # 持仓天数分布对比
    print("\n=== 持仓天数分布 ===")
    dir_map = {"v5e": "v5e_fast", "v5f": "v5f", "v5g": "v5g",
               "v5h": "v5h", "v5h_b": "v5h_b", "v5i": "v5i",
               "v5k": "v5k", "v5L": "v5L", "v5M": "v5M"}
    for df, label in versions:
        key = label.split()[0]
        trades_p = BASE / dir_map.get(key, key) / "trades_detail.csv"
        if trades_p.exists():
            td = pd.read_csv(trades_p)
            td = td[td["sell_date"] != "open"]
            if not td.empty:
                bins = [0, 10, 20, 30, 60, 90, 999]
                lbls = ["<10d", "10-20d", "20-30d", "30-60d", "60-90d", "90d+"]
                td["bucket"] = pd.cut(td["hold_days"], bins=bins, labels=lbls)
                dist = td.groupby("bucket", observed=True).size()
                pct  = (dist / len(td) * 100).round(1)
                print(f"  {label}: " + " | ".join(f"{l}:{p}%" for l, p in zip(lbls, pct)))


if __name__ == "__main__":
    main()
