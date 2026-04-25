# BBI v2 Enhanced Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade BBI backtrader strategy from simple crossover to a 4-condition entry with MACD confirmation, MA60 trend filter, BBI slope filter, and 50%+50% scale-in position management.

**Architecture:** Three files change — `config.py` adds new parameters, `10_prepare_data.py` calculates BBI(5,10,20,60) in Python (DB column uses old formula), `20_run_backtest.py` replaces BBIStrategy with BBIEnhancedStrategy. `30_generate_report.py` is unchanged.

**Tech Stack:** Python, Backtrader, pandas, SQLAlchemy, PostgreSQL (tushare_v2 schema)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/bbi/backtrader/v2/config.py` | Modify | Add BBI_PERIODS, MACD params, pyramid params |
| `scripts/bbi/backtrader/v2/10_prepare_data.py` | Modify | Calculate BBI+MA60 in Python, save to parquet |
| `scripts/bbi/backtrader/v2/20_run_backtest.py` | Modify | BBIEnhancedStrategy with all v2 logic |

---

## Task 1: Update config.py

**Files:**
- Modify: `scripts/bbi/backtrader/v2/config.py`

- [ ] **Step 1: Add new parameters to config.py**

Replace the entire file with:

```python
from pathlib import Path

START_DATE = "2018-01-01"
END_DATE   = None  # None = today

FILTER_MIN_LIST_DAYS  = 365
FILTER_MIN_CIRC_MV    = 1_000_000  # 万元 = 100亿元
FILTER_MIN_AMOUNT     = 50_000     # 千元 = 5000万元

COMMISSION_BUY        = 0.0005
COMMISSION_SELL       = 0.0015
MIN_COMMISSION        = 5.0

INIT_CASH             = 100_000.0
N_WORKERS             = 8

DB_URL = "postgresql://root:123456@localhost:5432/my_stock"
SCHEMA = "tushare_v2"

# v2: BBI uses MA(5,10,20,60) instead of DB's MA(3,6,12,24)
BBI_PERIODS = (5, 10, 20, 60)

# v2: MACD momentum confirmation
MACD_FAST   = 12
MACD_SLOW   = 26
MACD_SIGNAL = 9

# v2: scale-in position management
PYRAMID_FIRST_RATIO  = 0.5   # initial buy: 50% of available cash
PYRAMID_ADD_TRIGGER  = 0.03  # add remaining 50% when profit >= 3%

OUTPUT_DIR     = Path(__file__).parent / "output"
STOCK_DATA_DIR = OUTPUT_DIR / "stock_data"
KLINE_DATA_DIR = OUTPUT_DIR / "kline_data"
```

- [ ] **Step 2: Verify config loads correctly**

```bash
cd D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2
python -c "from config import BBI_PERIODS, MACD_FAST, PYRAMID_FIRST_RATIO; print(BBI_PERIODS, MACD_FAST, PYRAMID_FIRST_RATIO)"
```

Expected output: `(5, 10, 20, 60) 12 0.5`

---

## Task 2: Update 10_prepare_data.py

**Files:**
- Modify: `scripts/bbi/backtrader/v2/10_prepare_data.py`

**Critical context:** The DB column `bbi_qfq` uses a slightly different formula than standard MA(3,6,12,24)/4. For v2 with new periods MA(5,10,20,60), BBI must be calculated in Python. We also need `ma60` as a separate column for the MA60 filter in the strategy.

- [ ] **Step 1: Update the SQL query to fetch OHLCV only (drop bbi_qfq)**

In `10_prepare_data.py`, change the SQL in Step 3 from:
```python
    sql_data = text("""
        SELECT trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol, bbi_qfq
        FROM tushare_v2."063_stk_factor_pro"
        ...
    """)
```

To:
```python
    sql_data = text("""
        SELECT trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol
        FROM tushare_v2."063_stk_factor_pro"
        WHERE ts_code = :ts_code
          AND trade_date >= CAST(:start_date AS date)
          AND trade_date <= CAST(:end_date AS date)
        ORDER BY trade_date
    """)
