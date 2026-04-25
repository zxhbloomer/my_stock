# BBI 全市场 Backtrader 回测系统 — 设计文档

## 目标

对 A 股全市场（过滤后约 4000-5000 只）进行 BBI 金叉/死叉信号回测，输出：
1. 每只股票的独立统计（胜率、年化收益、最大回撤等）
2. 交互式 HTML 报告（排行榜 + K 线图 + 逐笔交易明细）

---

## 文件结构

```
scripts/bbi/backtrader/
├── config.py                  # 全局参数配置
├── 10_prepare_data.py         # 数据准备：从 PostgreSQL 提取并保存 parquet
├── 20_run_backtest.py         # 回测执行：并行 Backtrader，输出 CSV
├── 30_generate_report.py      # 报告生成：两个 HTML
└── output/                    # 所有输出文件（重复运行覆盖）
    ├── stock_data/            # 每只股票的 parquet 文件（10_ 生成）
    ├── trades_detail.csv      # 所有逐笔交易记录（20_ 生成）
    ├── stats_summary.csv      # 每只股票汇总统计（20_ 生成）
    ├── report_ranking.html    # 类一：全市场排行榜（30_ 生成）
    └── report_detail.html     # 类二：K线+交易明细（30_ 生成）
```

---

## 模块设计

### config.py

```python
# 回测时间范围
START_DATE = "2018-01-01"
END_DATE   = None  # None = 今天

# 股票过滤条件
FILTER_MIN_LIST_DAYS  = 365        # 上市天数
FILTER_MIN_CIRC_MV    = 1_000_000 # 流通市值（万元）= 100亿元，约1767只
FILTER_MIN_AMOUNT     = 50_000    # 日均成交额（千元）= 5000万元

# 交易成本（A股标准）
COMMISSION_BUY        = 0.0005    # 开仓 0.05%
COMMISSION_SELL       = 0.0015    # 平仓 0.15%（含印花税）
MIN_COMMISSION        = 5.0       # 最低 5 元

# 初始资金（每只股票独立）
INIT_CASH             = 100_000.0

# 并行进程数
N_WORKERS             = 8

# 数据库
DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

# 输出目录
OUTPUT_DIR = Path(__file__).parent / "output"
```

---

### 10_prepare_data.py — 数据准备

**职责**：从 PostgreSQL 提取数据，保存为 parquet，供回测使用。支持重复运行（覆盖）。

**步骤**：

1. 从 `001_stock_basic` 获取股票列表，应用过滤条件：
   - `list_status IN ('L', 'D')`
   - `ts_code NOT LIKE '8%'`（排除北交所）
   - `name NOT LIKE '%ST%'`（排除 ST）
   - `DATEDIFF(today, list_date) >= 365`

2. 从 `027_daily_basic` 计算 `START_DATE` 前252个交易日的均值（避免 look-ahead bias），过滤：
   - `avg(amount) >= 50000`（5000万元，单位千元）
   - `avg(circ_mv) >= 1000000`（100亿元，单位万元，约1767只）

3. 从 `063_stk_factor_pro` 提取每只股票的日线数据：
   - 字段：`trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol, bbi_qfq`
   - 时间范围：`START_DATE` 到 `END_DATE`

4. 保存：
   - `output/stock_list.csv`：过滤后的股票列表（ts_code, name, list_date）
   - `output/stock_data/{ts_code}.parquet`：每只股票的 OHLCV + BBI 数据

**幂等性**：先清空 `output/stock_data/`，再重新生成。

---

### 20_run_backtest.py — 回测执行

**职责**：读取 parquet，对每只股票独立跑 Backtrader，汇总结果。支持重复运行（覆盖）。

#### BBIStrategy（Backtrader Strategy）

```python
class BBIStrategy(bt.Strategy):
    def __init__(self):
        self.bbi   = self.data.bbi    # 直接读取 bbi_qfq 列
        self.close = self.data.close  # close_qfq

    def next(self):
        if not self.position:
            # 金叉：前一天 close < bbi，今天 close > bbi
            if self.close[-1] < self.bbi[-1] and self.close[0] > self.bbi[0]:
                self.buy()
        else:
            # 死叉：前一天 close > bbi，今天 close < bbi
            if self.close[-1] > self.bbi[-1] and self.close[0] < self.bbi[0]:
                self.close_position()
```

成交价：次日开盘价（`cheat_on_open=True`，避免未来数据）。

#### 自定义 PandasData Feed

```python
class BBIData(bt.feeds.PandasData):
    lines = ('bbi',)
    params = (('bbi', -1),)  # 映射 bbi_qfq 列
```

#### Analyzer 配置

每只股票的 Cerebro 添加：
- `bt.analyzers.TradeAnalyzer`：交易次数、胜率、盈亏比、平均持仓天数
- `bt.analyzers.Returns`：年化收益（`tann=252`）
- `bt.analyzers.DrawDown`：最大回撤

#### 并行执行

```python
with multiprocessing.Pool(N_WORKERS) as pool:
    results = pool.map(run_single_stock, stock_list)
```

