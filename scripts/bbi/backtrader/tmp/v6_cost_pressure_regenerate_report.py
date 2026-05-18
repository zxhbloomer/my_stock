import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = TMP_DIR / "v6_cost_pressure_output"


def load_experiment():
    spec = importlib.util.spec_from_file_location(
        "v6_cost_pressure_experiment",
        TMP_DIR / "v6_cost_pressure_experiment.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_variant_outputs(exp):
    outputs = {}
    for case in exp.CASES:
        for bps in exp.EXTRA_COST_BPS:
            label = f"{exp.case_name(case)}_cost{bps}bps"
            variant_dir = OUTPUT_DIR / label
            outputs[label] = {
                "nav": pd.read_csv(variant_dir / "nav_series.csv"),
                "trades": pd.read_csv(variant_dir / "trade_records.csv"),
                "rebalance": pd.read_csv(variant_dir / "rebalance_log.csv"),
                "scores": pd.read_csv(variant_dir / "strength_scores.csv"),
                "stats": json.loads((variant_dir / "summary.json").read_text(encoding="utf-8")),
            }
    return outputs


def main():
    exp = load_experiment()
    baselines = exp.load_baseline_outputs()
    experiments = load_variant_outputs(exp)
    expert_notes = (
        "Tavily 本轮成本/滑点搜索因额度限制失败，未使用其他搜索工具。"
        "本地设计评审原则：成本压力测试比继续堆过滤器更接近实盘；"
        "额外 bps 成本只改 commission，不改交易信号，便于归因。"
    )
    exp.build_report(baselines, experiments, expert_notes)
    print(f"regenerated {exp.REPORT_PATH}")


if __name__ == "__main__":
    main()
