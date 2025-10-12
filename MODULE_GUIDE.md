# 模块使用指南

本项目按照 Qlib 官方架构重构，新增三个核心模块：数据获取、数据处理、因子计算。

## 📁 项目结构

```
my_stock/
├── data/                          # 数据模块
│   ├── collectors/               # 数据采集器
│   │   ├── base_collector.py    # 基类（参考Qlib官方）
│   │   └── tushare_collector.py # Tushare采集器
│   ├── processors/               # 数据处理器
│   │   ├── normalizer.py        # 数据标准化
│   │   └── validator.py         # 数据验证
│   └── loaders/                  # 数据加载器（预留）
├── factors/                       # 因子模块
│   └── alpha_factors.py          # Alpha因子库
├── handlers/                      # Handler模块
│   └── custom_handler.py         # 自定义Handler
├── examples/                      # 使用示例
│   ├── data_collection_example.py
│   └── custom_handler_example.py
├── configs/                       # 配置文件
├── utils/                         # 工具模块
└── run_workflow.py                # 主工作流
```

## 🚀 快速开始

### 1. 数据采集模块

#### 1.1 使用 Tushare 采集器

```python
from data.collectors.tushare_collector import Run

# 配置token
TOKEN = "your_tushare_token"
runner = Run(token=TOKEN)

# 下载数据
runner.download(
    source_dir="~/.qlib/stock_data/source/tushare",
    start_date="20200101",
    end_date="20231231",
    interval="1d",
    delay=0.5
)

# 标准化数据
runner.normalize(
    source_dir="~/.qlib/stock_data/source/tushare",
    normalize_dir="~/.qlib/stock_data/normalized/tushare",
    interval="1d"
)
```

#### 1.2 转换为 Qlib 格式

```bash
python scripts/dump_bin.py dump_all \
    --data_path ~/.qlib/stock_data/normalized/tushare \
    --qlib_dir ~/.qlib/qlib_data/cn_data \
    --freq day \
    --include_fields open,close,high,low,volume,factor
```

### 2. 数据处理模块

#### 2.1 数据标准化

```python
from data.processors.normalizer import DataNormalizer
import pandas as pd

# 读取数据
df = pd.read_csv("stock_data.csv")

# 前复权
df_adj = DataNormalizer.forward_adjust(df)

# 填充缺失值
df_filled = DataNormalizer.fill_missing_data(df_adj, method='ffill')

# 去除异常值
df_clean = DataNormalizer.remove_outliers(df_filled, columns=['close', 'volume'])

# 标准化
df_normalized = DataNormalizer.standardize(df_clean, columns=['close'], method='zscore')
```

#### 2.2 数据验证

```python
from data.processors.validator import DataValidator

# 检查必需列
passed, missing = DataValidator.check_required_columns(df, ['date', 'open', 'close'])

# 检查缺失值
missing_stats = DataValidator.check_missing_values(df, threshold=0.5)

# 检查价格合理性
price_check = DataValidator.check_price_validity(df)

# 生成完整报告
report = DataValidator.generate_report(df)
print(report)
```

### 3. 因子计算模块

#### 3.1 获取因子表达式

```python
from factors.alpha_factors import AlphaFactors

# 获取所有因子
all_features = AlphaFactors.get_all_features()
print(f"总因子数: {len(all_features)}")

# 获取特定类别因子
price_features = AlphaFactors.get_price_features()      # 价格类因子
volume_features = AlphaFactors.get_volume_features()    # 成交量因子
vol_features = AlphaFactors.get_volatility_features()   # 波动率因子
tech_features = AlphaFactors.get_technical_indicators() # 技术指标
```

#### 3.2 在 Qlib 中使用因子

```python
import qlib
from qlib.data import D
from qlib.constant import REG_CN

# 初始化
qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

# 使用自定义因子
from factors.alpha_factors import AlphaFactors

instruments = ['SH600000', 'SH600016']
fields = AlphaFactors.get_price_features()[:5]  # 使用前5个价格因子

df = D.features(
    instruments=instruments,
    fields=fields,
    start_time='2020-01-01',
    end_time='2020-12-31',
    freq='day'
)
print(df.head())
```