每个 worker 返回：
- `stats`：汇总统计 dict（一行）
- `trades`：逐笔交易 list（多行）

#### 输出

- `output/stats_summary.csv`：每只股票一行

| ts_code | name | 交易次数 | 胜率 | 平均收益% | 盈亏比 | 年化收益% | 最大回撤% | 年化/回撤比 | 平均持仓天数 |

- `output/trades_detail.csv`：所有逐笔交易

| ts_code | name | buy_date | buy_price | sell_date | sell_price | return_pct | hold_days | pnl |

**幂等性**：直接覆盖写，不追加。

---

### 30_generate_report.py — 报告生成

**职责**：读取 CSV，生成两个独立 HTML。支持重复运行（覆盖）。

#### report_ranking.html — 类一：全市场排行榜

单页 HTML，嵌入 `stats_summary.csv` 数据。

布局：
- 顶部：全局统计（总股票数、平均胜率、平均年化收益）
- 主体：可排序表格（按年化/回撤比默认降序）
  - 列：排名、代码、名称、交易次数、胜率、平均收益、盈亏比、年化收益、最大回撤、年化/回撤比
  - 支持列头点击排序、搜索框过滤
- 底部：胜率分布直方图（ECharts bar）

#### report_detail.html — 类二：K线+交易明细

单页 HTML，嵌入 `stats_summary.csv` + `trades_detail.csv` + OHLCV+BBI 数据（从 parquet 读取后嵌入 JSON）。

布局（三栏）：

```
┌──────────────────────────────────────────────────────────┐
│  Header: BBI回测分析 | 总股票数 | 时间范围 | 搜索框       │
├──────────────┬───────────────────────────────────────────┤
│  左栏 1/3    │  右栏 2/3                                  │
│              │  ┌─ 股票名称/代码 + 统计卡片 ─────────────┐│
│  股票列表    │  │  交易次数 | 胜率 | 年化收益 | 最大回撤  ││
│  （可搜索）  │  ├───────────────────────────────────────┤│
│              │  │  上：K线图（60% 高度）                 ││
│  每行显示：  │  │  - 日线 OHLC（ECharts candlestick）   ││
│  名称/代码   │  │  - BBI 均线（折线叠加）                ││
│  年化收益    │  │  - 买入点▲（红色）卖出点▼（绿色）     ││
│  胜率        │  │  - dataZoom 可拖动缩放                 ││
│  最大回撤    │  ├───────────────────────────────────────┤│
│              │  │  下：逐笔交易明细表（40% 高度）        ││
│  支持排序：  │  │  买入日期/价格 卖出日期/价格           ││
│  年化收益    │  │  收益率 持仓天数 盈亏金额              ││
│  胜率        │  │  点击行 → K线图定位到该笔交易区间      ││
│  回撤比      │  └───────────────────────────────────────┘│
└──────────────┴───────────────────────────────────────────┘
```

交互：
- 点击左栏股票 → 右栏更新（统计卡片 + K线图 + 交易明细）
- 点击交易明细某行 → K线图 dataZoom 定位到该笔交易时间区间并高亮
- K线图默认显示全部历史，dataZoom 初始显示最近 2 年

---

## 数据流

```
PostgreSQL
  001_stock_basic  ──┐
  027_daily_basic  ──┼──→ 10_prepare_data.py ──→ output/stock_data/*.parquet
  063_stk_factor_pro─┘                            output/stock_list.csv

output/stock_data/*.parquet ──→ 20_run_backtest.py ──→ output/trades_detail.csv
                                                         output/stats_summary.csv

output/trades_detail.csv ──┐
output/stats_summary.csv ──┼──→ 30_generate_report.py ──→ output/report_ranking.html
output/stock_data/*.parquet┘                               output/report_detail.html
```

---

## 过滤条件汇总

| 条件 | 来源表 | 实现方式 |
|------|--------|---------|
| 排除北交所 | 001_stock_basic | `ts_code NOT LIKE '8%'` |
| 排除 ST | 001_stock_basic | `name NOT LIKE '%ST%'` |
| 上市天数 ≥ 365 | 001_stock_basic | `list_date <= START_DATE - 365天` |
| 流通市值 ≥ 100亿 | 027_daily_basic | START_DATE前252日均值 `avg(circ_mv) >= 1000000`（万元） |
| 日均成交额 ≥ 5000万 | 027_daily_basic | START_DATE前252日均值 `avg(amount) >= 50000`（千元） |

---

## 交易成本

| 项目 | 值 |
|------|-----|
| 开仓手续费 | 0.05% |
| 平仓手续费 | 0.15%（含印花税 0.1%） |
| 最低手续费 | 5 元 |
| 成交价 | 次日开盘价（cheat_on_open） |

---

## 重复运行保证

- `10_prepare_data.py`：清空 `output/stock_data/` 后重新生成
- `20_run_backtest.py`：直接覆盖 `trades_detail.csv` 和 `stats_summary.csv`
- `30_generate_report.py`：直接覆盖两个 HTML 文件
- 三个脚本均可独立重复运行，互不干扰
