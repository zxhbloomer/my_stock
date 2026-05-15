# v4 Weekly BBI DB Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tmp` 中验证使用数据库 `022_stk_week_month_adj` 周线复权行情计算周线 BBI，并用“连续 3 个已完成周跌破周线 BBI”作为强趋势股趋势止损。

**Architecture:** 不修改正式 `v4`。新增/改造 `tmp` 实验脚本，复用 v4 当前日线面板、买入、加仓、涨跌停成交和报表输出逻辑；周线 BBI 数据单独从 PostgreSQL 查询，按交易日只对齐已完成周线，避免未来函数。

**Tech Stack:** Python, pandas, SQLAlchemy, PostgreSQL, Tushare 本地表 `tushare_v2."022_stk_week_month_adj"`。

---

### Task 1: 周线 BBI 数据加载

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/v4_bull_hold_exit_experiment.py`

- [ ] **Step 1: 引入数据库配置和 SQLAlchemy**

从 `v4/config.py` 引入 `DB_URL`、`SCHEMA`，并新增 `sqlalchemy.create_engine`、`sqlalchemy.text`。

- [ ] **Step 2: 新增 `load_weekly_bbi_from_db`**

查询 `022_stk_week_month_adj`：

```sql
SELECT ts_code, trade_date, close_qfq
FROM tushare_v2."022_stk_week_month_adj"
WHERE freq = 'week'
  AND trade_date >= :start_date
  AND trade_date <= :end_date
  AND close_qfq IS NOT NULL
```

按 `ts_code, trade_date` 排序后计算：

```python
week_bbi_qfq = (MA3 + MA6 + MA12 + MA24) / 4
below_week_bbi = close_qfq < week_bbi_qfq
below_week_bbi_3w = below_week_bbi 连续 3 周为 True
```

- [ ] **Step 3: 对齐日线信号日期**

使用 `merge_asof` 把每个日线 `signal_date` 对齐到 `trade_date <= signal_date` 的最后一根已完成周线。禁止使用 `trade_date > signal_date` 的周线。

### Task 2: 新增实验模式

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/v4_bull_hold_exit_experiment.py`

- [ ] **Step 1: 增加模式**

新增模式：

```text
weekly_bbi_3w
```

- [ ] **Step 2: 卖出规则**

在 `resolve_bearish_volume_exit` 或风险退出判断中加入：

```text
强趋势股 + 盈利持仓遇到放量大阴线时，不直接卖出；
如果已完成周线连续 3 周 close_qfq < week_bbi_qfq，则下一交易日开盘卖出。
```

卖出原因：

```text
long_week_bbi_3w_exit
```

### Task 3: 输出和验证

**Files:**
- Modify: `scripts/bbi/backtrader/tmp/v4_bull_hold_exit_experiment.py`
- Modify: `scripts/bbi/backtrader/tmp/results.md`

- [ ] **Step 1: summary 增加统计**

增加：

```text
weekly_bbi_3w_exit_signals
weekly_bbi_3w_exit_fills
```

- [ ] **Step 2: 运行验证**

运行：

```powershell
C:\Users\Administrator\miniconda3\envs\mystock\python.exe scripts\bbi\backtrader\tmp\v4_bull_hold_exit_experiment.py --mode weekly_bbi_3w --start 2018-01-01 --end 2018-12-31
C:\Users\Administrator\miniconda3\envs\mystock\python.exe scripts\bbi\backtrader\tmp\v4_bull_hold_exit_experiment.py --mode weekly_bbi_3w --start 2025-01-01 --end 2025-12-31
```

- [ ] **Step 3: 对比 current**

用已有 `current` 或重跑同区间 `current`，对比收益、最大回撤、交易次数、牛股是否卖飞。

### QA Review Checklist

- [ ] 数据源必须是 `022_stk_week_month_adj`，不是日线聚合。
- [ ] 只使用 `trade_date <= signal_date` 的已完成周线。
- [ ] 周线 BBI 至少有 24 根周 K 后才有效。
- [ ] 跌停/停牌卖不出时沿用现有 pending sell。
- [ ] 不修改正式 `v4`。
