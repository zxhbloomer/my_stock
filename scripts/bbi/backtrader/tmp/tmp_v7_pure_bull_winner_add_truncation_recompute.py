from __future__ import annotations

import html
import sys
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
REPO_ROOT = TMP_DIR.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.bbi.backtrader.tmp import tmp_v7_pure_bull_winner_add_experiment as exp

V7_DIR = TMP_DIR.parent / "v7"
SOURCE_OUTPUT = TMP_DIR / "tmp_v7_pure_bull_winner_add_output"
OUTPUT_DIR = TMP_DIR / "tmp_v7_pure_bull_winner_add_truncation_recompute_output"
REPORT_PATH = OUTPUT_DIR / "report.html"
README_PATH = TMP_DIR / "tmp_v7_pure_bull_winner_add_robustness_README.md"

CASE_NAME = "纯牛市小额最后加仓"
CASE = exp.CASES_BY_NAME[CASE_NAME]
AUDIT_PATH = SOURCE_OUTPUT / f"{CASE_NAME}_extra_add_audit.csv"


def append_progress(message):
    with README_PATH.open("a", encoding="utf-8") as fh:
        fh.write(f"- {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def find_matching_extra_buy(trades, expected):
    if trades.empty:
        return {"found": False}
    frame = trades.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    expected_date = pd.to_datetime(expected["date"]).strftime("%Y-%m-%d")
    matches = frame[
        frame["date"].eq(expected_date)
        & frame["ts_code"].eq(expected["ts_code"])
        & frame["reason"].eq("pure_bull_extra_add")
    ]
    if matches.empty:
        return {"found": False}
    row = matches.iloc[0]
    return {
        "found": True,
        "date": row["date"],
        "ts_code": row["ts_code"],
        "price": float(row["price"]),
        "shares": float(row["shares"]),
        "amount": float(row["amount"]),
    }


def compare_expected_actual(expected, actual):
    if not actual.get("found"):
        return {
            "passed": False,
            "fail_reason": "missing_truncated_extra_buy",
            "price_diff": None,
            "shares_diff": None,
            "amount_diff": None,
        }
    price_diff = round(float(actual["price"]) - float(expected["price"]), 4)
    shares_diff = round(float(actual["shares"]) - float(expected["shares"]), 4)
    amount_diff = round(float(actual["amount"]) - float(expected["amount"]), 2)
    passed = abs(price_diff) <= 0.0001 and abs(shares_diff) <= 0.0001 and abs(amount_diff) <= 0.01
    return {
        "passed": bool(passed),
        "fail_reason": "" if passed else "truncated_trade_mismatch",
        "price_diff": price_diff,
        "shares_diff": shares_diff,
        "amount_diff": amount_diff,
    }


def build_recompute_row(expected, actual, expected_sequence, truncated_fills, truncated_final_date):
    compare = compare_expected_actual(expected, actual)
    sequence_ok = int(truncated_fills) == int(expected_sequence)
    return {
        "date": pd.to_datetime(expected["date"]).strftime("%Y-%m-%d"),
        "signal_date": pd.to_datetime(expected["signal_date"]).strftime("%Y-%m-%d"),
        "ts_code": expected["ts_code"],
        "name": expected.get("name", ""),
        "expected_price": float(expected["price"]),
        "actual_price": actual.get("price"),
        "expected_shares": float(expected["shares"]),
        "actual_shares": actual.get("shares"),
        "expected_amount": float(expected["amount"]),
        "actual_amount": actual.get("amount"),
        "market_regime": expected.get("market_regime", ""),
        "truncated_final_date": truncated_final_date,
        "expected_sequence": int(expected_sequence),
        "truncated_extra_add_fills": int(truncated_fills),
        "sequence_ok": sequence_ok,
        "passed": bool(compare["passed"] and sequence_ok),
        "fail_reason": compare["fail_reason"] if compare["fail_reason"] else ("" if sequence_ok else "truncated_sequence_mismatch"),
        "price_diff": compare["price_diff"],
        "shares_diff": compare["shares_diff"],
        "amount_diff": compare["amount_diff"],
    }


def load_panel_market():
    panel = pd.read_parquet(V7_DIR / "output" / "panel.parquet")
    market = pd.read_parquet(V7_DIR / "output" / "market_index.parquet")
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    market = exp.normalize_market_frame(market)
    return panel, market


def run_one_recompute(panel, market, expected, expected_sequence):
    trade_date = pd.to_datetime(expected["date"])
    signal_date = pd.to_datetime(expected["signal_date"])
    panel_cut = panel[panel["trade_date"] <= trade_date].copy()
    market_cut = market[market.index <= signal_date].copy()
    stats, nav, trades, rebalance_log = exp.run_case(CASE, panel_cut, market_cut)
    actual = find_matching_extra_buy(trades, expected)
    return build_recompute_row(
        expected,
        actual,
        expected_sequence,
        int(stats.get("pure_bull_extra_add_fills", 0)),
        str(nav["date"].max())[:10] if not nav.empty else "",
    )


def table_html(df, title):
    headers = "".join(f"<th>{html.escape(str(col))}</th>" for col in df.columns)
    rows = []
    for _, row in df.iterrows():
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(v))}</td>" for v in row.tolist()) + "</tr>")
    return f"<h2>{html.escape(title)}</h2><table><thead><tr>{headers}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_report(results):
    passed = int(results["passed"].sum()) if not results.empty else 0
    total = int(len(results))
    advice = "截断重算通过" if total > 0 and passed == total else "截断重算未通过"
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>纯牛市小额最后加仓截断重算</title>
<style>
body {{ font-family: Arial, "Microsoft YaHei", sans-serif; margin: 24px; color: #1f2937; }}
h1 {{ font-size: 24px; }}
h2 {{ font-size: 18px; margin-top: 22px; }}
.note {{ background: #f3f4f6; border-left: 4px solid #2563eb; padding: 12px 14px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #d1d5db; padding: 7px 8px; text-align: right; white-space: nowrap; }}
th:first-child, td:first-child {{ text-align: left; }}
th {{ background: #374151; color: white; }}
</style>
</head>
<body>
<h1>纯牛市小额最后加仓截断重算</h1>
<div class="note"><b>结论：{html.escape(advice)}</b><br>口径：每笔成交只保留 panel <= 成交日，market <= signal_date 后重跑，检查同日同股票同 reason 是否重现。</div>
{table_html(results, "逐笔结果")}
</body>
</html>"""
    REPORT_PATH.write_text(html_text, encoding="utf-8")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    append_progress("开始截断重算：逐笔只保留成交日及以前数据。")
    audit = pd.read_csv(AUDIT_PATH)
    panel, market = load_panel_market()
    rows = []
    for idx, expected in audit.iterrows():
        rows.append(run_one_recompute(panel, market, expected, idx + 1))
    results = pd.DataFrame(rows)
    results.to_csv(OUTPUT_DIR / "truncation_recompute_results.csv", index=False, encoding="utf-8-sig")
    render_report(results)
    passed = int(results["passed"].sum()) if not results.empty else 0
    append_progress(f"截断重算完成：passed={passed}/{len(results)}，report={REPORT_PATH}")


if __name__ == "__main__":
    main()
