# BBI因子 + Qlib完整流水线 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将BBI作为自定义因子加入Qlib Alpha158因子库，使用LightGBM在全A股选股，完成预测→选股→回测→每日荐股完整链路。

**Architecture:** PostgreSQL(tushare_v2) → 01_data_to_qlib.py转换为Qlib二进制 → handler.py定义173个因子 → 02_train_predict.py训练LightGBM → 03_backtest.py回测 → 04_daily_recommend.py每日荐股。训练集2018-2022，测试集2023-2026，全A股过滤ST/停牌/涨跌停/次新股/小市值/北交所。

**Tech Stack:** Python 3.8+, Qlib 0.9+, LightGBM, PostgreSQL(psycopg2), pandas, numpy

---

## 文件结构

```
scripts/bbi/
├── config.yaml              # 统一配置（DB连接、路径、训练参数）
├── handler.py               # BBIAlpha Handler（Alpha158 + 173因子）
├── 01_data_to_qlib.py       # PostgreSQL → Qlib二进制（一次性+增量）
├── 02_train_predict.py      # LightGBM训练与预测
├── 03_backtest.py           # 回测与IC分析报告
├── 04_daily_recommend.py    # 每日荐股（Phase 2）
└── 05_view_recommend.py     # 查看历史荐股结果
```

**数据输出目录：** `D:\Data\my_stock\`

---

## Task 1: config.yaml — 统一配置文件

**Files:**
- Create: `scripts/bbi/config.yaml`

- [ ] **Step 1: 创建配置文件**

```yaml
# scripts/bbi/config.yaml

database:
  url: "postgresql://root:123456@localhost:5432/my_stock"
  schema: "tushare_v2"

qlib_data:
  output_dir: "D:/Data/my_stock"
  region: "cn"

data:
  start_date: "2018-01-01"
  end_date: "2026-04-16"

segments:
  train: ["2018-01-01", "2022-12-31"]
  valid: ["2023-01-01", "2024-06-30"]
  test:  ["2024-07-01", "2026-04-16"]

market:
  universe: "all"          # 全A股
  benchmark: "SH000905"    # CSI500基准

stock_filter:
  min_circ_mv: 20          # 流通市值最小20亿（单位：亿元）
  min_amount: 5000         # 日均成交额最小5000万（单位：万元）
  exclude_bj: true         # 排除北交所
  exclude_st: true         # 排除ST/*ST
  min_list_days: 365       # 上市满1年

model:
  topk: 50                 # 每日持仓50只
  n_drop: 5                # 每期替换5只

backtest:
  limit_threshold: 0.095
  open_cost: 0.0005
  close_cost: 0.0015
  min_cost: 5
  deal_price: "close"

mlflow:
  experiment_name: "bbi_alpha"
  tracking_uri: "mlruns"
```

- [ ] **Step 2: 验证配置文件可读**

```bash
python -c "import yaml; cfg=yaml.safe_load(open('scripts/bbi/config.yaml')); print(cfg['database']['url'])"
```
Expected: `postgresql://root:123456@localhost:5432/my_stock`

---

## Task 2: handler.py — BBIAlpha自定义Handler

**Files:**
- Create: `scripts/bbi/handler.py`

- [ ] **Step 1: 创建handler.py**

```python
import sys
sys.path.insert(0, "D:/2026_project/99_github/qlib-main/qlib")

from qlib.contrib.data.handler import Alpha158


class BBIAlpha(Alpha158):
    """Alpha158 + BBI因子扩展，共173个因子。
    
    新增因子：
    - BBI组（6个）：基于bbi字段
    - 估值组（5个）：来自027_daily_basic
    - 筹码组（2个）：来自061_cyq_perf（2018起）
    - 资金流组（2个）：来自080_moneyflow
    """

    def get_feature_config(self):
        fields, names = super().get_feature_config()

        bbi_fields = [
            "$bbi/$close",
            "$close/$bbi - 1",
            "($bbi - Ref($bbi,1))/$bbi",
            "If($close > $bbi, 1, -1)",
            "Mean($close > $bbi, 5)",
            "Mean($close > $bbi, 20)",
        ]
        bbi_names = [
            "BBI_RATIO", "BBI_DEV", "BBI_SLOPE",
            "BBI_CROSS", "BBI_CROSS5", "BBI_CROSS20",
        ]

        val_fields = [
            "$pe_ttm",
            "$pb",
            "$turnover",
            "Rank($pe_ttm, 20)",
            "Rank($turnover, 20)",
        ]
        val_names = ["PE_TTM", "PB", "TURNOVER", "PE_RANK20", "TURN_RANK20"]

        chip_fields = [
            "$winner_rate",
            "$cost_avg / $close - 1",
        ]
        chip_names = ["WINNER_RATE", "COST_DEV"]

        flow_fields = [
            "$net_mf / ($volume * $close + 1e-12)",
            "Mean($net_mf, 5) / ($volume * $close + 1e-12)",
        ]
        flow_names = ["MF_RATIO", "MF_RATIO5"]

        fields += bbi_fields + val_fields + chip_fields + flow_fields
        names += bbi_names + val_names + chip_names + flow_names

        return fields, names
```

