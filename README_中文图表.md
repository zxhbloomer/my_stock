# 📊 Qlib中文图表使用指南

## ✅ 已完成内容

已成功创建Qlib中文图表模块，所有功能测试通过！

### 📁 文件清单

```
my_stock/
├── chinese_charts_simple.py          ✅ 中文图表模块 (推荐使用)
├── chinese_charts.py                 ⚠️ 完整版 (复杂，暂时有bug)
├── test_chinese_charts.py            ✅ 测试脚本
├── notebooks/
│   ├── backtest_analysis.ipynb       📝 原始英文版
│   └── backtest_analysis_cn.ipynb    ✅ 中文版 (新建)
└── docs/
    ├── Qlib图表中文化指南.md          📚 技术文档
    └── 查看图表指南.md                📚 查看指南
```

---

## 🚀 快速开始

### 方法1: 在Jupyter Notebook中使用 (推荐) ✅

```bash
# 1. 启动Jupyter
conda activate mystock
cd D:\2025_project\99_quantify\python\my_stock
jupyter notebook

# 2. 打开中文版Notebook
notebooks/backtest_analysis_cn.ipynb

# 3. 运行所有cells (Shift+Enter)
```

### 方法2: 在Python脚本中使用

```python
import qlib
import pandas as pd
from pathlib import Path
from qlib.workflow import R

# 导入中文图表模块
from chinese_charts_simple import (
    score_ic_graph_cn,
    model_performance_graph_cn,
    report_graph_cn,
    risk_analysis_graph_cn,
    show_all_charts_cn  # 一次性显示所有图表
)

# 初始化Qlib
mlflow_path = Path("mlruns").resolve()
mlflow_uri = "file:///" + str(mlflow_path).replace("\\", "/")

qlib.init(
    provider_uri="~/.qlib/qlib_data/cn_data",
    region="cn",
    exp_manager={
        "class": "MLflowExpManager",
        "module_path": "qlib.workflow.expm",
        "kwargs": {"uri": mlflow_uri, "default_exp_name": "Experiment"},
    }
)

# 加载回测数据
recorder = R.get_recorder(
    recorder_id="your_recorder_id",
    experiment_name="backtest_analysis"
)

pred_df = recorder.load_object("pred.pkl")
label_df = recorder.load_object("label.pkl")
report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

# 准备数据
pred_label = pd.concat([label_df, pred_df], axis=1).reindex(label_df.index)
pred_label.columns = ['label', 'score']

# 显示单个图表
score_ic_graph_cn(pred_label)              # IC分析
model_performance_graph_cn(pred_label)     # 模型性能
report_graph_cn(report_df)                 # 投资组合
risk_analysis_graph_cn(analysis_df, report_df)  # 风险分析

# 或一次性显示所有图表
show_all_charts_cn(pred_label, report_df, analysis_df)
```

---

## 📊 图表说明

### 1. IC分数分析图 (`score_ic_graph_cn`)

**中文说明**:
- IC (皮尔逊相关): 预测分数与真实收益的线性相关性
- Rank IC (斯皮尔曼相关): 预测排序与真实收益排序的相关性
- IC均值 > 0.01: 良好
- IC均值 > 0.03: 优秀

**我们的结果**: IC=0.052, Rank IC=0.055 (优秀！)

### 2. 模型性能分析图 (`model_performance_graph_cn`)

**中文说明**:
- Cumulative Return: 各预测分组的累积收益曲线
- long-short: Top组 - Bottom组的多空收益
- long-average: Top组 - 市场平均的超额收益

**策略应用**:
- 做多Top组 (买入预测分数最高的股票)
- 做空Bottom组 (卖出预测分数最低的股票)

### 3. 投资组合报告图 (`report_graph_cn`)

**中文说明**:
- return: 策略日收益
- bench: 基准(沪深300)日收益
- turnover: 日换手率 (交易比例)
- cost: 交易成本

**关键指标**:
- 年化收益: 11.18% (含成本)
- 相对基准: 有明显超额收益

### 4. 风险分析图 (`risk_analysis_graph_cn`)

**中文说明**:
- excess_return_without_cost: 超额收益 (不含交易成本)
- excess_return_with_cost: 超额收益 (含交易成本)
- annualized_return: 年化收益率
- information_ratio: 信息比率 (>1.0为优秀)
- max_drawdown: 最大回撤

**我们的结果**:
- 最大回撤: -8.83% (风险可控)
- 信息比率: 1.29 (优秀)

---

## 🔍 测试验证

运行测试脚本验证所有功能:

```bash
python test_chinese_charts.py
```

**预期输出**:

```
================================================================================
Qlib中文图表模块测试
================================================================================

[1/5] 初始化Qlib...
[OK] Qlib初始化成功

[2/5] 查找最新回测记录...
[OK] 找到回测记录: cfd957248e714461a81b66da80eab4f4

[3/5] 加载回测数据...
[OK] 数据加载成功
  - 预测记录: 261,207条
  - 交易日数: 871天

[4/5] 准备图表数据...
[OK] 数据准备完成

[5/5] 测试图表生成...
  - 测试 score_ic_graph_cn()... [OK]
  - 测试 model_performance_graph_cn()... [OK]
  - 测试 report_graph_cn()... [OK]
  - 测试 risk_analysis_graph_cn()... [OK]

================================================================================
[SUCCESS] 所有中文图表测试通过！
================================================================================
```

---

## 💡 使用提示

### ✅ 优点

1. **中文说明**: 每个图表显示前打印详细中文说明
2. **稳定可靠**: 直接调用Qlib官方函数，兼容性好
3. **保持功能**: 所有交互功能完全保留
4. **易于使用**: 导入即用，无需配置

### ⚠️ 注意事项

1. **图表标题**: Plotly图表内部标题仍为英文(Qlib官方默认)
2. **中文字体**: 在Jupyter中自动显示，无需特殊配置
3. **编码问题**: 如遇到GBK编码错误，使用Jupyter Notebook

### 🔄 中英文切换

```python
# 中文版
from chinese_charts_simple import score_ic_graph_cn
score_ic_graph_cn(pred_label)

# 英文版 (Qlib官方)
from qlib.contrib.report import analysis_position
analysis_position.score_ic_graph(pred_label)
```

---

## 📚 相关文档

- **技术详解**: `docs/Qlib图表中文化指南.md`
- **查看指南**: `docs/查看图表指南.md`
- **项目分析**: `docs/Qlib项目实现分析报告.md`

---

## 🎯 总结

✅ **已完成**:
1. 创建中文图表模块 (`chinese_charts_simple.py`)
2. 创建中文版Jupyter Notebook (`backtest_analysis_cn.ipynb`)
3. 编写测试脚本并验证通过
4. 编写完整使用文档

✅ **主要特点**:
- 🇨🇳 完整中文说明
- 🔧 调用官方函数，稳定可靠
- 📊 保持所有交互功能
- 📝 详细的使用指南

**推荐使用**: 在Jupyter Notebook中打开 `backtest_analysis_cn.ipynb` 运行所有cells！

---

**更新时间**: 2025-10-08
**测试状态**: ✅ 全部通过
**环境**: Windows 11 + Python 3.8 + Qlib 0.9.x
