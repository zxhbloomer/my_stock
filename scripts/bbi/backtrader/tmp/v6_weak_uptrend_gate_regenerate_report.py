import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd


TMP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = TMP_DIR / "v6_weak_uptrend_gate_output"


def load_experiment():
    spec = importlib.util.spec_from_file_location(
        "v6_weak_uptrend_gate_experiment",
        TMP_DIR / "v6_weak_uptrend_gate_experiment.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_variant_outputs(exp):
    outputs = {}
    for variant in exp.VARIANTS:
        variant_dir = OUTPUT_DIR / variant
        outputs[variant] = {
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
        "Tavily 复核：上涨趋势常用均线多头排列、长均线向上、相对强度和 52 周强度；"
        "A 股文献显示中期动量不稳定，短期动量与反转并存，所以牛市和弱市不应使用完全相同门槛。"
    )
    exp.build_report(baselines, experiments, expert_notes)
    print(f"regenerated {exp.REPORT_PATH}")


if __name__ == "__main__":
    main()
