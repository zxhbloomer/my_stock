# Qlib中国A股完整工作流程指南

## 概述

本文档基于官方Qlib文档，提供中国A股量化投资的完整工作流程，包括数据准备、模型训练、预测、回测和可视化分析。

## 目录

1. [环境初始化](#1-环境初始化)
2. [数据准备](#2-数据准备)
3. [特征工程](#3-特征工程)
4. [模型训练](#4-模型训练)
5. [预测生成](#5-预测生成)
6. [回测分析](#6-回测分析)
7. [可视化分析](#7-可视化分析)
8. [完整工作流程示例](#8-完整工作流程示例)

---

## 1. Qlib完整目录结构

### 1.1 标准目录结构

```
~/.qlib/                              # Qlib根目录
├── qlib_data/                        # 数据存储根目录
│   ├── cn_data/                      # 中国A股日频数据
│   │   ├── calendars/                # 交易日历
│   │   │   └── day.txt              # 日频交易日历（格式: YYYY-MM-DD，每行一个日期）
│   │   ├── instruments/              # 股票池定义
│   │   │   ├── all.txt              # 全市场股票列表
│   │   │   ├── csi300.txt           # 沪深300成份股
│   │   │   ├── csi500.txt           # 中证500成份股
│   │   │   └── ...                  # 其他股票池
│   │   └── features/                 # 股票特征数据（二进制格式）
│   │       ├── sh600000/             # 股票代码目录
│   │       │   ├── open.day.bin     # 开盘价数据
│   │       │   ├── high.day.bin     # 最高价数据
│   │       │   ├── low.day.bin      # 最低价数据
│   │       │   ├── close.day.bin    # 收盘价数据
│   │       │   ├── volume.day.bin   # 成交量数据
│   │       │   ├── factor.day.bin   # 复权因子数据
│   │       │   └── ...              # 其他特征数据
│   │       ├── sh600519/             # 贵州茅台
│   │       ├── sz000001/             # 平安银行
│   │       └── ...                   # 其他股票
│   │
│   ├── cn_data_1min/                 # 中国A股分钟数据（可选）
│   │   ├── calendars/
│   │   │   └── 1min.txt             # 分钟级交易日历
│   │   ├── instruments/
│   │   └── features/
│   │
│   └── pit/                          # Point-in-Time数据（季度/年度财务数据）
│       └── quarterly/                # 季度数据
│           └── ...
│
├── stock_data/                       # 原始数据存储（可选）
│   ├── source/                       # 数据源文件
│   │   ├── cn_data/                 # CSV格式原始数据
│   │   │   ├── sh600000.csv
│   │   │   ├── sh600519.csv
│   │   │   └── ...
│   │   └── cn_1min/                 # 分钟级原始数据
│   │
│   └── normalize/                    # 归一化后的数据
│
├── cache/                            # 缓存目录（自动生成）
│   ├── [hash_expression_cache]/     # 表达式计算缓存
│   │   ├── .meta                    # 元数据文件
│   │   └── data.pkl                 # 缓存数据
│   └── [hash_dataset_cache]/        # 数据集缓存
│       ├── .meta
│       ├── .index
│       └── data.pkl
│
└── mlruns/                           # MLflow实验跟踪（项目目录）
    ├── 0/                            # 实验ID
    │   ├── meta.yaml                # 实验元数据
    │   └── [run_id]/                # 运行ID
    │       ├── artifacts/           # 存储的对象
    │       │   ├── model.pkl        # 训练好的模型
    │       │   ├── pred.pkl         # 预测结果
    │       │   └── portfolio_analysis/  # 组合分析结果
    │       │       ├── report_normal_1day.pkl
    │       │       ├── positions_normal_1day.pkl
    │       │       └── port_analysis_1day.pkl
    │       ├── metrics/             # 性能指标
    │       ├── params/              # 超参数
    │       └── tags/                # 标签
    └── 1/
```

### 1.2 数据文件格式详解

#### 1.2.1 交易日历文件 (calendars/day.txt)

**格式**: 纯文本文件，每行一个交易日期

```text
2008-01-02
2008-01-03
2008-01-04
2008-01-07
2008-01-08
...
2020-12-31
```

**说明**:
- 日期格式: `YYYY-MM-DD`
- 只包含交易日，不包含周末和节假日
- 按时间顺序排列

#### 1.2.2 股票池文件 (instruments/csi300.txt)

**格式**: 纯文本文件，包含股票代码、起始日期、结束日期

```text
SH600000	2008-01-02	2099-12-31
SH600519	2008-01-02	2099-12-31
SZ000001	2008-01-02	2099-12-31
SZ000002	2008-01-02	2020-06-15
...
```

**字段说明**:
- 第1列: 股票代码 (SH开头为上交所，SZ开头为深交所)
- 第2列: 该股票在此股票池的起始日期
- 第3列: 该股票在此股票池的结束日期 (2099-12-31表示仍在池中)
- 分隔符: Tab键 (`\t`)

#### 1.2.3 特征数据文件 (features/sh600000/close.day.bin)

**格式**: NumPy二进制数组 (`.bin`)

**数据结构**:
```python
# 二进制文件存储格式
dtype = np.float32  # 4字节浮点数
# 每个交易日对应一个浮点数值
# 按时间顺序排列，与交易日历对应
```

**示例读取**:
```python
import numpy as np

# 读取收盘价数据
close_data = np.fromfile('~/.qlib/qlib_data/cn_data/features/sh600000/close.day.bin', dtype=np.float32)
print(close_data.shape)  # (交易日数量,)
print(close_data[:5])    # 前5个交易日的收盘价
```

**常见特征文件**:
- `open.day.bin`: 开盘价
- `high.day.bin`: 最高价
- `low.day.bin`: 最低价
- `close.day.bin`: 收盘价
- `volume.day.bin`: 成交量
- `factor.day.bin`: 复权因子 (用于前复权/后复权计算)
- `vwap.day.bin`: 成交量加权平均价 (如果有)
- `amount.day.bin`: 成交额 (如果有)

#### 1.2.4 PIT数据格式 (Point-in-Time 财务数据)

**数据结构** (quarterly数据):
```python
# PIT数据采用结构化数组存储
dtype = [
    ('date', '<u4'),      # 公告日期 (YYYYMMDD格式的无符号整数)
    ('period', '<u4'),    # 报告期 (YYYYQQ格式，如202001表示2020年Q1)
    ('value', '<f8'),     # 数据值 (双精度浮点数)
    ('_next', '<u4')      # 下一条记录的字节索引
]
```

**示例数据** (某股票的ROE数据):
```python
array([
    (20200428, 202001, 0.0902, 4294967295),  # 2020-04-28公布2020Q1 ROE=9.02%
    (20200817, 202002, 0.1393, 4294967295),  # 2020-08-17公布2020Q2 ROE=13.93%
    (20201023, 202003, 0.2459, 4294967295),  # 2020-10-23公布2020Q3 ROE=24.59%
    (20210301, 202004, 0.3479, 80),          # 2021-03-01公布2020Q4 ROE=34.79%
    (20210313, 202004, 0.3960, 4294967295),  # 2021-03-13修正2020Q4 ROE=39.60%
    ...
], dtype=dtype)
```

**说明**:
- `_next`: 指向同一报告期下一次更新的字节位置，4294967295表示最新数据
- PIT数据保证了历史回测的时间一致性，避免前视偏差

#### 1.2.5 缓存文件格式

**表达式缓存** (cache/[hash]/):
```
[hash_of_expression]/
├── .meta                    # 元数据文件 (JSON格式)
│   {
│       "instrument": "sh600000",
│       "field": "$close / Ref($close, 5)",
│       "freq": "day",
│       "visit_count": 12,
│       "last_visit": "2024-01-15 10:30:00"
│   }
└── data.pkl                 # Pickle序列化的计算结果
```

**数据集缓存** (cache/[hash]/):
```
[hash_of_dataset_config]/
├── .meta                    # 元数据
├── .index                   # 索引文件 (行索引到日期的映射)
└── data.pkl                 # 完整数据集
```

### 1.3 环境初始化

#### 1.3.1 Qlib初始化

```python
import qlib
from qlib.constant import REG_CN

# 初始化Qlib - 中国市场
provider_uri = "~/.qlib/qlib_data/cn_data"
qlib.init(provider_uri=provider_uri, region=REG_CN)
```

#### 1.3.2 下载数据

```bash
# 方法1: 使用官方脚本下载预处理数据
python scripts/get_data.py qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn

# 方法2: 下载分钟级数据（可选，用于高频策略）
python scripts/get_data.py qlib_data --target_dir ~/.qlib/qlib_data/cn_data_1min --region cn --interval 1min

# 方法3: 从GitHub下载预编译数据包（备用）
wget https://github.com/chenditc/investment_data/releases/latest/download/qlib_bin.tar.gz
mkdir -p ~/.qlib/qlib_data/cn_data
tar -zxvf qlib_bin.tar.gz -C ~/.qlib/qlib_data/cn_data --strip-components=2
rm -f qlib_bin.tar.gz
```

#### 1.3.3 自定义数据准备流程

**步骤1: 下载原始数据**
```bash
# 从Yahoo Finance下载（示例）
python scripts/data_collector/yahoo/collector.py download_data \
    --source_dir ~/.qlib/stock_data/source/cn_data \
    --start 2008-01-01 \
    --end 2024-12-31 \
    --delay 1 \
    --interval 1d \
    --region CN
```

**步骤2: 数据归一化**
```bash
python scripts/data_collector/yahoo/collector.py normalize_data \
    --source_dir ~/.qlib/stock_data/source/cn_data \
    --normalize_dir ~/.qlib/stock_data/normalize/cn_data \
    --region CN \
    --interval 1d
```

**步骤3: 转换为Qlib二进制格式**
```bash
python scripts/dump_bin.py dump_all \
    --data_path ~/.qlib/stock_data/normalize/cn_data \
    --qlib_dir ~/.qlib/qlib_data/cn_data \
    --freq day \
    --include_fields open,close,high,low,volume,factor \
    --date_field_name date \
    --symbol_field_name instrument \
    --file_suffix .csv
```

**说明**:
- `--include_fields`: 指定要转换的字段（对应CSV列名）
- `--exclude_fields`: 可选，排除不需要的字段（如date, symbol）
- `--date_field_name`: CSV中日期列的名称
- `--symbol_field_name`: CSV中股票代码列的名称
- `--file_suffix`: 源文件后缀（.csv或.parquet）

#### 1.3.4 数据完整性检查

```bash
# 检查数据健康度
python scripts/check_data_health.py check_data \
    --qlib_dir ~/.qlib/qlib_data/cn_data

# 使用自定义阈值检查
python scripts/check_data_health.py check_data \
    --qlib_dir ~/.qlib/qlib_data/cn_data \
    --missing_data_num 30055 \
    --large_step_threshold_volume 94485 \
    --large_step_threshold_price 20
```

**检查内容**:
- 缺失数据数量
- 价格/成交量异常波动
- 必需字段完整性 (open, high, low, close, volume, factor)

---

## 2. 数据准备

### 2.1 获取交易日历

```python
from qlib.data import D

# 获取指定时间范围的交易日历
calendar = D.calendar(start_time='2010-01-01', end_time='2020-12-31', freq='day')
print(calendar[:10])
```

### 2.2 定义股票池

```python
# 使用CSI300指数成份股
market = "csi300"
instruments = D.instruments(market)

# 获取指定时间范围的股票列表
stock_list = D.list_instruments(
    instruments=instruments,
    start_time='2010-01-01',
    end_time='2020-12-31',
    as_list=True
)
print(f"股票数量: {len(stock_list)}")
print(f"前10只股票: {stock_list[:10]}")
```

### 2.3 获取股票特征数据

```python
# 单只股票的OHLCV数据
instruments = ['SH600000']
fields = ['$open', '$high', '$low', '$close', '$volume', '$factor']

df = D.features(
    instruments,
    fields,
    start_time='2020-01-01',
    end_time='2020-12-31',
    freq='day'
)
print(df.head())
```

---

## 3. 特征工程

### 3.1 使用Alpha158特征集

Alpha158是Qlib内置的158个技术指标特征，适用于股票预测。

```python
from qlib.contrib.data.handler import Alpha158
from qlib.data.dataset import DatasetH

# 配置数据处理器
data_handler_config = {
    "start_time": "2008-01-01",
    "end_time": "2020-08-01",
    "fit_start_time": "2008-01-01",
    "fit_end_time": "2014-12-31",
    "instruments": "csi300",
    "infer_processors": [
        {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
        {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
    ],
    "learn_processors": [
        {"class": "DropnaLabel"},
        {"class": "CSZScoreNorm", "kwargs": {"fields_group": "label"}},
    ],
}

# 创建数据集
dataset = DatasetH(
    handler={
        "class": "Alpha158",
        "module_path": "qlib.contrib.data.handler",
        "kwargs": data_handler_config,
    },
    segments={
        "train": ["2008-01-01", "2014-12-31"],
        "valid": ["2015-01-01", "2016-12-31"],
        "test": ["2017-01-01", "2020-08-01"]
    }
)
```

### 3.2 查看特征数据

```python
# 准备训练数据
train_data = dataset.prepare("train", col_set=["feature", "label"])
print(f"训练样本数: {len(train_data)}")
print(f"特征维度: {train_data['feature'].shape[1]}")
print(train_data.head())
```

---

## 4. 模型训练

### 4.1 LightGBM模型训练

```python
from qlib.contrib.model.gbdt import LGBModel
from qlib.workflow import R
from qlib.utils import flatten_dict

# 创建LightGBM模型
model = LGBModel(
    loss="mse",
    learning_rate=0.1,
    max_depth=8,
    num_leaves=210,
    colsample_bytree=0.8879,
    subsample=0.8789,
    lambda_l1=205.6999,
    lambda_l2=580.9768,
    num_threads=20,
    early_stopping_rounds=50,
    num_boost_round=1000
)

# 开始训练实验
with R.start(experiment_name="lightgbm_alpha158"):
    # 记录超参数
    R.log_params(**flatten_dict({
        "model": "LGBModel",
        "loss": "mse",
        "learning_rate": 0.1,
        "max_depth": 8
    }))

    # 训练模型
    evals_result = {}
    model.fit(
        dataset,
        verbose_eval=20,
        evals_result=evals_result
    )

    # 保存模型
    R.save_objects(**{"model.pkl": model})

    # 获取训练信息
    print(f"最佳迭代次数: {model.model.best_iteration}")
    print(f"验证集MSE: {evals_result['valid_0']['l2'][-1]:.6f}")

    # 保存实验ID
    recorder = R.get_recorder()
    rid = recorder.id
    print(f"实验ID: {rid}")
```

### 4.2 多模型集成训练

```python
from qlib.model.trainer import TrainerR
from qlib.contrib.model.pytorch_nn import DNNModelPytorch
from qlib.contrib.model.gbdt import LGBModel, XGBModel

# 定义多个模型任务
tasks = [
    {
        "model": {
            "class": "LGBModel",
            "module_path": "qlib.contrib.model.gbdt",
            "kwargs": {"loss": "mse", "learning_rate": 0.1, "num_leaves": 64}
        },
        "dataset": dataset
    },
    {
        "model": {
            "class": "XGBModel",
            "module_path": "qlib.contrib.model.gbdt",
            "kwargs": {"loss": "mse", "eta": 0.1, "max_depth": 6}
        },
        "dataset": dataset
    },
]

# 训练所有模型
trainer = TrainerR(
    experiment_name="ensemble_models",
    call_in_subproc=True
)

recorders = trainer.train(tasks)
print(f"训练了 {len(recorders)} 个模型")

# 集成预测
import pandas as pd
ensemble_pred = pd.DataFrame()
for recorder in recorders:
    model = recorder.load_object("model.pkl")
    pred = model.predict(dataset, segment="test")
    ensemble_pred[recorder.info['id']] = pred

# 平均集成
final_pred = ensemble_pred.mean(axis=1)
print(f"集成预测形状: {final_pred.shape}")
```

---

## 5. 预测生成

### 5.1 生成预测信号

```python
from qlib.workflow.record_temp import SignalRecord

# 加载训练好的模型
with R.start(experiment_name="backtest_analysis"):
    recorder = R.get_recorder(recorder_id=rid, experiment_name="lightgbm_alpha158")
    model = recorder.load_object("model.pkl")

    # 生成预测信号
    new_recorder = R.get_recorder()
    sr = SignalRecord(model, dataset, new_recorder)
    sr.generate()

    # 获取预测结果
    pred_df = new_recorder.load_object("pred.pkl")
    print(f"预测数据形状: {pred_df.shape}")
    print(pred_df.head())
```

### 5.2 查看预测结果

```python
# 测试集预测
predictions = model.predict(dataset, segment="test")
print("预测结果示例:")
print(predictions.head(10))

# 预测统计
print(f"\n预测统计:")
print(f"平均值: {predictions.mean():.6f}")
print(f"标准差: {predictions.std():.6f}")
print(f"最小值: {predictions.min():.6f}")
print(f"最大值: {predictions.max():.6f}")
```

---

## 6. 回测分析

### 6.1 配置回测参数

```python
# 回测配置
benchmark = "SH000300"  # 沪深300指数作为基准

port_analysis_config = {
    "executor": {
        "class": "SimulatorExecutor",
        "module_path": "qlib.backtest.executor",
        "kwargs": {
            "time_per_step": "day",
            "generate_portfolio_metrics": True,
        },
    },
    "strategy": {
        "class": "TopkDropoutStrategy",
        "module_path": "qlib.contrib.strategy.signal_strategy",
        "kwargs": {
            "signal": "<PRED>",  # 使用模型预测作为信号
            "topk": 50,          # 持仓前50只股票
            "n_drop": 5,         # 每期替换5只股票
        },
    },
    "backtest": {
        "start_time": "2017-01-01",
        "end_time": "2020-08-01",
        "account": 100000000,      # 初始资金1亿
        "benchmark": benchmark,
        "exchange_kwargs": {
            "freq": "day",
            "limit_threshold": 0.095,  # 涨跌停限制9.5%
            "deal_price": "close",     # 使用收盘价成交
            "open_cost": 0.0005,       # 买入手续费0.05%
            "close_cost": 0.0015,      # 卖出手续费0.15%
            "min_cost": 5,             # 最小手续费5元
        },
    },
}
```

### 6.2 执行回测

```python
from qlib.workflow.record_temp import PortAnaRecord

# 执行回测和分析
with R.start(experiment_name="backtest_analysis", recorder_id=rid, resume=True):
    recorder = R.get_recorder()

    # 组合分析
    par = PortAnaRecord(recorder, port_analysis_config, "day")
    par.generate()

    # 保存回测结果
    ba_rid = recorder.id
    print(f"回测记录ID: {ba_rid}")
```

### 6.3 加载回测结果

```python
from qlib.contrib.report import analysis_position, analysis_model
from qlib.contrib.evaluate import risk_analysis

# 加载回测结果
recorder = R.get_recorder(recorder_id=ba_rid, experiment_name="backtest_analysis")

# 加载各类分析结果
pred_df = recorder.load_object("pred.pkl")
report_normal_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
positions = recorder.load_object("portfolio_analysis/positions_normal_1day.pkl")
analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

print("回测报告示例:")
print(report_normal_df.head())
```

### 6.4 绩效指标分析

```python
# 计算风险收益指标
from qlib.contrib.evaluate import backtest_analysis

# 绩效分析
report_dict = backtest_analysis(
    report_normal_df,
    account=100000000,
    benchmark=benchmark
)

print("\n组合绩效:")
print(f"年化收益率: {report_dict['annualized_return']:.2%}")
print(f"年化波动率: {report_dict['annualized_volatility']:.2%}")
print(f"信息比率(IR): {report_dict['information_ratio']:.2f}")
print(f"最大回撤: {report_dict['max_drawdown']:.2%}")
print(f"卡玛比率: {report_dict['calmar_ratio']:.2f}")
print(f"胜率: {report_dict['win_rate']:.2%}")
```

---

## 7. 可视化分析

### 7.1 组合收益曲线

```python
import matplotlib.pyplot as plt
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

# 绘制组合收益曲线
analysis_position.report_graph(report_normal_df)
plt.show()
```

### 7.2 风险分析图表

```python
# 风险分析图表
analysis_position.risk_analysis_graph(analysis_df, report_normal_df)
plt.show()
```

### 7.3 IC分析

```python
# 合并预测和标签
label_df = dataset.prepare("test", col_set="label")
label_df.columns = ["label"]

pred_label = pd.concat([label_df, pred_df], axis=1, sort=True).reindex(label_df.index)

# IC分析图表
analysis_position.score_ic_graph(pred_label)
plt.show()
```

### 7.4 模型性能分析

```python
# 模型性能图表
analysis_model.model_performance_graph(pred_label)
plt.show()
```

### 7.5 自定义中文图表

```python
# 使用自定义中文图表工具
from utils.chinese_charts import show_all_charts_cn

# 显示所有中文图表
show_all_charts_cn(
    recorder=recorder,
    pred_label=pred_label,
    report_df=report_normal_df,
    analysis_df=analysis_df
)
```

---

## 8. 完整工作流程示例

### 8.1 使用YAML配置文件

创建配置文件 `workflow_config_lightgbm_Alpha158.yaml`:

```yaml
qlib_init:
    provider_uri: "~/.qlib/qlib_data/cn_data"
    region: cn

market: &market csi300
benchmark: &benchmark SH000300

task:
    model:
        class: LGBModel
        module_path: qlib.contrib.model.gbdt
        kwargs:
            loss: mse
            learning_rate: 0.1
            max_depth: 8
            num_leaves: 210
            colsample_bytree: 0.8879
            subsample: 0.8789
            lambda_l1: 205.6999
            lambda_l2: 580.9768
            num_threads: 20

    dataset:
        class: DatasetH
        module_path: qlib.data.dataset
        kwargs:
            handler:
                class: Alpha158
                module_path: qlib.contrib.data.handler
                kwargs:
                    start_time: 2008-01-01
                    end_time: 2020-08-01
                    fit_start_time: 2008-01-01
                    fit_end_time: 2014-12-31
                    instruments: *market
            segments:
                train: [2008-01-01, 2014-12-31]
                valid: [2015-01-01, 2016-12-31]
                test: [2017-01-01, 2020-08-01]

    record:
        - class: SignalRecord
          module_path: qlib.workflow.record_temp
        - class: SigAnaRecord
          module_path: qlib.workflow.record_temp
        - class: PortAnaRecord
          module_path: qlib.workflow.record_temp
          kwargs:
            config:
                strategy:
                    class: TopkDropoutStrategy
                    module_path: qlib.contrib.strategy
                    kwargs:
                        signal: <PRED>
                        topk: 50
                        n_drop: 5
                backtest:
                    start_time: 2017-01-01
                    end_time: 2020-08-01
                    account: 100000000
                    benchmark: *benchmark
                    exchange_kwargs:
                        freq: day
                        limit_threshold: 0.095
                        deal_price: close
                        open_cost: 0.0005
                        close_cost: 0.0015
                        min_cost: 5
```

### 8.2 运行完整工作流程

```bash
# 使用qrun命令执行完整工作流程
qrun workflow_config_lightgbm_Alpha158.yaml
```

### 8.3 Python代码完整示例

```python
import qlib
import pandas as pd
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config, flatten_dict
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord
from qlib.contrib.report import analysis_position, analysis_model

# 1. 初始化Qlib
provider_uri = "~/.qlib/qlib_data/cn_data"
qlib.init(provider_uri=provider_uri, region=REG_CN)

# 2. 定义市场和基准
market = "csi300"
benchmark = "SH000300"

# 3. 配置数据处理器
data_handler_config = {
    "start_time": "2008-01-01",
    "end_time": "2020-08-01",
    "fit_start_time": "2008-01-01",
    "fit_end_time": "2014-12-31",
    "instruments": market,
}

# 4. 配置任务
task = {
    "model": {
        "class": "LGBModel",
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": {
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
            "num_threads": 20,
        },
    },
    "dataset": {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": {
                "class": "Alpha158",
                "module_path": "qlib.contrib.data.handler",
                "kwargs": data_handler_config,
            },
            "segments": {
                "train": ("2008-01-01", "2014-12-31"),
                "valid": ("2015-01-01", "2016-12-31"),
                "test": ("2017-01-01", "2020-08-01"),
            },
        },
    },
}

# 5. 初始化模型和数据集
model = init_instance_by_config(task["model"])
dataset = init_instance_by_config(task["dataset"])

# 6. 训练模型
with R.start(experiment_name="train_model"):
    R.log_params(**flatten_dict(task))
    model.fit(dataset)
    R.save_objects(trained_model=model)
    rid = R.get_recorder().id
    print(f"训练完成，实验ID: {rid}")

# 7. 生成预测信号
with R.start(experiment_name="backtest_analysis"):
    recorder = R.get_recorder(recorder_id=rid, experiment_name="train_model")
    model = recorder.load_object("trained_model")

    # 预测
    new_recorder = R.get_recorder()
    ba_rid = new_recorder.id
    sr = SignalRecord(model, dataset, new_recorder)
    sr.generate()

    # 配置回测
    port_analysis_config = {
        "executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        },
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {
                "signal": "<PRED>",
                "topk": 50,
                "n_drop": 5,
            },
        },
        "backtest": {
            "start_time": "2017-01-01",
            "end_time": "2020-08-01",
            "account": 100000000,
            "benchmark": benchmark,
            "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        },
    }

    # 执行回测
    par = PortAnaRecord(new_recorder, port_analysis_config, "day")
    par.generate()
    print(f"回测完成，回测ID: {ba_rid}")

# 8. 加载并分析结果
recorder = R.get_recorder(recorder_id=ba_rid, experiment_name="backtest_analysis")
pred_df = recorder.load_object("pred.pkl")
report_normal_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
positions = recorder.load_object("portfolio_analysis/positions_normal_1day.pkl")
analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

# 9. 绩效指标
print("\n绩效分析:")
print(analysis_df)

# 10. 可视化
label_df = dataset.prepare("test", col_set="label")
label_df.columns = ["label"]
pred_label = pd.concat([label_df, pred_df], axis=1, sort=True).reindex(label_df.index)

# 生成图表
analysis_position.report_graph(report_normal_df)
analysis_position.risk_analysis_graph(analysis_df, report_normal_df)
analysis_position.score_ic_graph(pred_label)
analysis_model.model_performance_graph(pred_label)

print("\n完整工作流程执行完毕！")
```

---

## 9. 进阶功能

### 9.1 强化学习策略（订单执行优化）

```python
from qlib.rl.order_execution import SingleAssetOrderExecutionSimple
from qlib.rl.order_execution.policy import PPO
from qlib.rl.order_execution.interpreter import CategoricalActionInterpreter, FullHistoryStateInterpreter
from qlib.rl.order_execution.reward import PPOReward

# 配置强化学习训练
# 详见官方文档 examples/rl_order_execution/
```

### 9.2 在线学习和滚动更新

```python
from qlib.workflow.online.strategy import RollingOnlineStrategy
from qlib.workflow.online.manager import OnlineManager

# 配置在线策略
online_strategy = RollingOnlineStrategy(
    name="rolling_strategy",
    task_template=task,
    rolling_step=20,   # 每20天重新训练
    horizon=20         # 预测周期
)

# 运行在线服务
# online_manager = OnlineManager(...)
# online_manager.run()
```

### 9.3 特征重要性分析

```python
import numpy as np
import shap

# 获取特征重要性
feature_importance = model.model.feature_importance(importance_type="gain")
feature_names = dataset.handler.get_feature_names()

importance_df = pd.DataFrame({
    "feature": feature_names,
    "importance": feature_importance
}).sort_values("importance", ascending=False)

print("Top 10 特征:")
print(importance_df.head(10))

# SHAP分析
test_data = dataset.prepare("test", col_set="feature")
explainer = shap.TreeExplainer(model.model)
shap_values = explainer.shap_values(test_data.values[:1000])

mean_abs_shap = np.abs(shap_values).mean(axis=0)
shap_importance = pd.DataFrame({
    "feature": feature_names,
    "shap_importance": mean_abs_shap
}).sort_values("shap_importance", ascending=False)

print("\nTop 10 SHAP特征:")
print(shap_importance.head(10))
```

---

## 10. 关键指标说明

### 10.1 回测指标

| 指标 | 英文名称 | 说明 |
|------|---------|------|
| 年化收益率 | Annualized Return | 策略年化收益率 |
| 年化波动率 | Annualized Volatility | 收益率年化标准差 |
| 信息比率 | Information Ratio (IR) | 超额收益/跟踪误差，IR>1优秀 |
| 最大回撤 | Max Drawdown (MDD) | 净值最大回撤百分比 |
| 夏普比率 | Sharpe Ratio | 风险调整后收益 |
| 卡玛比率 | Calmar Ratio | 年化收益/最大回撤 |
| 胜率 | Win Rate | 盈利交易日占比 |

### 10.2 IC指标

| 指标 | 说明 | 参考值 |
|------|------|-------|
| IC均值 | 预测与收益的线性相关系数均值 | >0.01良好，>0.03优秀 |
| Rank IC | 预测与收益的秩相关系数 | 更稳健的相关性度量 |
| ICIR | IC均值/IC标准差 | 类似信息比率 |

---

## 11. 常见问题

### 11.1 数据缺失处理

```python
# 在数据处理器中配置填充策略
"infer_processors": [
    {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
],
```

### 11.2 调整交易成本

```python
# 在回测配置中修改
"exchange_kwargs": {
    "open_cost": 0.0003,   # 降低买入成本到0.03%
    "close_cost": 0.0013,  # 降低卖出成本到0.13%
}
```

### 11.3 更换股票池

```python
# 使用不同的指数
market = "csi500"      # 中证500
benchmark = "SH000905"  # 中证500指数
```

---

## 12. 参考资源

- **官方文档**: https://github.com/microsoft/qlib
- **API文档**: https://qlib.readthedocs.io/
- **示例代码**: `qlib/examples/`
- **论文**: Qlib相关学术论文

---

## 总结

本指南覆盖了使用Qlib进行中国A股量化投资的完整工作流程：

1. ✅ 环境初始化和数据下载
2. ✅ 特征工程（Alpha158）
3. ✅ 模型训练（LightGBM）
4. ✅ 预测生成
5. ✅ 回测分析（TopkDropoutStrategy）
6. ✅ 可视化分析（收益曲线、IC、风险分析）
7. ✅ 完整示例代码

所有代码均基于官方Qlib文档和实际示例，可直接运行使用。