```

- [ ] **Step 2: Add BBI and MA60 calculation after fetching data**

Update the import at the top to include BBI_PERIODS:
```python
from config import (
    DB_URL, START_DATE, END_DATE,
    FILTER_MIN_CIRC_MV, FILTER_MIN_AMOUNT,
    STOCK_DATA_DIR, OUTPUT_DIR,
    BBI_PERIODS,
)
```

After `df = _query(conn, sql_data, {...})` and before `if len(df) < 60:`, add:
```python
            # Calculate BBI using v2 periods (MA5+MA10+MA20+MA60)/4
            for p in BBI_PERIODS:
                df[f'ma{p}'] = df['close_qfq'].rolling(p).mean()
            df['bbi_qfq'] = sum(df[f'ma{p}'] for p in BBI_PERIODS) / len(BBI_PERIODS)
            # ma60 kept as separate column for MA60 filter in strategy
            df = df.drop(columns=[f'ma{p}' for p in BBI_PERIODS if p != 60])
            df = df.dropna(subset=['bbi_qfq'])
```

- [ ] **Step 3: Verify parquet output has correct columns**

```bash
cd D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2
python -c "
import pandas as pd, glob
files = glob.glob('output/stock_data/*.parquet')
if files:
    df = pd.read_parquet(files[0])
    print(df.columns.tolist())
    print(df[['close_qfq','bbi_qfq','ma60']].tail(3))
else:
    print('No parquet files yet - run 10_prepare_data.py first')
"
```

Expected columns include: `trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol, bbi_qfq, ma60, name`

---

## Task 3: Upgrade 20_run_backtest.py

**Files:**
- Modify: `scripts/bbi/backtrader/v2/20_run_backtest.py`

**Key design decisions:**
- BBIData needs 3 new lines: `ma60`, `macd_line`, `signal_line`
- T+1 protection: track `self.buy_bar` (bar index at buy), skip exit on same bar
- Scale-in state machine: state 0=flat, 1=half position, 2=full position
- MACD computed via `bt.indicators.MACD` (returns DIF, DEA, histogram)
- MA60 computed via `bt.indicators.SMA(self.data.close, period=60)`

- [ ] **Step 1: Update imports in 20_run_backtest.py**

```python
import csv
import multiprocessing
import pandas as pd
import backtrader as bt
from config import (
    STOCK_DATA_DIR, OUTPUT_DIR, N_WORKERS, INIT_CASH,
    COMMISSION_BUY, COMMISSION_SELL, MIN_COMMISSION,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    PYRAMID_FIRST_RATIO, PYRAMID_ADD_TRIGGER,
)
```

- [ ] **Step 2: Update BBIData to add ma60 line**

```python
class BBIData(bt.feeds.PandasData):
    lines = ('bbi', 'ma60',)
    params = (
        ('datetime', None),
        ('open',         'open_qfq'),
        ('high',         'high_qfq'),
        ('low',          'low_qfq'),
        ('close',        'close_qfq'),
        ('volume',       'vol'),
        ('openinterest', -1),
        ('bbi',          'bbi_qfq'),
        ('ma60',         'ma60'),
    )