- [ ] **Step 2: 验证handler可导入**

```bash
cd D:/2026_project/10_quantify/00_py/my_stock
python -c "from scripts.bbi.handler import BBIAlpha; h = BBIAlpha.__new__(BBIAlpha); print('BBIAlpha OK')"
```
Expected: `BBIAlpha OK`

---

## Task 3: 01_data_to_qlib.py — 数据转换脚本

**Files:**
- Create: `scripts/bbi/01_data_to_qlib.py`

此脚本从PostgreSQL读取数据，写入Qlib二进制格式到`D:\Data\my_stock\`。

- [ ] **Step 1: 创建脚本（第一部分：导入和配置）**

```python
"""
01_data_to_qlib.py
PostgreSQL(tushare_v2) → Qlib二进制格式

用法:
    python scripts/bbi/01_data_to_qlib.py           # 全量转换
    python scripts/bbi/01_data_to_qlib.py --incremental  # 增量更新（追加最新数据）
"""
import argparse
import os
import struct
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
import yaml
from tqdm import tqdm

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
DB_URL = CFG["database"]["url"]
SCHEMA = CFG["database"]["schema"]
OUTPUT_DIR = Path(CFG["qlib_data"]["output_dir"])
START_DATE = CFG["data"]["start_date"]
END_DATE = CFG["data"]["end_date"]


def get_conn():
    import psycopg2
    from urllib.parse import urlparse
    u = urlparse(DB_URL)
    return psycopg2.connect(
        host=u.hostname, port=u.port or 5432,
        dbname=u.path.lstrip("/"),
        user=u.username, password=u.password
    )
```

- [ ] **Step 2: 添加交易日历写入函数**

在Step 1代码后追加：

```python

def write_calendars(conn):
    """写交易日历到 calendars/day.txt"""
    cal_dir = OUTPUT_DIR / "calendars"
    cal_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_sql(
        f"SELECT cal_date FROM {SCHEMA}.\"003_trade_cal\" "
        f"WHERE exchange='SSE' AND is_open=1 "
        f"AND cal_date >= '{START_DATE}' AND cal_date <= '{END_DATE}' "
        f"ORDER BY cal_date",
        conn
    )
    with open(cal_dir / "day.txt", "w") as f:
        for d in df["cal_date"]:
            f.write(str(d)[:10] + "\n")
    print(f"[calendars] {len(df)} trading days written")
```

- [ ] **Step 3: 添加股票列表写入函数**

```python

def write_instruments(conn):
    """写股票列表到 instruments/all.txt，过滤北交所"""
    inst_dir = OUTPUT_DIR / "instruments"
    inst_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_sql(
        f"SELECT ts_code, list_date, delist_date FROM {SCHEMA}.\"001_stock_basic\" "
        f"WHERE list_status IN ('L','D') "
        f"AND ts_code NOT LIKE '8%'",   # 排除北交所
        conn
    )
    df["delist_date"] = df["delist_date"].fillna("2099-12-31")
    with open(inst_dir / "all.txt", "w") as f:
        for _, row in df.iterrows():
            symbol = row["ts_code"].replace(".", "").lower()
            f.write(f"{symbol}\t{str(row['list_date'])[:10]}\t{str(row['delist_date'])[:10]}\n")
    print(f"[instruments] {len(df)} stocks written")
    return df["ts_code"].tolist()
```

- [ ] **Step 4: 添加二进制写入工具函数**

```python