### 4. 自定义 Handler

#### 4.1 使用 SimpleAlphaHandler（精简版）

```python
import qlib
from qlib.constant import REG_CN
from handlers.custom_handler import SimpleAlphaHandler

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

handler = SimpleAlphaHandler(
    instruments="csi300",
    start_time="2020-01-01",
    end_time="2020-12-31",
    fit_start_time="2020-01-01",
    fit_end_time="2020-06-30"
)

# 获取特征
feature_df = handler.fetch(col_set="feature")
print(f"特征数量: {feature_df.shape[1]}")
```

#### 4.2 使用 CustomAlphaHandler（完整版）

```python
from handlers.custom_handler import CustomAlphaHandler

handler = CustomAlphaHandler(
    instruments="csi300",
    start_time="2020-01-01",
    end_time="2020-12-31",
    fit_start_time="2020-01-01",
    fit_end_time="2020-06-30"
)

# 获取所有因子（Alpha158 + 自定义因子）
all_features = handler.fetch(col_set="feature")
print(f"总特征数: {all_features.shape[1]}")
```

## 📊 因子说明

### 价格类因子（16个）
- 收益率：1日、5日、10日、20日收益率
- 均线偏离度：5/10/20/60日均线偏离
- 均线交叉：5/20、10/30均线比
- 价格Z-score：20日、60日标准化价格
- 日内特征：振幅、日内收益、相对位置等

### 成交量因子（9个）
- 量比：5/10/20日量比
- 量变化：量变化率、对数量比
- 量动量：短期/长期量比、变异系数
- 量集中度：5/20日量集中度

### 波动率因子（8个）
- 历史波动率：5/10/20/60日波动率
- 振幅标准差：5/20日振幅波动
- 价格区间：20日最高最低价差
- ATR：平均真实波幅

### 技术指标（7个）
- MACD系列：MACD、信号线
- RSI：相对强弱指标
- 布林带：位置、宽度
- 威廉指标：%R

### 相关性因子（5个）
- 价量相关：5/10/20日价量相关性
- 自相关：价格自相关
- 高低价相关：高低价相关性

### 形态因子（6个）
- 趋势强度
- 新高新低
- 跳空缺口
- 上下影线比例

**总计：51个自定义因子 + Alpha158 = 200+因子**

## 🔧 配置工作流

在 `configs/workflow_config_custom.yaml` 中使用自定义Handler：

```yaml
task:
    dataset:
        class: DatasetH
        module_path: qlib.data.dataset
        kwargs:
            handler:
                class: CustomAlphaHandler
                module_path: handlers.custom_handler
                kwargs:
                    start_time: 2008-01-01
                    end_time: 2020-08-01
                    fit_start_time: 2008-01-01
                    fit_end_time: 2014-12-31
                    instruments: csi300
            segments:
                train: [2008-01-01, 2014-12-31]
                valid: [2015-01-01, 2016-12-31]
                test: [2017-01-01, 2020-08-01]
```

## 📝 注意事项

1. **Tushare Token**：需要注册 Tushare 并获取 token
2. **数据格式**：标准格式为 `date, instrument, open, close, high, low, volume, factor`
3. **复权处理**：默认使用前复权，可在 `normalizer.py` 中切换
4. **因子计算**：所有因子基于 Qlib 表达式，自动处理缺失值
5. **性能优化**：大量因子会增加计算时间，可使用 SimpleAlphaHandler 快速实验

## 🎯 下一步

1. 运行 `examples/data_collection_example.py` 下载数据
2. 运行 `examples/custom_handler_example.py` 测试Handler
3. 修改 `run_workflow.py` 使用自定义Handler
4. 根据回测结果优化因子组合

## 📚 参考资料

- [Qlib 官方文档](https://qlib.readthedocs.io/)
- [Qlib GitHub](https://github.com/microsoft/qlib)
- [Tushare 文档](https://tushare.pro/document/2)
