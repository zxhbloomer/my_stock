# 📊 Qlib图表中文化指南

## 问题分析

### ❌ Qlib官方图表的限制

Qlib使用**Plotly**生成交互式图表，但存在以下问题:

1. **硬编码英文标题**: 所有图表标题都是英文，如 "Score IC", "Cumulative Return"
2. **无国际化接口**: Qlib没有提供i18n(国际化)配置选项
3. **源码修改风险**: 直接修改源码会在升级时丢失

### ✅ 解决方案

我们提供了**自定义中文图表模块** `chinese_charts.py`，保持与Qlib官方函数相同的功能，但提供完整中文界面。

---

## 使用方法

### 方案1: 使用自定义中文图表 (推荐) ✅

在Jupyter Notebook中使用中文版图表函数:

```python
import qlib
import pandas as pd
from pathlib import Path
import yaml
from qlib.workflow import R

# 导入中文图表模块
from chinese_charts import (
    score_ic_graph_cn,
    model_performance_graph_cn,
    report_graph_cn,
    risk_analysis_graph_cn
)

# 初始化Qlib
mlflow_path = Path("../mlruns").resolve()
mlflow_uri = "file:///" + str(mlflow_path).replace("\\", "/")

qlib.init(
    provider_uri="~/.qlib/qlib_data/cn_data",
    region="cn",
    exp_manager={
        "class": "MLflowExpManager",
        "module_path": "qlib.workflow.expm",
        "kwargs": {
            "uri": mlflow_uri,
            "default_exp_name": "Experiment",
        },
    }
)

# 加载回测数据 (与原来相同)
recorder = R.get_recorder(recorder_id="your_recorder_id", experiment_name="backtest_analysis")
pred_df = recorder.load_object("pred.pkl")
label_df = recorder.load_object("label.pkl")
report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

# 使用中文图表函数
pred_label = pd.concat([label_df, pred_df], axis=1, sort=True).reindex(label_df.index)
if isinstance(pred_label.columns, pd.MultiIndex):
    pred_label.columns = ['label', 'score']
else:
    pred_label.columns = ['label', 'score']

# 1. IC分数分析图 (中文版)
score_ic_graph_cn(pred_label)

# 2. 模型性能分析图 (中文版)
model_performance_graph_cn(pred_label)

# 3. 投资组合报告图 (中文版)
report_graph_cn(report_df)

# 4. 风险分析图 (中文版)
risk_analysis_graph_cn(analysis_df, report_df)
```

### 方案2: 修改原Notebook使用中文图表

创建新的Notebook文件 `backtest_analysis_cn.ipynb`:

```python
# Cell 1: 导入库和初始化 (与原来相同)
import qlib
import pandas as pd
from pathlib import Path
import yaml
from qlib.workflow import R

# 导入中文图表模块 (新增)
from chinese_charts import (
    score_ic_graph_cn,
    model_performance_graph_cn,
    report_graph_cn,
    risk_analysis_graph_cn
)

# ... 初始化和加载数据代码 ...

# Cell 9: IC分数分析图 (使用中文版)
score_ic_graph_cn(pred_label)

# Cell 11: 模型性能分析图 (使用中文版)
model_performance_graph_cn(pred_label)

# Cell 13: 投资组合报告图 (使用中文版)
report_graph_cn(report_df)

# Cell 15: 风险分析图 (使用中文版)
risk_analysis_graph_cn(analysis_df, report_df)
```

---

## 中文图表对照表

| 原始函数 | 中文版函数 | 主要改进 |
|---------|-----------|---------|
| `analysis_position.score_ic_graph()` | `score_ic_graph_cn()` | 标题、轴标签、图例全部中文 |
| `analysis_model.model_performance_graph()` | `model_performance_graph_cn()` | 子图标题、分组名称中文 |
| `analysis_position.report_graph()` | `report_graph_cn()` | 指标名称、图例中文 |
| `analysis_position.risk_analysis_graph()` | `risk_analysis_graph_cn()` | 风险指标名称中文 |

---

## 中文化效果对比

### 原始英文版
```
Title: "Score IC"
X-axis: "datetime"
Y-axis: "IC"
Legend: "ic", "rank_ic"
```

### 中文版
```
Title: "预测分数IC分析 (Information Coefficient)"
X-axis: "日期"
Y-axis: "IC值"
Legend: "IC (皮尔逊相关)", "Rank IC (斯皮尔曼相关)"
```

---

## 技术细节

### 中文字体配置

所有图表都配置了中文字体支持:

```python
layout=dict(
    font=dict(family="Microsoft YaHei, SimHei, Arial", size=12),
    # 微软雅黑 → 黑体 → Arial (降级顺序)
)
```

### 保持Qlib原始功能

中文图表模块**完全兼容**Qlib原始数据处理逻辑:

1. ✅ 使用相同的数据计算方法
2. ✅ 保持相同的图表布局结构
3. ✅ 支持所有原始参数传递
4. ✅ 交互功能完全一致

### 扩展性

如果需要自定义更多图表，可以参考 `chinese_charts.py` 的实现模式:

```python
def your_custom_graph_cn(data: pd.DataFrame, show_notebook: bool = True, **kwargs):
    """
    自定义中文图表
    """
    fig = go.Figure(...)

    fig.update_layout(
        title="您的图表标题",
        font=dict(family="Microsoft YaHei, SimHei, Arial", size=12),
        # 其他中文配置
    )

    if show_notebook:
        BaseGraph.show_graph_in_notebook([fig])
    else:
        return (fig,)
```

---

## 常见问题

### Q1: 为什么不直接修改Qlib源码?

**A**: 修改源码有以下问题:
- 升级Qlib时会丢失修改
- 影响其他项目使用Qlib
- 不符合软件工程最佳实践

### Q2: 中文图表性能如何?

**A**: 性能完全相同，因为:
- 使用相同的Plotly渲染引擎
- 数据处理逻辑未改变
- 仅替换文本字符串

### Q3: 如何切换回英文?

**A**: 只需改回原始函数:

```python
# 中文版
from chinese_charts import score_ic_graph_cn
score_ic_graph_cn(pred_label)

# 英文版
from qlib.contrib.report import analysis_position
analysis_position.score_ic_graph(pred_label)
```

### Q4: 支持其他语言吗?

**A**: 可以基于 `chinese_charts.py` 创建其他语言版本:
- 复制文件并重命名 (如 `japanese_charts.py`)
- 替换所有中文字符串为目标语言
- 调整字体配置

---

## 文件清单

```
my_stock/
├── chinese_charts.py           # 中文图表模块 (新增)
├── notebooks/
│   ├── backtest_analysis.ipynb        # 原始英文版
│   └── backtest_analysis_cn.ipynb     # 中文版 (可选创建)
└── docs/
    └── Qlib图表中文化指南.md   # 本文档
```

---

## 总结

✅ **推荐使用自定义中文图表模块**
- 不影响Qlib原始代码
- 完全兼容现有工作流
- 易于维护和扩展
- 支持中英文灵活切换

❌ **不推荐直接修改Qlib源码**
- 升级时会丢失修改
- 影响其他项目
- 维护困难

---

**下一步**: 在Jupyter Notebook中运行 `from chinese_charts import *` 即可使用中文图表！