def write_bin(path: Path, values: np.ndarray):
    """写Qlib .bin文件：4字节float32数组，前4字节为起始索引（固定0）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<I", 0))   # 起始索引
        f.write(values.astype(np.float32).tobytes())


def append_bin(path: Path, values: np.ndarray):
    """追加模式：读取现有文件长度，追加新数据"""
    if not path.exists():
        write_bin(path, values)
        return
    with open(path, "r+b") as f:
        f.seek(0, 2)   # 文件末尾
        f.write(values.astype(np.float32).tobytes())
```

- [ ] **Step 5: 添加主数据写入函数**

```python

FIELDS_063 = {
    "open":   "open_qfq",
    "high":   "high_qfq",
    "low":    "low_qfq",
    "close":  "close_qfq",
    "volume": "vol",
    "vwap":   "close_qfq",   # 无vwap，用close代替
    "bbi":    "bbi_qfq",
}

FIELDS_027 = {
    "pe_ttm":  "pe_ttm",
    "pb":      "pb",
    "turnover": "turnover_rate",
    "circ_mv": "circ_mv",
    "amount":  "amount",
}

FIELDS_061 = {
    "winner_rate": "winner_rate",
    "cost_avg":    "weight_avg",
}

FIELDS_080 = {
    "net_mf": "net_mf_amount",
}


def write_stock_features(conn, ts_codes: list, mode: str = "full"):
    """为每只股票写特征.bin文件"""
    feat_dir = OUTPUT_DIR / "features"

    # 一次性读取所有数据到内存（按表分批）
    print("[features] Loading 063_stk_factor_pro ...")
    df063 = pd.read_sql(
        f"SELECT ts_code, trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol, bbi_qfq "
        f"FROM {SCHEMA}.\"063_stk_factor_pro\" "
        f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
        f"ORDER BY ts_code, trade_date",
        conn, parse_dates=["trade_date"]
    )

    print("[features] Loading 027_daily_basic ...")
    df027 = pd.read_sql(
        f"SELECT ts_code, trade_date, pe_ttm, pb, turnover_rate, circ_mv, amount "
        f"FROM {SCHEMA}.\"027_daily_basic\" "
        f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
        f"ORDER BY ts_code, trade_date",
        conn, parse_dates=["trade_date"]
    )

    print("[features] Loading 061_cyq_perf ...")
    df061 = pd.read_sql(
        f"SELECT ts_code, trade_date, winner_rate, weight_avg "
        f"FROM {SCHEMA}.\"061_cyq_perf\" "
        f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
        f"ORDER BY ts_code, trade_date",
        conn, parse_dates=["trade_date"]
    )

    print("[features] Loading 080_moneyflow ...")
    df080 = pd.read_sql(
        f"SELECT ts_code, trade_date, net_mf_amount "
        f"FROM {SCHEMA}.\"080_moneyflow\" "
        f"WHERE trade_date >= '{START_DATE}' AND trade_date <= '{END_DATE}' "
        f"ORDER BY ts_code, trade_date",
        conn, parse_dates=["trade_date"]
    )

    # 读取交易日历作为时间轴
    cal_path = OUTPUT_DIR / "calendars/day.txt"
    calendar = pd.to_datetime([l.strip() for l in open(cal_path)])

    for ts_code in tqdm(ts_codes, desc="Writing features"):
        symbol = ts_code.replace(".", "").lower()
        s063 = df063[df063["ts_code"] == ts_code].set_index("trade_date")
        s027 = df027[df027["ts_code"] == ts_code].set_index("trade_date")
        s061 = df061[df061["ts_code"] == ts_code].set_index("trade_date")
        s080 = df080[df080["ts_code"] == ts_code].set_index("trade_date")

        # 以交易日历为基准reindex，缺失填NaN
        s063 = s063.reindex(calendar)
        s027 = s027.reindex(calendar)
        s061 = s061.reindex(calendar)
        s080 = s080.reindex(calendar)

        stock_dir = feat_dir / symbol
        write_fn = append_bin if mode == "incremental" else write_bin

        # 写063字段
        for qlib_name, col in FIELDS_063.items():
            vals = s063[col].values if col in s063.columns else np.full(len(calendar), np.nan)
            write_fn(stock_dir / f"{qlib_name}.day.bin", vals)

        # factor固定1.0（已后复权）
        write_fn(stock_dir / "factor.day.bin", np.ones(len(calendar), dtype=np.float32))

        # 写027字段
        for qlib_name, col in FIELDS_027.items():
            vals = s027[col].values if col in s027.columns else np.full(len(calendar), np.nan)
            write_fn(stock_dir / f"{qlib_name}.day.bin", vals)

        # 写061字段
        for qlib_name, col in FIELDS_061.items():
            vals = s061[col].values if col in s061.columns else np.full(len(calendar), np.nan)
            write_fn(stock_dir / f"{qlib_name}.day.bin", vals)

        # 写080字段
        for qlib_name, col in FIELDS_080.items():
            vals = s080[col].values if col in s080.columns else np.full(len(calendar), np.nan)
            write_fn(stock_dir / f"{qlib_name}.day.bin", vals)
```

- [ ] **Step 6: 添加main入口**

```python

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--incremental", action="store_true", help="增量更新模式")
    args = parser.parse_args()
    mode = "incremental" if args.incremental else "full"

    print(f"[01_data_to_qlib] mode={mode}, output={OUTPUT_DIR}")
    conn = get_conn()
    try:
        write_calendars(conn)
        ts_codes = write_instruments(conn)
        write_stock_features(conn, ts_codes, mode=mode)
        print("[01_data_to_qlib] Done!")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 运行数据转换（预计30-60分钟）**

```bash
cd D:/2026_project/10_quantify/00_py/my_stock
conda activate mystock
python scripts/bbi/01_data_to_qlib.py
```

Expected输出：
```
[01_data_to_qlib] mode=full, output=D:/Data/my_stock
[calendars] 2000+ trading days written
[instruments] 5000+ stocks written
[features] Loading 063_stk_factor_pro ...
...
[01_data_to_qlib] Done!
```

- [ ] **Step 8: 验证输出文件**

```bash
python -c "
from pathlib import Path
p = Path('D:/Data/my_stock')
print('calendars:', (p/'calendars/day.txt').exists())
print('instruments:', (p/'instruments/all.txt').exists())
import os
stocks = list((p/'features').iterdir())
print('stock dirs:', len(stocks))
bins = list((p/'features'/stocks[0].name).glob('*.bin'))
print('bins per stock:', len(bins), [b.name for b in bins[:5]])
"
```
Expected: calendars True, instruments True, stock dirs 5000+, bins per stock 16

---

## Task 4: 02_train_predict.py — 模型训练与预测

**Files:**
- Create: `scripts/bbi/02_train_predict.py`

- [ ] **Step 1: 创建训练脚本**

```python
"""
02_train_predict.py
使用BBIAlpha Handler训练LightGBM，生成每日预测score