```

- [ ] **Step 3: Replace BBIStrategy with BBIEnhancedStrategy**

Remove the old `BBIStrategy` class entirely and replace with:

```python
class BBIEnhancedStrategy(bt.Strategy):
    def __init__(self):
        self.bbi    = self.data.bbi
        self.close  = self.data.close
        self.ma60   = self.data.ma60
        macd_ind    = bt.indicators.MACD(
            self.data.close,
            period_me1=MACD_FAST,
            period_me2=MACD_SLOW,
            period_signal=MACD_SIGNAL,
        )
        self.macd   = macd_ind.macd
        self.signal = macd_ind.signal

        self.state    = 0   # 0=flat, 1=half, 2=full
        self.buy_bar  = -1  # bar index when last buy executed
        self.add_order = None

    def _entry_signal(self):
        # All 4 conditions must be true
        cross_up  = self.close[-1] < self.bbi[-1] and self.close[0] > self.bbi[0]
        bbi_slope = self.bbi[0] > self.bbi[-3]
        above_ma60 = self.close[0] > self.ma60[0]
        macd_ok   = self.macd[0] > self.signal[0] or self.macd[0] > 0
        return cross_up and bbi_slope and above_ma60 and macd_ok

    def _exit_signal(self):
        # BBI death cross OR (MACD dead cross AND MACD below zero)
        cross_down = self.close[-1] > self.bbi[-1] and self.close[0] < self.bbi[0]
        macd_dead  = self.macd[0] < self.signal[0] and self.macd[0] < 0
        return cross_down or macd_dead

    def notify_order(self, order):
        if order.status in (order.Completed,):
            if order.isbuy():
                self.buy_bar = len(self)
            if self.add_order is not None and order.ref == self.add_order.ref:
                self.add_order = None
                self.state = 2

    def next(self):
        if self.state == 0:
            if self._entry_signal():
                cash = self.broker.getcash()
                size = int(cash * PYRAMID_FIRST_RATIO / self.close[0] / 100) * 100
                if size >= 100:
                    self.buy(size=size, exectype=bt.Order.Market)
                    self.state = 1

        elif self.state == 1:
            # T+1: skip exit on buy bar
            if len(self) > self.buy_bar:
                if self._exit_signal():
                    self.close()
                    self.state = 0
                    return
            # scale-in: profit >= threshold and MACD > 0
            pos = self.broker.getposition(self.data)
            if pos.size > 0:
                profit_pct = (self.close[0] - pos.price) / pos.price
                if profit_pct >= PYRAMID_ADD_TRIGGER and self.macd[0] > 0:
                    if self.add_order is None:
                        cash = self.broker.getcash()
                        size = int(cash / self.close[0] / 100) * 100
                        if size >= 100:
                            self.add_order = self.buy(size=size, exectype=bt.Order.Market)

        elif self.state == 2:
            if len(self) > self.buy_bar and self._exit_signal():
                self.close()
                self.state = 0
```

- [ ] **Step 4: Update cerebro.addstrategy call**

Change:
```python
        cerebro.addstrategy(BBIStrategy)
```
To:
```python
        cerebro.addstrategy(BBIEnhancedStrategy)
```

- [ ] **Step 5: Verify the file has no syntax errors**

```bash
cd D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2
python -c "import py_compile; py_compile.compile('20_run_backtest.py', doraise=True); print('OK')"
```

Expected: `OK`

---

## Task 4: Run Backtest and Compare

- [ ] **Step 1: Regenerate parquet data with new BBI formula**

```bash
cd D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2
python 10_prepare_data.py
```

Expected: prints stock count, exports parquet files to `output/stock_data/`

- [ ] **Step 2: Run v2 backtest**

```bash
cd D:\2026_project\10_quantify\00_py\my_stock\scripts\bbi\backtrader\v2
python 20_run_backtest.py
```

Expected: prints `Done. N stocks, M trades.`

- [ ] **Step 3: Compare v1 vs v2 results**

```python
import pandas as pd

v1 = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v1/output/stats_summary.csv')
v2 = pd.read_csv('D:/2026_project/10_quantify/00_py/my_stock/scripts/bbi/backtrader/v2/output/stats_summary.csv')

metrics = ['win_rate', 'annual_return_pct', 'max_drawdown_pct',
           'trade_count', 'avg_hold_days', 'calmar_ratio']
print(f"{'Metric':<25} {'v1':>10} {'v2':>10} {'Delta':>10}")
print("-" * 55)
for m in metrics:
    v1_val = v1[m].mean()
    v2_val = v2[m].mean()
    delta  = v2_val - v1_val
    print(f"{m:<25} {v1_val:>10.4f} {v2_val:>10.4f} {delta:>+10.4f}")
```

**v1 baseline (target to beat):**
| Metric | v1 | v2 Target |
|--------|-----|-----------|
| win_rate | 0.2868 | > 0.38 |
| annual_return_pct | 0.49 | > 5.0 |
| max_drawdown_pct | 52.62 | < 40.0 |
| trade_count | 128.9 | < 80 |
| calmar_ratio | ~0.01 | > 0.1 |
