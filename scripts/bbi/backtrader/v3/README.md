# BBI 趋势跟踪策略 v3 — 单股逐一回测（筹码增强版）

## 策略精髓

**v3 在 v2 基础上新增筹码分布出场信号：当获利盘比例（winner_rate）过高时，主动离场规避抛压。**

核心问题意识：v2 的出场信号（BBI 死叉、MACD 死叉、ATR 止盈）都是价格滞后信号，往往在趋势已经反转后才触发。v3 引入 `cyq_perf.winner_rate` 作为前瞻性出场信号——获利盘过多意味着潜在抛压大，提前离场。

---

## v2 → v3 的核心变化

### 新增：筹码分布出场信号

| 维度 | v2 | v3 |
|------|----|----|
| 出场信号数量 | 3 种（BBI 死叉 / MACD 双死叉 / ATR 止盈） | **4 种**（新增筹码出场） |
| 筹码出场条件 | ❌ | ✅ `winner_rate > 80`（T-1 日数据） |
| 数据来源 | 仅价格数据 | 价格 + **筹码分布**（cyq_perf） |

```python
# 筹码出场逻辑
chip_exit = self.winner_line[0] > CHIP_EXIT_THRESHOLD  # winner_rate > 80
```

`winner_rate` 表示当前价格下处于盈利状态的持仓比例（Tushare 0-100 scale）。超过 80 意味着 80% 的持仓者已盈利，抛压风险极高。

### 参数调整（基于 v2 实验结果进一步优化）

| 参数 | v2.4 | v3 | 说明 |
|------|------|----|------|
| `ATR_MULTIPLIER` | 3.5 | **4.5** | 进一步加宽，给趋势更多空间 |
| `MIN_HOLD_DAYS` | 10 | **20** | 延长保护期，过滤更多短期噪声 |
| `CHIP_EXIT_THRESHOLD` | — | **80.0** | 新增筹码出场阈值 |

### 防未来数据泄露（v3 新增规范）

`winner_rate` 是盘后数据，在 `10_prepare_data.py` 中统一做 `shift(1)`：

```python
df['winner_rate'] = df['winner_rate'].shift(1)  # T 日决策只用 T-1 日筹码数据
```

---

## 数据来源

| 数据 | 来源表 | 说明 |
|------|--------|------|
| OHLCV + BBI + MA60 | `tushare_v2.063_stk_factor_pro` | 前复权价格 |
| 筹码分布 | `tushare_v2.061_cyq_perf` | `winner_rate`，**shift(1)** 防泄露（v3 新增） |

### 股票筛选（与 v2 相同）

| 条件 | 值 |
|------|----|
| 上市天数 | ≥ 365 天 |
| 流通市值 | ≥ 100 亿元 |
| 日均成交额 | ≥ 5000 万元 |
| 排除 | ST、退市、北交所 |

---

## 出场逻辑（完整四层）

| 层级 | 条件 | 说明 |
|------|------|------|
| 第一层（硬止损） | 亏损 ≥ 8% | 立即出场 |
| 第二层（持仓保护） | 入场后前 20 日 | 屏蔽软出场信号 |
| 第三层（软出场） | BBI 死叉 / MACD 双死叉 / ATR 移动止盈 | 满足任一即出场 |
| **第四层（筹码出场）** | **winner_rate > 80（T-1 日）** | **v3 新增，前瞻性离场** |

---

## 回测框架

与 v1/v2 相同，使用 **Backtrader** 框架，多进程逐股回测（`N_WORKERS=4`）。

输出文件：
- `output/stats_summary.csv` — 全市场统计汇总
- `output/trades_detail.csv` — 全部交易明细

---

## 关键参数

| 参数 | 值 |
|------|----|
| 初始资金 | 10 万元（每股独立） |
| `ATR_MULTIPLIER` | 4.5 |
| `MIN_HOLD_DAYS` | 20 |
| `HARD_STOP_LOSS` | 8% |
| `CHIP_EXIT_THRESHOLD` | 80.0 |

---

## 运行方式

```bash
cd scripts/bbi/backtrader/v3
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

---

## v3 的局限性

v3 在出场信号上做了前瞻性增强，但仍是**逐股独立回测**模式，无法解决 v2 的根本问题：
- 无法模拟真实组合操作
- 无选股排序机制
- 实盘参考性低

v4_plan 通过**周度轮动组合**模式彻底解决这些问题，同时大幅简化策略逻辑（去掉所有复杂出场条件，改为每周强制换仓）。