用法:
    python scripts/bbi/02_train_predict.py
"""
import sys
from pathlib import Path

import qlib
import yaml
from qlib.config import REG_CN
from qlib.contrib.model.gbdt import LGBModel
from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
from qlib.data.dataset import DatasetH
from qlib.data.dataset.handler import DataHandlerLP
from qlib.utils import init_instance_by_config
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/bbi"))

from handler import BBIAlpha

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
QLIB_DIR = CFG["qlib_data"]["output_dir"]
TRAIN_START, TRAIN_END = CFG["segments"]["train"]
VALID_START, VALID_END = CFG["segments"]["valid"]
TEST_START, TEST_END = CFG["segments"]["test"]
DATA_START = CFG["data"]["start_date"]
DATA_END = CFG["data"]["end_date"]
EXP_NAME = CFG["mlflow"]["experiment_name"]


def main():
    # 初始化Qlib
    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)

    # Handler配置
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
        "label_names": ["LABEL0"],
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

    # LightGBM模型
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

    # 训练并记录到MLflow
    with R.start(experiment_name=EXP_NAME):
        model.fit(dataset)
        R.save_objects(trained_model=model)

        # 生成预测
        recorder = R.get_recorder()
        sr = SignalRecord(model, dataset, recorder)
        sr.generate()
        print(f"[02_train_predict] Done! Recorder ID: {recorder.id}")
        print(f"View results: mlflow ui --backend-store-uri {ROOT}/mlruns")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行训练（预计20-60分钟）**

```bash
cd D:/2026_project/10_quantify/00_py/my_stock
conda activate mystock
python scripts/bbi/02_train_predict.py
```

Expected输出末尾：
```
[02_train_predict] Done! Recorder ID: xxxxxxxx
View results: mlflow ui --backend-store-uri .../mlruns
```

---

## Task 5: 03_backtest.py — 回测与IC分析

**Files:**
- Create: `scripts/bbi/03_backtest.py`

- [ ] **Step 1: 创建回测脚本**

```python
"""
03_backtest.py
基于02_train_predict.py生成的预测score，运行回测并输出IC分析报告

