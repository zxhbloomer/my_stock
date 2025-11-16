# MLflow UI 使用指南 - IC分析结果查看

## 启动MLflow UI

```bash
cd D:\2025_project\99_quantify\python\my_stock
mlflow ui
```

然后在浏览器访问：http://localhost:5000

---

## 📊 可以查看的内容

### 1. 实验列表页面

**位置**：首页 - Experiments

你会看到3个实验：
- `train_model` - 模型训练记录
- `backtest_analysis` - 回测分析记录
- `ic_analysis` - IC因子分析记录 ⭐

**点击 `ic_analysis` 进入详情**

---

### 2. IC分析运行记录

**位置**：ic_analysis 实验页面

显示所有IC分析的历史记录，每条记录包含：

#### 📈 关键指标（Metrics）
| 指标名称 | 含义 | 示例值 |
|---------|------|--------|
| `ic_mean_all` | 所有因子的IC均值 | -0.0076 |
| `ic_std_all` | 所有因子的IC标准差 | 0.1488 |
| `ir_mean_all` | 所有因子的IR均值 | -0.06 |
| `ic_mean_strong` | 强因子的IC均值 | -0.0095 |
| `ic_max_strong` | 强因子的最大IC | 0.0267 |
| `ic_min_strong` | 强因子的最小IC | -0.0337 |
| `strong_factors_count` | 强因子数量 | 8 |
| `total_factors_count` | 总因子数 | 10 |
| `retention_rate` | 强因子保留率 | 0.80 (80%) |

#### ⚙️ 参数（Parameters）
| 参数名称 | 含义 | 示例值 |
|---------|------|--------|
| `pool` | 股票池 | csi300 |
| `ic_threshold` | IC阈值 | 0.01 |
| `start_time` | 开始时间 | 2017-01-01 |
| `end_time` | 结束时间 | 2020-12-31 |
| `stock_count` | 股票数量 | 300 |

---

### 3. 📊 可视化图表（最重要！）

**位置**：点击某条记录 → Artifacts 标签

你会看到3个PNG图表：

#### 图表1：`ic_distribution.png` - IC分布直方图
**作用**：查看所有因子的IC分布情况

**解读要点**：
- 📊 横轴：IC值（-0.1 ~ 0.1）
- 📊 纵轴：因子数量
- 🔴 红色虚线：±0.01阈值线
- ✅ **理想状态**：分布偏向正值，说明因子整体有预测能力
- ⚠️ **警告信号**：集中在0附近，说明因子预测能力弱

**示例解读**：
```
如果看到：
- 大部分因子IC在[-0.02, 0.02]之间 → 因子预测能力一般
- 有明显的正偏 (右侧突起) → 好因子多
- 有明显的负偏 (左侧突起) → 可能需要反转信号
```

---

#### 图表2：`ic_timeseries_top5.png` - Top 5强因子IC时间序列
**作用**：查看最强的5个因子每天的IC变化

**解读要点**：
- 📈 每个子图显示1个因子的每日IC曲线
- 灰色虚线：0基准线
- ✅ **稳定因子**：IC围绕某个值波动，不跨越0线
- ⚠️ **不稳定因子**：IC频繁穿越0线，正负摇摆

**示例解读**：
```
因子A: IC均值=0.03，曲线稳定在0以上 → ✅ 优质因子
因子B: IC均值=0.02，但曲线频繁穿0 → ⚠️ 不稳定，慎用
因子C: IC均值=-0.03，曲线稳定在0以下 → 🔄 反转后可用
```

**实战用途**：
- 选因子时，优先选IC稳定且不穿0的
- IC频繁震荡的因子，即使均值高也要慎重

---

#### 图表3：`strong_factors_by_library.png` - 按因子库统计
**作用**：对比3个因子库的表现

**包含2个子图**：

##### 左图：强因子数量（柱状图）
- Alpha158：X个强因子
- AlphaFactors：Y个强因子
- ChinaMarketFactors：Z个强因子

**解读**：
- 📊 哪个库强因子多 → 该库质量高
- 示例：Alpha158有80个，AlphaFactors有15个 → Alpha158更优

##### 右图：强因子IC均值（柱状图）
- Alpha158：平均IC值
- AlphaFactors：平均IC值
- ChinaMarketFactors：平均IC值

**解读**：
- 📈 IC均值越高 → 该库因子预测能力越强
- 红色虚线：0.01阈值参考线

**实战决策**：
```
如果看到：
Alpha158: 80个因子，IC均值=0.025 → ✅ 主力因子库，重点使用
AlphaFactors: 15个因子，IC均值=0.035 → ⭐ 精品库，全部采用
ChinaMarketFactors: 5个因子，IC均值=0.015 → 补充使用
```

---

### 4. 📦 数据文件（Artifacts）

**位置**：Artifacts 标签

除了图表，还有2个数据文件：

#### `ic_analysis_full` (pickle)
完整的IC分析DataFrame，包含所有255个因子的：
- `factor_name`：因子名称
- `library`：所属因子库
- `ic_mean`：IC均值
- `ic_std`：IC标准差
- `ir`：信息比率
- `valid_days`：有效交易日数

