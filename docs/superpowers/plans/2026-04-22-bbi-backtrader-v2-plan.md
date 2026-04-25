# BBI Backtrader v2 优化计划

**日期：** 2026-04-22  
**代码目录：** `scripts/bbi/backtrader/v2/`  
**文档目录：** `docs/superpowers/`

---

## 背景

v1 回测结果（1708只股票）显示：
- 平均胜率 28.68%，平均年化 0.49%
- 平均持仓 4.8 天，大量信号穿越后立刻反转
- 交易次数 >150 的股票年化 -4.06%
- 当前策略只用"收盘价穿越 BBI"一个条件，无止损

---

## 需求清单（按优先级排序）

### REQ-01：止损机制（最高优先级）
**问题：** 当前只靠 BBI 死叉出场，无止损，回撤无上限  
**方案：** 在 `20_run_backtest.py` 的 `BBIStrategy.next()` 中加入止损逻辑  
- 固定止损：买入价 × (1 - STOP_LOSS_PCT)，默认 8%  
- ATR 动态止损：买入价 - STOP_LOSS_ATR_MULTIPLIER × ATR(14)  
- 通过 config 开关控制类型  
**新增统计字段：** `stop_loss_count`（止损触发次数）

---

### REQ-02：BBI 斜率过滤（高优先级）
**问题：** BBI 横盘时频繁穿越，大量假信号  
**方案：** 买入条件新增 `bbi[0] > bbi[-1]`（BBI 本身在上升）  
**改动：** `20_run_backtest.py` → `BBIStrategy.next()` 一行改动

---

### REQ-03：成交量确认（高优先级）
**问题：** 缩量穿越大概率是假突破  
**方案：** 买入条件新增：当日成交量 > N 日均量 × M 倍  
- 默认 N=20，M=1.5，参数写入 config  
**改动：** `20_run_backtest.py` → `BBIStrategy.__init__` 加 SMA(volume)

---

### REQ-04：MA60 大趋势过滤（高优先级）
**问题：** 熊市中个股反复被套  
**方案：** 买入条件新增：收盘价 > 个股自身 MA60  
**注意：** 用个股自身 MA60，不用大盘指数  
**改动：** `20_run_backtest.py` → `BBIStrategy.__init__` 加 SMA(close, 60)

---

### REQ-05：config.py 扩展
**方案：** 把所有新增参数集中到 `config.py`，方便后续参数扫描

新增参数：
```python
BBI_SLOPE_FILTER         = True
VOLUME_FILTER_ENABLED    = True
VOLUME_FILTER_PERIOD     = 20
VOLUME_FILTER_MULTIPLIER = 1.5
MA_TREND_FILTER_ENABLED  = True
MA_TREND_PERIOD          = 60
STOP_LOSS_ENABLED        = True
STOP_LOSS_TYPE           = "fixed"   # "fixed" or "atr"
STOP_LOSS_PCT            = 0.08
STOP_LOSS_ATR_PERIOD     = 14
STOP_LOSS_ATR_MULTIPLIER = 2.0
```

---

### REQ-06：stats_summary 新增字段
**方案：** `20_run_backtest.py` 输出新增 `stop_loss_count` 字段  
**目的：** 分析止损是否过于频繁，辅助参数调优

---

## 暂不做

| 方向 | 原因 |
|---|---|
| 加权 BBI | 更快响应 = 更多假信号，方向可能反了 |
| 分板块参数优化 | 过拟合风险大 |
| 选股过滤 | 属于 `10_prepare_data.py` 范畴，单独讨论 |

---

## 执行顺序

1. REQ-05 config 扩展（基础，其他依赖它）
2. REQ-01 止损机制
3. REQ-02 BBI 斜率过滤
4. REQ-03 成交量确认
5. REQ-04 MA60 趋势过滤
6. REQ-06 stats 字段

---

## 等待指令
