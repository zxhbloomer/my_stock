# BBI v2 增强策略设计文档

**日期：** 2026-04-23  
**目标目录：** `scripts/bbi/backtrader/v2/`  
**对比基准：** v1 回测结果（`v1/output/stats_summary.csv`）

---

## 一、背景与目标

### v1 基准问题

v1 策略仅用"收盘价穿越 BBI"作为唯一信号，在 1709 只 A 股上的回测结果：

| 指标 | v1 基准 |
|------|---------|
| 平均胜率 | 28.68% |
| 平均年化收益 | 0.49% |
| 平均最大回撤 | 52.62% |
| 平均交易次数 | 128.9 次 |
| 平均持仓天数 | 4.8 天 |

核心问题：震荡市假穿越多，胜率极低，回撤大。

### v2 优化目标

| 指标 | 目标 |
|------|------|
| 平均胜率 | > 38% |
| 平均年化收益 | > 5% |
| 平均最大回撤 | < 40% |
| 平均交易次数 | < 80 次（减少假信号） |

---

## 二、策略设计

### 2.1 BBI 参数调整

**原参数：** MA(3) + MA(6) + MA(12) + MA(24)  
**新参数：** MA(5) + MA(10) + MA(20) + MA(60)

**理由：** 中期趋势跟踪路线，MA60 是 A 股最重要的中期均线，信号更稳定，假穿越更少。

`config.py` 新增：
```python
BBI_PERIODS = (5, 10, 20, 60)
```

`10_prepare_data.py` 中 BBI 计算改为读取 `BBI_PERIODS`，不再硬编码。

---

### 2.2 趋势过滤（入场条件强化）

在原有"收盘价上穿 BBI"基础上，增加两个过滤条件，**三个条件同时满足才入场**：

```
条件1：close[-1] < bbi[-1] AND close[0] > bbi[0]   # 收盘价上穿 BBI（原有）
条件2：bbi[0] > bbi[-3]                              # BBI 3日斜率 > 0（趋势向上）
条件3：close[0] > ma60[0]                            # 收盘价在 MA60 之上（中期多头）
```

**理由：**
- 条件2 过滤 BBI 横盘时的假穿越
- 条件3 过滤中期下跌趋势中的反弹假信号

---

### 2.3 MACD 动量确认（叠加指标）

**文献依据：** 浙江工商大学 2025 年论文（A股 2015-2025 回测）：MACD+RSI 组合年化收益显著优于单指标，在牛熊震荡三种市场均有效。ACM 2025 论文：BBI+MACD 等六指标共振策略胜率最高。

MACD 与 BBI 互补：BBI 判断价格位置，MACD 判断动量方向，两者均为趋势类指标，不相互矛盾。

**参数：** MACD(12, 26, 9)（标准参数）

**入场条件（四个同时满足）：**
```
条件1：close[-1] < bbi[-1] AND close[0] > bbi[0]   # 收盘价上穿 BBI
条件2：bbi[0] > bbi[-3]                              # BBI 3日斜率 > 0
条件3：close[0] > ma60[0]                            # 收盘价在 MA60 之上
条件4：macd[0] > signal[0] OR macd[0] > 0            # MACD 金叉或 MACD > 0
```

**出场条件（任一触发，T+1 保护）：**
```
条件A：close[-1] > bbi[-1] AND close[0] < bbi[0]   # 收盘价下穿 BBI（死叉）
条件B：macd[0] < signal[0] AND macd[0] < 0          # MACD 死叉且在零轴下方
```

**T+1 保护：** 买入当日不执行出场判断，次日起生效。

---

### 2.4 分批建仓（盈利加仓）

初始买入 50% 仓位，持仓盈利达到阈值后加仓剩余 50%。

```python
PYRAMID_FIRST_RATIO = 0.5   # 初始仓位：可用资金的 50%
PYRAMID_ADD_TRIGGER = 0.03  # 加仓触发：持仓盈利 >= 3%，且 MACD 仍 > 0
```

**状态机：**
```
状态 0（空仓）：
  → 触发入场条件 → 买入 50% → 进入状态 1

状态 1（半仓，等待加仓）：
  → 盈利 >= 5% → 加仓剩余 50% → 进入状态 2
  → 触发止损/死叉 → 全部平仓 → 回到状态 0

状态 2（满仓）：
  → 触发止损/死叉 → 全部平仓 → 回到状态 0
```

**仓位计算：**
- 初始买入：`size = int(cash * 0.5 / price / 100) * 100`
- 加仓：`size = int(remaining_cash / price / 100) * 100`

---

## 三、文件改动清单

| 文件 | 改动内容 |
|------|---------|
| `v2/config.py` | 新增 `BBI_PERIODS`, `MACD_FAST/SLOW/SIGNAL`, `PYRAMID_FIRST_RATIO`, `PYRAMID_ADD_TRIGGER` |
| `v2/10_prepare_data.py` | BBI 计算改用 `BBI_PERIODS`，重新生成 parquet |
| `v2/20_run_backtest.py` | 升级 `BBIStrategy` → `BBIEnhancedStrategy`，加入趋势过滤、MACD确认、分批建仓、T+1保护 |
| `v2/30_generate_report.py` | 不改动（复用 v1 报告逻辑） |

---

## 四、评估方法

### 4.1 运行步骤

```bash
cd scripts/bbi/backtrader/v2
python 10_prepare_data.py   # 重新生成含新 BBI 参数的 parquet
python 20_run_backtest.py   # 跑回测，输出到 v2/output/
python 30_generate_report.py  # 生成 HTML 报告
```

### 4.2 对比指标

运行后用以下脚本对比 v1 vs v2：

```python
import pandas as pd
v1 = pd.read_csv('v1/output/stats_summary.csv')
v2 = pd.read_csv('v2/output/stats_summary.csv')

metrics = ['win_rate', 'annual_return_pct', 'max_drawdown_pct',
           'trade_count', 'avg_hold_days', 'calmar_ratio']
for m in metrics:
    print(f"{m}: v1={v1[m].mean():.4f}  v2={v2[m].mean():.4f}")
```

### 4.3 分段验证

按市场环境分段检验策略稳健性：
- 2018：熊市
- 2019-2021：结构性牛市
- 2022-2024：震荡下行
- 2025-2026：政策驱动反弹

---

## 五、风险与注意事项

1. **T+1**：买入当日不执行止损，Backtrader 里需要记录买入日期
2. **ATR 动态更新**：每个 `next()` 都要重新计算 ATR，不能用入场时快照
3. **加仓订单管理**：用 `self.add_order` 跟踪加仓订单状态，避免重复下单
4. **MA60 预热期**：前 60 根 K 线无有效信号，Backtrader 的 `minperiod` 会自动处理
5. **parquet 重新生成**：BBI 参数变了，必须先跑 `10_prepare_data.py`

---

## 六、参数敏感性测试（后续）

v2 跑完后，对以下参数做敏感性分析，验证是否过拟合：

| 参数 | 测试范围 |
|------|---------|
| `ATR_MULTIPLIER` | 1.5, 2.0, 2.5, 3.0 |
| `PYRAMID_ADD_TRIGGER` | 3%, 5%, 8% |
| BBI 斜率窗口 | 3日, 5日 |