**用途**：
```python
from qlib.workflow import R
recorder = R.get_recorder(recorder_id='your_id', experiment_name='ic_analysis')
ic_df = recorder.load_object('ic_analysis_full')

# 查找IC最高的10个因子
top10 = ic_df.nlargest(10, 'ic_mean')
```

#### `strong_factors_list` (pickle)
筛选后的强因子列表（|IC| > 0.01）

**用途**：
```python
strong_factors = recorder.load_object('strong_factors_list')
print(f"共有 {len(strong_factors)} 个强因子")
```

---

## 🎯 实战分析流程

### 第1步：看分布图（ic_distribution.png）
**目的**：整体评估因子质量

✅ **好的信号**：
- IC分布偏正（右偏）
- 超过50%因子|IC| > 0.01

⚠️ **警告信号**：
- IC集中在0附近
- 强因子占比 < 30%

---

### 第2步：看时间序列（ic_timeseries_top5.png）
**目的**：评估Top因子稳定性

✅ **优质因子特征**：
- IC曲线不穿越0线
- 波动幅度小（标准差小）
- 趋势一致（一直正或一直负）

⚠️ **问题因子特征**：
- IC频繁穿0（不稳定）
- 某段时间突然失效
- 波动过大（高风险）

---

### 第3步：看库统计（strong_factors_by_library.png）
**目的**：决定因子库使用策略

**决策矩阵**：
```
强因子多 + IC均值高 → 主力库，全量使用
强因子少 + IC均值高 → 精品库，精选使用
强因子多 + IC均值低 → 筛选使用，只用Top因子
强因子少 + IC均值低 → 放弃该库
```

---

### 第4步：下载数据深入分析
**操作**：点击 Artifacts → 下载 `ic_analysis_full`

**Python分析示例**：
```python
import pandas as pd
from qlib.workflow import R

# 加载最新结果
exp = R.get_exp(experiment_name='ic_analysis')
recorders = exp.list_recorders()
latest_id = recorders.iloc[0]['id']

recorder = R.get_recorder(recorder_id=latest_id, experiment_name='ic_analysis')
ic_df = recorder.load_object('ic_analysis_full')

# 分析1：找出最稳定的因子（IC高且标准差小）
ic_df['stability'] = ic_df['ic_mean'] / ic_df['ic_std']
stable_factors = ic_df.nlargest(20, 'stability')

# 分析2：找出正负IC因子分布
positive_ic = ic_df[ic_df['ic_mean'] > 0]
negative_ic = ic_df[ic_df['ic_mean'] < 0]
print(f"正IC因子: {len(positive_ic)}")
print(f"负IC因子: {len(negative_ic)}")

# 分析3：按库对比
library_stats = ic_df.groupby('library').agg({
    'ic_mean': ['mean', 'std', 'max', 'min'],
    'factor_name': 'count'
})
```

---

## 💡 关键指标解读

### IC值含义
| IC范围 | 质量评价 | 使用建议 |
|--------|----------|----------|
| > 0.05 | 极优 | 核心因子，必用 |
| 0.03 ~ 0.05 | 优秀 | 重点使用 |
| 0.01 ~ 0.03 | 良好 | 可选使用 |
| 0 ~ 0.01 | 一般 | 组合使用 |
| < 0 | 反向 | 反转信号或舍弃 |

### IR值含义（信息比率 = IC均值/IC标准差）
| IR范围 | 稳定性 | 使用建议 |
|--------|--------|----------|
| > 1.0 | 极稳定 | 首选因子 |
| 0.5 ~ 1.0 | 稳定 | 可靠因子 |
| 0.2 ~ 0.5 | 一般 | 谨慎使用 |
| < 0.2 | 不稳定 | 避免使用 |

### 保留率（Retention Rate）
| 保留率 | 因子库质量 |
|--------|-----------|
| > 80% | 优秀 |
| 60% ~ 80% | 良好 |
| 40% ~ 60% | 一般 |
| < 40% | 较差 |

---

## 🚀 下一步行动建议

查看完MLflow UI后，你可以：

1. **导出强因子列表**
   ```bash
   python scripts/21_use_ic_results.py
   ```

2. **使用Top因子重新训练模型**
   - 修改 `configs/workflow_config_*.yaml`
   - 只使用IC > 0.03的因子
   - 对比性能提升

3. **定期重新分析**
   - 每季度运行一次IC分析
   - 监控因子有效性衰减
   - 及时更新因子池

---

## 📝 常见问题

**Q1：为什么有些因子IC是负值？**
A：负IC说明因子与未来收益负相关，可以反转信号使用（乘以-1）

**Q2：IC多少算好？**
A：A股市场IC > 0.02就算不错，IC > 0.05属于优秀

**Q3：为什么IC时间序列波动大？**
A：市场风格轮动导致，应关注长期均值而非短期波动

**Q4：如何判断因子是否失效？**
A：连续3个月IC < 0.01，或IC由正转负持续1个月以上

---

**总结**：MLflow UI最重要的是看3张图，理解因子分布、稳定性和库对比，据此优化因子选择策略。