用法:
    python scripts/bbi/03_backtest.py
    python scripts/bbi/03_backtest.py --recorder-id <id>  # 指定recorder
"""
import argparse
import sys
from pathlib import Path

import qlib
import yaml
from qlib.config import REG_CN
from qlib.contrib.evaluate import backtest_daily, risk_analysis
from qlib.contrib.report import analysis_model, analysis_position
from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
from qlib.workflow import R

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

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

    qlib.init(provider_uri=QLIB_DIR, region=REG_CN)

    # 获取最新recorder
    exp = R.get_exp(experiment_name=EXP_NAME)
    if args.recorder_id:
        recorder = R.get_recorder(recorder_id=args.recorder_id, experiment_name=EXP_NAME)
    else:
        recorders = exp.list_recorders()
        recorder = sorted(recorders.values(), key=lambda r: r.info["start_time"])[-1]

    print(f"[03_backtest] Using recorder: {recorder.id}")

    # 读取预测
    pred = recorder.load_object("pred.pkl")

    # IC分析
    print("\n=== IC Analysis ===")
    label = recorder.load_object("label.pkl")
    ic_df = analysis_model.calc_ic(pred, label)
    print(ic_df.describe())
    print(f"IC Mean: {ic_df['IC'].mean():.4f}")
    print(f"ICIR:    {ic_df['IC'].mean() / ic_df['IC'].std():.4f}")
    print(f"Rank IC: {ic_df['Rank IC'].mean():.4f}")

    # 回测
    strategy = TopkDropoutStrategy(
        signal=pred,
        topk=TOPK,
        n_drop=N_DROP,
    )

    portfolio_metric_dict, indicator_dict = backtest_daily(
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
    analysis = risk_analysis(portfolio_metric_dict["1day"]["portfolio_metrics"])
    print(analysis)

    # 保存报告
    recorder.log_metrics(**{
        "ic_mean": float(ic_df["IC"].mean()),
        "icir": float(ic_df["IC"].mean() / ic_df["IC"].std()),
        "rank_ic": float(ic_df["Rank IC"].mean()),
    })
    print(f"\n[03_backtest] Done! View: mlflow ui --backend-store-uri {ROOT}/mlruns")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行回测**

```bash
cd D:/2026_project/10_quantify/00_py/my_stock
conda activate mystock
python scripts/bbi/03_backtest.py
```

Expected输出包含：
```
=== IC Analysis ===
IC Mean: 0.0xxx
ICIR:    0.xxxx
=== Backtest Report ===
...annual_return...max_drawdown...
```

---

## Task 6: 04_daily_recommend.py — 每日荐股

**Files:**
- Create: `scripts/bbi/04_daily_recommend.py`

- [ ] **Step 1: 创建每日荐股脚本**

```python
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
import qlib
import yaml
from qlib.config import REG_CN
from qlib.workflow import R

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

CFG = yaml.safe_load(open(ROOT / "scripts/bbi/config.yaml"))
QLIB_DIR = CFG["qlib_data"]["output_dir"]
EXP_NAME = CFG["mlflow"]["experiment_name"]
OUTPUT_DIR = ROOT / "data/手动执行/推荐结果"


def get_stock_name(conn, ts_codes: list) -> dict:
    import psycopg2
    from urllib.parse import urlparse
    u = urlparse(CFG["database"]["url"])
    schema = CFG["database"]["schema"]
    codes_str = "','".join(ts_codes)
    df = pd.read_sql(
        f"SELECT ts_code, name FROM {schema}.\"001_stock_basic\" WHERE ts_code IN ('{codes_str}')",
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

    # 获取最新recorder
    exp = R.get_exp(experiment_name=EXP_NAME)
    if args.recorder_id:
        recorder = R.get_recorder(recorder_id=args.recorder_id, experiment_name=EXP_NAME)
    else:
        recorders = exp.list_recorders()
        recorder = sorted(recorders.values(), key=lambda r: r.info["start_time"])[-1]

    pred = recorder.load_object("pred.pkl")

    # 取指定日期的预测
    target_date = pd.Timestamp(args.date)
    if target_date not in pred.index.get_level_values("datetime"):
        # 取最近一个有数据的日期
        available = pred.index.get_level_values("datetime").unique().sort_values()
        target_date = available[available <= target_date][-1]
        print(f"[04_daily_recommend] No data for {args.date}, using {target_date.date()}")

    day_pred = pred.xs(target_date, level="datetime").sort_values("score", ascending=False)
    top_stocks = day_pred.head(args.topn)

    # 获取股票名称
    import psycopg2
    from urllib.parse import urlparse
    u = urlparse(CFG["database"]["url"])
    conn = psycopg2.connect(
        host=u.hostname, port=u.port or 5432,
        dbname=u.path.lstrip("/"),
        user=u.username, password=u.password
    )
    name_map = get_stock_name(conn, top_stocks.index.tolist())
    conn.close()

    result = top_stocks.reset_index()
    result.columns = ["ts_code", "score"]
    result["rank"] = range(1, len(result) + 1)
    result["name"] = result["ts_code"].map(name_map).fillna("")
    result["date"] = str(target_date.date())
    result = result[["date", "ts_code", "name", "score", "rank"]]

    # 保存结果
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{target_date.date()}.csv"
    result.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"\n=== 推荐股票 {target_date.date()} Top{args.topn} ===")
    print(result.to_string(index=False))
    print(f"\n[04_daily_recommend] 结果已保存: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行荐股**

```bash
cd D:/2026_project/10_quantify/00_py/my_stock
conda activate mystock
python scripts/bbi/04_daily_recommend.py --topn 20
```

Expected输出：
```
=== 推荐股票 2026-04-19 Top20 ===
date        ts_code  name    score  rank
2026-04-19  600519.SH 贵州茅台  0.031   1
...
结果已保存: data/手动执行/推荐结果/2026-04-19.csv
```

---

## Task 7: 05_view_recommend.py — 查看历史荐股

**Files:**
- Create: `scripts/bbi/05_view_recommend.py`

- [ ] **Step 1: 创建查看脚本**

```python
"""
05_view_recommend.py
查看历史推荐结果

