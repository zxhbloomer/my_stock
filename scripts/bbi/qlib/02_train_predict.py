
"""
02_train_predict.py
使用BBIAlpha Handler训练LightGBM，生成每日预测score

用法:
    python scripts/bbi/02_train_predict.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/bbi"))

try:
    import qlib
except ImportError:
    sys.path.insert(0, "D:/2026_project/99_github/qlib-main/qlib")
    import qlib

import yaml
from qlib.config import REG_CN
from qlib.contrib.model.gbdt import LGBModel
from qlib.data.dataset import DatasetH
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord

from handler import BBIAlpha

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
QLIB_DIR = CFG["qlib_data"]["output_dir"]
TRAIN_START, TRAIN_END = CFG["segments"]["train"]
VALID_START, VALID_END = CFG["segments"]["valid"]
TEST_START, TEST_END = CFG["segments"]["test"]
DATA_START = CFG["data"]["start_date"]
DATA_END = CFG["data"]["end_date"]
EXP_NAME = CFG["mlflow"]["experiment_name"]


DATASET_CACHE = Path(CFG["qlib_data"]["output_dir"]) / "dataset_cache.pkl"


def build_dataset():
    """阶段1：构建并缓存dataset到磁盘"""
    if DATASET_CACHE.exists():
        DATASET_CACHE.unlink()
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN, kernels=8)

    handler_config = {
        "start_time": DATA_START,
        "end_time": DATA_END,
        "fit_start_time": TRAIN_START,
        "fit_end_time": TRAIN_END,
        "instruments": "all",
        "infer_processors": [
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
        "learn_processors": [
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
        "label": ["Ref($close, -2) / Ref($close, -1) - 1"],
    }

    handler = BBIAlpha(**handler_config)
    dataset = DatasetH(
        handler=handler,
        segments={
            "train": (TRAIN_START, TRAIN_END),
            "valid": (VALID_START, VALID_END),
            "test":  (TEST_START, TEST_END),
        },
    )
    dataset.config(dump_all=True, recursive=True)
    dataset.to_pickle(DATASET_CACHE)
    print(f"[02] Dataset cached to {DATASET_CACHE}")


def train():
    """阶段2：从缓存加载dataset，训练模型"""
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN, kernels=1)

    dataset = DatasetH.load(DATASET_CACHE)

    model = LGBModel(
        loss="mse",
        colsample_bytree=0.8879,
        learning_rate=0.0421,
        subsample=0.8789,
        lambda_l1=205.6999,
        lambda_l2=580.9768,
        max_depth=8,
        num_leaves=210,
        num_threads=20,
    )

    with R.start(experiment_name=EXP_NAME):
        model.fit(dataset)
        R.save_objects(trained_model=model)
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()
        print(f"[02_train_predict] Done! Recorder ID: {recorder.id}")
        print(f"View results: mlflow ui --backend-store-uri {ROOT}/mlruns")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["build", "train", "all"], default="all")
    args = parser.parse_args()

    if args.stage == "build":
        build_dataset()
    elif args.stage == "train":
        train()
    else:
        import subprocess, sys
        subprocess.run([sys.executable, __file__, "--stage", "build"], check=True)
        train()


if __name__ == "__main__":
    main()
