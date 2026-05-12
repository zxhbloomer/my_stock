# v4_plan BBI 择时组合策略设计文档

**Goal:** 将 v4_plan 从"周度轮动"改造为"BBI 择时组合"，核心逻辑与 v3 完全一致，扩展为同时管理 5-10 只股票的组合版本。

**Architecture:** 每日收盘后扫描全市场，发现 BBI 金叉则次日开盘建仓；持仓期间逐日检查加仓/止损条件；死叉或止损触发则次日开盘清仓。资金回池后按当前总资产动态分配槽位，实现复利。

**Tech Stack:** Python, pandas, SQLAlchemy, PostgreSQL (tushare_v2)

---

## 1. 策略框架

### 1.1 运行频率

每个交易日收盘后运行一次，产生次日的买入/加仓/卖出指令列表，次日开盘价执行。

### 1.2 数据来源

复用 v4_plan_1 的 parquet 数据（已含 BBI、ATR14、MACD、MACD_Signal、winner_rate）。
不需要重新准备数据，直接读取 `v4_plan_1/output/stock_data/*.parquet`。

---

## 2. 仓位管理

### 2.1 最大槽位数

`total_assets = cash + sum(持仓市值)`，每日开盘前重新计算。

```
max_slots = min(10, max(5, int(total_assets / 100_000)))
```

| 总资产 | 最大槽位 |
|--------|---------|
| 50万   | 5       |
| 80万   | 8       |
| ≥100万 | 10      |

槽位数每次建仓前实时计算，持仓盈利导致总资产增加时可自动解锁新槽位。

### 2.2 建仓金额（滚动式）

```
empty_slots = max_slots - len(holdings)
alloc = available_cash / empty_slots   # 每次建仓后 available_cash 实时更新
```

同一天有多只股票建仓时，按顺序依次扣减现金（滚动式），后买入的股票分配金额略小。
`empty_slots <= 0` 则不建仓。建仓时将 `alloc` 存入持仓记录（`entry_alloc`），作为后续加仓的基准。

### 2.3 加仓金额（金字塔递减，以 entry_alloc 为基准）

- 第1次加仓：`entry_alloc × 50%`
- 第2次加仓：`entry_alloc × 25%`
- 加仓不占槽位，用可用现金支付，现金不足则跳过
- `entry_alloc` 在建仓时快照，后续加仓始终以此为基准，不随市场变化

### 2.4 复利机制

清仓后资金回到现金池，下次建仓时按新的 `available_cash / empty_slots` 重新计算，自动复利。

---

## 3. 买入条件（与 v3 完全一致）

同时满足以下三个条件，次日开盘买入：

1. **BBI 金叉**：`close[-1] < BBI[-1]` 且 `close[0] > BBI[0]`
2. **BBI 向上**：`BBI[0] > BBI[-3]`（3日斜率为正）
3. **MACD 确认**：`MACD[0] > signal[0]` 或 `MACD[0] > 0`

额外过滤：
- 次日开盘为一字涨停板（`abs(open - close) < close×0.001` 且 `(close - prev_close)/prev_close ≥ 9.5%`）→ 跳过，不买入
- 当前持仓数 ≥ max_slots → 跳过

当同一天有多只股票同时金叉，按 **5日涨幅**（`(close[0] - close[-5]) / close[-5]`，不含当日）降序排列，优先买入动量最强的，直到槽位满。

---

## 4. 加仓条件（与 v3 完全一致，扩展为2次）

对每只已持仓股票，每日收盘后检查，次日开盘执行：

**第1次加仓**（`add_count == 0`）：
- `(close - cost_price) / cost_price ≥ 0.03` 且 `MACD[0] > 0`
- 加仓量 = `entry_alloc × 50%`，次日开盘执行
- 加仓成交后记录 `add1_close = 当日收盘价`，用于第2次加仓触发基准

**第2次加仓**（`add_count == 1`）：
- `close ≥ add1_close + 1 × ATR14` 且 `MACD[0] > 0`
- 加仓量 = `entry_alloc × 25%`，次日开盘执行

**加仓遇涨停板**：次日开盘为一字涨停板时跳过，不加仓（同建仓规则）。

**加仓后止损线更新**：
```
trail_stop = max(trail_stop, new_avg_cost)
```
取 ATR 追踪止损线和新加权平均成本价的较高值，既保留 ATR 追踪优势，又增加保本保护。

---

## 5. 卖出条件（与 v3 完全一致）

每日收盘后检查，次日开盘执行：

| 条件 | 触发规则 | 持仓天数限制 |
|------|---------|------------|
| 硬止损 | `(close - cost) / cost <= -0.08` | 无限制，立即触发 |
| ATR 追踪止损 | `close < peak_close - 4.5 × ATR14` | 无限制 |
| BBI 死叉 | `close[-1] > BBI[-1]` 且 `close[0] < BBI[0]` | ≥ 20 天 |
| MACD 死叉 | `MACD < signal` 且 `MACD < 0` 且 `BBI[0] < BBI[-3]` | ≥ 20 天 |
| 筹码胜率过高 | `winner_rate > 80`（T-1数据） | ≥ 20 天 |

卖出时：
- 一字跌停板（`abs(open - close) < close×0.001` 且 `(close - prev_close)/prev_close ≤ -9.5%`）→ 按跌停价（收盘价）成交
- 连续跌停无法成交时：持续记录为"待卖出"，每日尝试，直到非跌停日成交

---

## 6. 文件结构

```
v4_plan/
├── config.py              # 修改：新增仓位参数，移除周度参数
├── 10_prepare_data.py     # 不改：复用 v4_plan_1 的 parquet 数据
├── 20_run_backtest.py     # 重写：BBI 择时组合逻辑
└── output/
    ├── nav_series.csv
    ├── trade_records.csv
    └── last_holdings.json
```

`10_prepare_data.py` 不需要修改，直接指向 `v4_plan_1/output/stock_data/`。

---

## 7. 关键参数

```python
INIT_CASH            = 500_000.0
SLOT_PER_100K        = 1          # 每10万对应1个槽位
MIN_SLOTS            = 5
MAX_SLOTS            = 10

ATR_PERIOD           = 14
ATR_MULTIPLIER       = 4.5
HARD_STOP_LOSS       = 0.08
CHIP_EXIT_THRESHOLD  = 80.0
MIN_HOLD_DAYS        = 20

PYRAMID_ADD_TRIGGER  = 0.03       # 浮盈3%触发第1次加仓
PYRAMID_ADD1_RATIO   = 0.50       # 第1次加仓 = 建仓额×50%
PYRAMID_ADD2_RATIO   = 0.25       # 第2次加仓 = 建仓额×25%

LIMIT_UP_THRESHOLD   = 0.095
LIMIT_DOWN_THRESHOLD = -0.095
```

---

## 8. 与 v3 的差异总结

| 维度 | v3 | 新 v4_plan |
|------|-----|-----------|
| 持仓数量 | 单股 | 5-10只组合 |
| 建仓金额 | 现金×50% | 现金/空余槽位 |
| 加仓次数 | 最多1次（用全部剩余现金） | 最多2次（递减50%/25%） |
| 买入信号冲突 | 无（单股） | 按5日涨幅排序，优先强势 |
| 复利 | 单股内复利 | 组合级复利（资金回池） |
| 买卖信号逻辑 | 完全相同 | 完全相同 |