用法:
    python scripts/bbi/05_view_recommend.py              # 查看最新一天
    python scripts/bbi/05_view_recommend.py --date 2026-04-19
    python scripts/bbi/05_view_recommend.py --list       # 列出所有历史日期
"""
import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = ROOT / "data/手动执行/推荐结果"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    csvs = sorted(OUTPUT_DIR.glob("*.csv"))
    if not csvs:
        print("暂无推荐结果，请先运行 04_daily_recommend.py")
        return

    if args.list:
        print("历史推荐日期：")
        for f in csvs:
            df = pd.read_csv(f)
            print(f"  {f.stem}  ({len(df)}只)")
        return

    if args.date:
        target = OUTPUT_DIR / f"{args.date}.csv"
    else:
        target = csvs[-1]

    if not target.exists():
        print(f"找不到 {target}")
        return

    df = pd.read_csv(target)
    print(f"\n=== 推荐结果 {target.stem} ===")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证查看脚本**

```bash
cd D:/2026_project/10_quantify/00_py/my_stock
conda activate mystock
python scripts/bbi/05_view_recommend.py --list
```

Expected: 列出已有的推荐日期文件

---

## 执行顺序总结

```
Step 1: python scripts/bbi/01_data_to_qlib.py          # 全量数据转换（一次性，30-60分钟）
Step 2: python scripts/bbi/02_train_predict.py          # 训练模型（20-60分钟）
Step 3: python scripts/bbi/03_backtest.py               # 回测验证（5分钟）
Step 4: python scripts/bbi/04_daily_recommend.py        # 每日荐股（每天收盘后）
Step 5: python scripts/bbi/05_view_recommend.py --list  # 查看历史

# 每日增量更新（收盘后）：
python scripts/bbi/01_data_to_qlib.py --incremental
python scripts/bbi/04_daily_recommend.py
```

## 验收标准

- [ ] IC均值 > 0.02（模型有预测力）
- [ ] ICIR > 0.5
- [ ] 年化超额收益 > 10%
- [ ] 最大回撤 < 20%
- [ ] 每日荐股输出CSV文件正常


