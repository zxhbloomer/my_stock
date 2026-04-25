# BBI Backtrader Backtesting System — Implementation Plan

**Date:** 2026-04-20
**Goal:** Build a standalone BBI-crossover backtesting system using Backtrader. Reads pre-filtered A-share data from PostgreSQL, runs per-stock backtests in parallel, and generates two self-contained HTML reports (ranking overview + per-stock detail with ECharts K-line).

---

## Architecture

```
scripts/bbi/backtrader/
├── config.py                  # all constants and paths
├── 10_prepare_data.py         # filter stocks + export parquet
├── 20_run_backtest.py         # parallel Cerebro runs
├── 30_generate_report.py      # HTML reports
└── output/
    ├── stock_data/            # {ts_code}.parquet  (OHLCV + BBI)
    ├── kline_data/            # {ts_code}.json     (ECharts payload)
    ├── stats_summary.csv
    ├── trades_detail.csv
    ├── report_ranking.html
    └── report_detail.html
```

## Tech Stack

| Layer | Library |
|-------|---------|
| Backtesting | backtrader |
| Data storage | parquet via pandas + pyarrow |
| DB access | SQLAlchemy + psycopg2 |
| Parallelism | multiprocessing.Pool |
| Reporting | Jinja2 + ECharts 5 (CDN) |

---

## Task 1: config.py + Output Directory Structure

**File:** `scripts/bbi/backtrader/config.py`

### Steps

1. Create directory `scripts/bbi/backtrader/` with an empty `__init__.py`.
2. Write `config.py` with all constants.
3. Verify: run `python config.py` from inside `scripts/bbi/backtrader/` — should print no errors.
4. Commit: `git add scripts/bbi/backtrader/ && git commit -m 'feat: add BBI backtrader config'`

### config.py

```python
# scripts/bbi/backtrader/config.py
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

OUTPUT_DIR     = Path(__file__).parent / "output"
STOCK_DATA_DIR = OUTPUT_DIR / "stock_data"
KLINE_DATA_DIR = OUTPUT_DIR / "kline_data"
```

### Directory bootstrap (called at top of each script)

```python
from config import OUTPUT_DIR, STOCK_DATA_DIR, KLINE_DATA_DIR

def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    KLINE_DATA_DIR.mkdir(parents=True, exist_ok=True)
```

---

## Task 2: 10_prepare_data.py -- Stock Filtering + Parquet Export

**File:** `scripts/bbi/backtrader/10_prepare_data.py`

### Steps

1. Write the script (full code below).
2. Run: `python 10_prepare_data.py` (from inside `scripts/bbi_backtrader/`).
3. Verify: `output/stock_data/` contains `.parquet` files; spot-check one with `pd.read_parquet()`.
4. Commit: `git add scripts/bbi_backtrader/10_prepare_data.py && git commit -m "feat: add BBI data preparation script"`

### Idempotency

At startup: `shutil.rmtree(STOCK_DATA_DIR)` then `STOCK_DATA_DIR.mkdir()` -- guarantees a clean re-run.

### SQL Step 1: Basic filter

No look-ahead bias: list_date must be at least 365 days before START_DATE.

```sql
SELECT ts_code, name, list_date
FROM tushare_v2."001_stock_basic"
WHERE list_status IN ('L', 'D')
  AND ts_code NOT LIKE '8%'
  AND name NOT LIKE '%ST%'
  AND list_date <= to_char(
        :start_date::date - interval '365 days',
        'YYYYMMDD'
      )
```

### SQL Step 2: Liquidity filter

Window = [start-504d, start) to avoid look-ahead bias (504 calendar days = 252 trading days).

```sql
SELECT ts_code
FROM tushare_v2."027_daily_basic"
WHERE trade_date >= to_char(
        :start_date::date - interval '504 days',
        'YYYYMMDD'
      )
  AND trade_date < :start_date
GROUP BY ts_code
HAVING AVG(circ_mv) >= :min_circ_mv
   AND AVG(amount)  >= :min_amount
```

### SQL Step 3: OHLCV + BBI per stock

```sql
SELECT trade_date,
       open_qfq, high_qfq, low_qfq, close_qfq,
       vol,
       bbi_qfq
FROM tushare_v2."063_stk_factor_pro"
WHERE ts_code  = :ts_code
  AND trade_date >= :start_date
  AND trade_date <= :end_date
ORDER BY trade_date
```

### Full Script

```python
# scripts/bbi/backtrader/10_prepare_data.py
import shutil
import datetime
import pandas as pd
from sqlalchemy import create_engine, text
from config import (
    DB_URL, START_DATE, END_DATE,
    FILTER_MIN_CIRC_MV, FILTER_MIN_AMOUNT,
    STOCK_DATA_DIR, OUTPUT_DIR,
)

def main():
    end_date = END_DATE or datetime.date.today().strftime('%Y-%m-%d')

    if STOCK_DATA_DIR.exists():
        shutil.rmtree(STOCK_DATA_DIR)
    STOCK_DATA_DIR.mkdir(parents=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = create_engine(DB_URL)

    sql_basic = text("""
        SELECT ts_code, name, list_date
        FROM tushare_v2."001_stock_basic"
        WHERE list_status IN ('L', 'D')
          AND ts_code NOT LIKE '8%'
          AND name NOT LIKE '%ST%'
          AND list_date <= to_char(
                :start_date::date - interval '365 days', 'YYYYMMDD')
    """)
    with engine.connect() as conn:
        df_basic = pd.read_sql(sql_basic, conn, params={'start_date': START_DATE})
    print(f'Step 1: {len(df_basic)} stocks after basic filter')

    sql_liq = text("""
        SELECT ts_code
        FROM tushare_v2."027_daily_basic"
        WHERE trade_date >= to_char(
                :start_date::date - interval '504 days', 'YYYYMMDD')
          AND trade_date < :start_date
        GROUP BY ts_code
        HAVING AVG(circ_mv) >= :min_circ_mv
           AND AVG(amount)  >= :min_amount
    """)
    with engine.connect() as conn:
        df_liq = pd.read_sql(sql_liq, conn, params={
            'start_date': START_DATE,
            'min_circ_mv': FILTER_MIN_CIRC_MV,
            'min_amount': FILTER_MIN_AMOUNT,
        })
    liquid_codes = set(df_liq['ts_code'])
    df_stocks = df_basic[df_basic['ts_code'].isin(liquid_codes)].reset_index(drop=True)
    print(f'Step 2: {len(df_stocks)} stocks after liquidity filter')

    sql_data = text("""
        SELECT trade_date, open_qfq, high_qfq, low_qfq, close_qfq, vol, bbi_qfq
        FROM tushare_v2."063_stk_factor_pro"
        WHERE ts_code = :ts_code
          AND trade_date >= :start_date
          AND trade_date <= :end_date
        ORDER BY trade_date
    """)

    skipped = 0
    with engine.connect() as conn:
        for _, row in df_stocks.iterrows():
            ts_code = row['ts_code']
            df = pd.read_sql(sql_data, conn, params={
                'ts_code': ts_code,
                'start_date': START_DATE,
                'end_date': end_date,
            })
            if len(df) < 60:
                skipped += 1
                continue
            df['name'] = row['name']
            df.to_parquet(STOCK_DATA_DIR / f'{ts_code}.parquet', index=False)

    print(f'Exported {len(df_stocks) - skipped} parquet files ({skipped} skipped)')

if __name__ == '__main__':
    main()
```

---

## Task 3: 20_run_backtest.py -- BBIData Feed + BBIStrategy + Parallel Cerebro

**File:** `scripts/bbi/backtrader/20_run_backtest.py`

### Steps

1. Write the script (full code below).
2. Run: `python 20_run_backtest.py`
3. Verify: `output/stats_summary.csv` and `output/trades_detail.csv` exist and have data.
4. Commit: `git add scripts/bbi_backtrader/20_run_backtest.py && git commit -m "feat: add BBI parallel backtest runner"`

### Idempotency

CSV files opened with `mode='w'` (overwrite on each run).

### BBIData Feed

Maps parquet columns to Backtrader line names. The `bbi` line carries the pre-computed BBI value from `063_stk_factor_pro`.

```python
import backtrader as bt

class BBIData(bt.feeds.PandasData):
    lines = ('bbi',)
    params = (
        ('datetime', None),
        ('open',         'open_qfq'),
        ('high',         'high_qfq'),
        ('low',          'low_qfq'),
        ('close',        'close_qfq'),
        ('volume',       'vol'),
        ('openinterest', -1),
        ('bbi',          'bbi_qfq'),
    )
```

### AShareCommission

Buy: 0.05% (min 5 yuan). Sell: 0.15% (min 5 yuan). A single `CommInfoBase` subclass checks `size`
sign to apply the correct rate. Backtrader does not support two separate commission objects on the
same broker — the second call to `addcommissioninfo` would overwrite the first.

```python
from config import COMMISSION_BUY, COMMISSION_SELL, MIN_COMMISSION

class AShareCommission(bt.CommInfoBase):
    params = (
        ('stocklike', True),
        ('commtype',  bt.CommInfoBase.COMM_PERC),
    )
    def _getcommission(self, size, price, pseudoexec):
        rate = COMMISSION_BUY if size > 0 else COMMISSION_SELL
        return max(abs(size) * price * rate, MIN_COMMISSION)
```

### BBIStrategy

BBI golden cross (close crosses above BBI) = buy. BBI death cross (close crosses below BBI) = sell.

```python
import datetime as dt

class BBIStrategy(bt.Strategy):
    def __init__(self):
        self.bbi   = self.data.bbi
        self.close = self.data.close

    def next(self):
        if not self.position:
            # close crossed above BBI
            if self.close[-1] < self.bbi[-1] and self.close[0] > self.bbi[0]:
                self.buy(exectype=bt.Order.Market)
        else:
            # close crossed below BBI
            if self.close[-1] > self.bbi[-1] and self.close[0] < self.bbi[0]:
                self.close()
```

### Per-stock runner

```python
def run_single_stock(args):
    ts_code, name, parquet_path = args
    try:
        df = pd.read_parquet(parquet_path)
        df.index = pd.to_datetime(df['trade_date'])
        df = df.sort_index()

        cerebro = bt.Cerebro()
        cerebro.addstrategy(BBIStrategy)
        data = BBIData(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(INIT_CASH)
        cerebro.broker.addcommissioninfo(AShareCommission())
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,  _name='trade')
        cerebro.addanalyzer(bt.analyzers.Returns,        _name='returns', tann=252)
        cerebro.addanalyzer(bt.analyzers.DrawDown,       _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Transactions,   _name='txn')

        results = cerebro.run()
        strat = results[0]

        trade_an  = strat.analyzers.trade.get_analysis()
        ret_an    = strat.analyzers.returns.get_analysis()
        dd_an     = strat.analyzers.drawdown.get_analysis()

        total_trades = trade_an.get('total', {}).get('closed', 0)
        won          = trade_an.get('won',   {}).get('total',  0)
        win_rate     = won / total_trades if total_trades > 0 else 0.0

        avg_ret_pct  = trade_an.get('pnl', {}).get('net', {}).get('average', 0.0)
        gross_won    = trade_an.get('won',  {}).get('pnl', {}).get('total', 0.0)
        gross_lost   = abs(trade_an.get('lost', {}).get('pnl', {}).get('total', 1.0))
        pl_ratio     = gross_won / gross_lost if gross_lost > 0 else 0.0

        annual_ret   = ret_an.get('rnorm100', 0.0)
        max_dd       = dd_an.get('max', {}).get('drawdown', 0.0)
        calmar       = annual_ret / max_dd if max_dd > 0 else 0.0

        # avg_hold_days: TradeAnalyzer stores bar lengths under len.total / len.average
        avg_hold = trade_an.get('len', {}).get('average', 0.0)

        stats = {
            'ts_code':          ts_code,
            'name':             name,
            'trade_count':      total_trades,
            'win_rate':         round(win_rate, 4),
            'avg_return_pct':   round(avg_ret_pct, 4),
            'profit_loss_ratio':round(pl_ratio, 4),
            'annual_return_pct':round(annual_ret, 4),
            'max_drawdown_pct': round(max_dd, 4),
            'calmar_ratio':     round(calmar, 4),
            'avg_hold_days':    round(avg_hold, 1),
        }

        # build trades list using Transactions analyzer
        # txn_an: {datetime: [(size, price, value, pnlcomm), ...]}
        txn_an = strat.analyzers.txn.get_analysis()
        trades_out = []
        open_trade = None
        for dt_obj in sorted(txn_an.keys()):
            for txn in txn_an[dt_obj]:
                size, price, value, pnlcomm = txn[0], txn[1], txn[2], txn[3]
                date_str = dt_obj.strftime('%Y-%m-%d')
                if size > 0:  # buy
                    open_trade = {'buy_date': date_str, 'buy_price': round(price, 4),
                                  'buy_size': size}
                elif size < 0 and open_trade:  # sell
                    hold = (dt_obj - pd.Timestamp(open_trade['buy_date'])).days
                    ret_pct = round((price - open_trade['buy_price']) / open_trade['buy_price'] * 100, 4)
                    trades_out.append({
                        'ts_code':    ts_code,
                        'name':       name,
                        'buy_date':   open_trade['buy_date'],
                        'buy_price':  open_trade['buy_price'],
                        'sell_date':  date_str,
                        'sell_price': round(price, 4),
                        'return_pct': ret_pct,
                        'hold_days':  hold,
                        'pnl':        round(pnlcomm, 2),
                    })
                    open_trade = None

        return stats, trades_out
    except Exception as e:
        return None, []
```

### Main with Windows multiprocessing guard

```python
import multiprocessing
import csv
import pandas as pd
from pathlib import Path
from config import STOCK_DATA_DIR, OUTPUT_DIR, N_WORKERS, INIT_CASH

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parquet_files = sorted(STOCK_DATA_DIR.glob('*.parquet'))
    args_list = []
    for p in parquet_files:
        ts_code = p.stem
        df_meta = pd.read_parquet(p, columns=['name'])
        name = df_meta['name'].iloc[0] if len(df_meta) > 0 else ''
        args_list.append((ts_code, name, p))

    print(f'Running backtest on {len(args_list)} stocks with {N_WORKERS} workers...')

    with multiprocessing.Pool(N_WORKERS) as pool:
        all_results = pool.map(run_single_stock, args_list)

    stats_rows  = [s for s, _ in all_results if s is not None]
    trades_rows = [t for _, tl in all_results for t in tl]

    stats_fields  = ['ts_code','name','trade_count','win_rate','avg_return_pct',
                     'profit_loss_ratio','annual_return_pct','max_drawdown_pct',
                     'calmar_ratio','avg_hold_days']
    trades_fields = ['ts_code','name','buy_date','buy_price','sell_date',
                     'sell_price','return_pct','hold_days','pnl']

    with open(OUTPUT_DIR / 'stats_summary.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=stats_fields)
        w.writeheader()
        w.writerows(stats_rows)

    with open(OUTPUT_DIR / 'trades_detail.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=trades_fields)
        w.writeheader()
        w.writerows(trades_rows)

    print(f'Done. {len(stats_rows)} stocks, {len(trades_rows)} trades.')

if __name__ == '__main__':
    main()
```

---

## Task 4: 30_generate_report.py -- report_ranking.html + report_detail.html

**File:** `scripts/bbi/backtrader/30_generate_report.py`

### Steps

1. Write the script (full code below).
2. Run: `python 30_generate_report.py`
3. Verify: open `output/report_ranking.html` and `output/report_detail.html` in a browser.
4. Commit: `git add scripts/bbi_backtrader/30_generate_report.py && git commit -m "feat: add BBI report generator"`

### Idempotency

Both HTML files are overwritten directly on each run.

### ECharts K-line Data Format

ECharts candlestick series uses `[open, close, low, high]` order (NOT OHLC).
K-line JSON files are stored per-stock in `output/kline_data/{ts_code}.json` and loaded on-demand
via `fetch()` in the HTML -- NOT embedded (would be ~360 MB total).

```python
def build_kline_json(ts_code, df_trades):
    df = pd.read_parquet(STOCK_DATA_DIR / f'{ts_code}.parquet').sort_values('trade_date')
    dates   = df['trade_date'].tolist()
    # ECharts candlestick order: [open, close, low, high]
    candles = df[['open_qfq','close_qfq','low_qfq','high_qfq']].round(4).values.tolist()
    bbi     = df['bbi_qfq'].round(4).tolist()
    sub     = df_trades[df_trades['ts_code'] == ts_code]
    buys    = sub[['buy_date',  'buy_price']].values.tolist()
    sells   = sub[['sell_date', 'sell_price']].values.tolist()
    return {'dates': dates, 'candles': candles, 'bbi': bbi, 'buys': buys, 'sells': sells}
```

### report_ranking.html Layout

- Global stats header: total stocks, avg win rate, avg annual return.
- Sortable table (default sort: calmar_ratio desc).
- Columns: rank, ts_code, name, trade_count, win_rate, avg_return_pct, profit_loss_ratio,
  annual_return_pct, max_drawdown_pct, calmar_ratio, avg_hold_days.
- Search box filters rows by ts_code or name.
- Win rate distribution histogram (ECharts bar, 10 buckets 0-100%).
- Click any row opens `report_detail.html?stock={ts_code}` in a new tab.

### report_detail.html Layout

Three-panel layout:
- Header bar: title.
- Left panel (1/3 width): scrollable stock list sorted by calmar_ratio; click to load.
- Right panel (2/3 width):
  - Stats cards row: trade_count, win_rate, annual_return_pct, max_drawdown_pct, calmar_ratio.
  - Upper chart (60% of right panel height): ECharts K-line with BBI overlay + buy/sell markers.
  - Lower table (40%): trade detail rows; click a row to dataZoom the K-line to that trade range.

K-line chart features:
- Candlestick series: `[open, close, low, high]` per ECharts convention.
- BBI line overlay on same y-axis.
- Buy markers: red triangle-up (symbol: `triangle`, color: `#e74c3c`).
- Sell markers: green triangle-down (symbol: `triangle`, symbolRotate: 180, color: `#2ecc71`).
- dataZoom default shows last 2 years (startValue = dates.length - 504).
- On trade row click: `chart.dispatchAction({ type: 'dataZoom', startValue: buyIdx-10, endValue: sellIdx+10 })`.

### Full Script

The script has two main functions: `make_ranking_html` and `make_detail_html`, plus a `main` that
orchestrates them. HTML is built via string concatenation (not f-strings) to avoid CSS/JS brace
conflicts. ECharts CDN is used -- no local assets needed.

```python
# scripts/bbi/backtrader/30_generate_report.py
import json
import numpy as np
import pandas as pd
from config import OUTPUT_DIR, STOCK_DATA_DIR, KLINE_DATA_DIR


def build_kline_json(ts_code, df_trades):
    parquet_path = STOCK_DATA_DIR / (ts_code + '.parquet')
    if not parquet_path.exists():
        return None
    df = pd.read_parquet(parquet_path).sort_values('trade_date')
    dates   = df['trade_date'].tolist()
    candles = df[['open_qfq', 'close_qfq', 'low_qfq', 'high_qfq']].round(4).values.tolist()
    bbi     = df['bbi_qfq'].round(4).tolist()
    sub     = df_trades[df_trades['ts_code'] == ts_code]
    buys    = sub[['buy_date',  'buy_price']].values.tolist()
    sells   = sub[['sell_date', 'sell_price']].values.tolist()
    return {'dates': dates, 'candles': candles, 'bbi': bbi, 'buys': buys, 'sells': sells}


def make_ranking_html(df_sorted, total_stocks, avg_win_rate, avg_annual_ret,
                      hist_labels, hist_counts):
    rows = ''
    for i, row in df_sorted.iterrows():
        rows += (
            '<tr onclick="window.open(\'report_detail.html?stock='
            + row.ts_code + '\',\'_blank\')" style="cursor:pointer">'
            + '<td>' + str(i+1) + '</td>'
            + '<td>' + row.ts_code + '</td>'
            + '<td>' + row['name'] + '</td>'
            + '<td>' + str(int(row.trade_count)) + '</td>'
            + '<td>' + f'{row.win_rate:.1%}' + '</td>'
            + '<td>' + f'{row.avg_return_pct:.2f}%' + '</td>'
            + '<td>' + f'{row.profit_loss_ratio:.2f}' + '</td>'
            + '<td>' + f'{row.annual_return_pct:.2f}%' + '</td>'
            + '<td>' + f'{row.max_drawdown_pct:.2f}%' + '</td>'
            + '<td>' + f'{row.calmar_ratio:.2f}' + '</td>'
            + '<td>' + f'{row.avg_hold_days:.1f}' + '</td>'
            + '</tr>'
        )
    css = (
        'body{font-family:Arial,sans-serif;margin:20px;background:#f5f5f5}'
        '.header{background:#2c3e50;color:white;padding:16px 24px;border-radius:8px;margin-bottom:20px}'
        '.stats-bar{display:flex;gap:40px;margin-top:8px}'
        '.stat{font-size:1.2em}.stat span{font-weight:bold;color:#f39c12}'
        'input#search{padding:8px 12px;width:300px;border:1px solid #ccc;border-radius:4px;margin-bottom:12px}'
        'table{width:100%;border-collapse:collapse;background:white;border-radius:8px;overflow:hidden}'
        'th{background:#34495e;color:white;padding:10px 8px;cursor:pointer;user-select:none}'
        'th:hover{background:#2c3e50}'
        'td{padding:8px;border-bottom:1px solid #eee;text-align:center}'
        'tr:hover{background:#ecf0f1}'
        '#histogram{height:200px;margin-top:24px;background:white;border-radius:8px}'
    )
    js_filter = (
        'function filterTable(q){'
        'q=q.toLowerCase();'
        'document.querySelectorAll(\'#tableBody tr\').forEach(r=>{'
        'r.style.display=r.textContent.toLowerCase().includes(q)?\'\':\' none\';});}'
    )
    js_sort = (
        'let sortDir={};'
        'function sortTable(col){'
        'const tbody=document.getElementById(\'tableBody\');'
        'const rows=Array.from(tbody.rows);'
        'sortDir[col]=!sortDir[col];'
        'rows.sort((a,b)=>{'
        'const av=a.cells[col].textContent.replace(\'%\',\'\'),'
        'bv=b.cells[col].textContent.replace(\'%\',\'\');'
        'const an=parseFloat(av),bn=parseFloat(bv);'
        'if(!isNaN(an)&&!isNaN(bn))return sortDir[col]?bn-an:an-bn;'
        'return sortDir[col]?bv.localeCompare(av):av.localeCompare(bv);});'
        'rows.forEach(r=>tbody.appendChild(r));}'
    )
    js_chart = (
        'const chart=echarts.init(document.getElementById(\'histogram\'));'
        'chart.setOption({'
        'title:{text:\'Win Rate Distribution\',left:\'center\'},'
        'xAxis:{type:\'category\',data:' + json.dumps(hist_labels) + '},'
        'yAxis:{type:\'value\',name:\'Stocks\'},'
        'series:[{type:\'bar\',data:' + json.dumps(hist_counts) + ',itemStyle:{color:\'#3498db\'}}]'
        '});'
    )
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<title>BBI Ranking</title>'
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
        '<style>' + css + '</style></head><body>'
        '<div class="header"><h2 style="margin:0">BBI Backtest Ranking</h2>'
        '<div class="stats-bar">'
        '<div class="stat">Total Stocks: <span>' + str(total_stocks) + '</span></div>'
        '<div class="stat">Avg Win Rate: <span>' + str(avg_win_rate) + '%</span></div>'
        '<div class="stat">Avg Annual Return: <span>' + str(avg_annual_ret) + '%</span></div>'
        '</div></div>'
        '<input id="search" placeholder="Search by code or name..." oninput="filterTable(this.value)">'
        '<table id="rankTable"><thead><tr>'
        '<th onclick="sortTable(0)">Rank</th>'
        '<th onclick="sortTable(1)">Code</th>'
        '<th onclick="sortTable(2)">Name</th>'
        '<th onclick="sortTable(3)">Trades</th>'
        '<th onclick="sortTable(4)">Win Rate</th>'
        '<th onclick="sortTable(5)">Avg Ret%</th>'
        '<th onclick="sortTable(6)">P/L Ratio</th>'
        '<th onclick="sortTable(7)">Annual Ret%</th>'
        '<th onclick="sortTable(8)">Max DD%</th>'
        '<th onclick="sortTable(9)">Calmar</th>'
        '<th onclick="sortTable(10)">Avg Hold Days</th>'
        '</tr></thead>'
        '<tbody id="tableBody">' + rows + '</tbody></table>'
        '<div id="histogram"></div>'
        '<script>' + js_filter + js_sort + js_chart + '</script>'
        '</body></html>'
    )
    return html
```

```python
def make_detail_html(df_sorted, df_trades):
    stock_list = ''
    for _, row in df_sorted.iterrows():
        color = '#e74c3c' if row.annual_return_pct >= 0 else '#2ecc71'
        stock_list += (
            '<div class="stock-item" onclick="loadStock(\'' + row.ts_code + '\')">'
            '<span class="code">' + row.ts_code + '</span>'
            '<span class="name">' + row['name'] + '</span>'
            '<span class="ret" style="color:' + color + '">'
            + f'{row.annual_return_pct:.1f}%</span></div>'
        )

    stats_js = ('const statsData = '
        + json.dumps(
            df_sorted.set_index('ts_code')[
                ['trade_count','win_rate','annual_return_pct','max_drawdown_pct','calmar_ratio']
            ].to_dict('index')
        ) + ';')

    trades_parts = ['const tradesData = {};']
    for ts_code in df_sorted['ts_code']:
        sub = df_trades[df_trades['ts_code'] == ts_code][
            ['buy_date','buy_price','sell_date','sell_price','return_pct','hold_days','pnl']
        ].to_dict('records')
        trades_parts.append('tradesData["' + ts_code + '"] = ' + json.dumps(sub) + ';')
    trades_js = '\n'.join(trades_parts)

    css = (
        '*{box-sizing:border-box;margin:0;padding:0}'
        'body{font-family:Arial,sans-serif;display:flex;flex-direction:column;height:100vh;background:#f0f2f5}'
        '.header{background:#2c3e50;color:white;padding:12px 20px;flex-shrink:0}'
        '.main{display:flex;flex:1;overflow:hidden}'
        '.left-panel{width:33%;border-right:1px solid #ddd;overflow-y:auto;background:white}'
        '.right-panel{flex:1;display:flex;flex-direction:column;overflow:hidden;padding:12px;gap:12px}'
        '.stock-item{display:flex;justify-content:space-between;padding:10px 14px;cursor:pointer;border-bottom:1px solid #f0f0f0}'
        '.stock-item:hover,.stock-item.active{background:#ecf0f1}'
        '.stock-item .code{font-weight:bold;color:#2c3e50;width:90px}'
        '.stock-item .name{flex:1;color:#555}'
        '.stock-item .ret{font-weight:bold;width:60px;text-align:right}'
        '.stats-cards{display:flex;gap:10px;flex-shrink:0}'
        '.card{background:white;border-radius:8px;padding:10px 16px;flex:1;text-align:center}'
        '.card .label{font-size:.75em;color:#888}'
        '.card .value{font-size:1.3em;font-weight:bold;color:#2c3e50}'
        '#kline-chart{background:white;border-radius:8px;flex:0 0 60%;min-height:0}'
        '.trade-table-wrap{background:white;border-radius:8px;flex:1;overflow-y:auto;min-height:0}'
        'table{width:100%;border-collapse:collapse;font-size:.85em}'
        'th{background:#34495e;color:white;padding:8px;position:sticky;top:0}'
        'td{padding:7px 8px;border-bottom:1px solid #eee;text-align:center;cursor:pointer}'
        'tr:hover td{background:#ecf0f1}'
    )

    js_main = r"""
const chart = echarts.init(document.getElementById('kline-chart'));
function loadStock(code) {
  document.querySelectorAll('.stock-item').forEach(el => el.classList.remove('active'));
  const el = document.querySelector('.stock-item[onclick*="' + code + '"]');
  if (el) el.classList.add('active');
  const s = statsData[code] || {};
  document.getElementById('c-trades').textContent  = s.trade_count != null ? s.trade_count : '--';
  document.getElementById('c-winrate').textContent = s.win_rate    != null ? (s.win_rate*100).toFixed(1)+'%' : '--';
  document.getElementById('c-annret').textContent  = s.annual_return_pct != null ? s.annual_return_pct.toFixed(2)+'%' : '--';
  document.getElementById('c-maxdd').textContent   = s.max_drawdown_pct  != null ? s.max_drawdown_pct.toFixed(2)+'%'  : '--';
  document.getElementById('c-calmar').textContent  = s.calmar_ratio      != null ? s.calmar_ratio.toFixed(2)           : '--';
  fetch('kline_data/' + code + '.json').then(r => r.json()).then(data => renderChart(code, data));
}
function renderChart(code, data) {
  const startIdx = Math.max(0, data.dates.length - 504);
  chart.setOption({
    animation: false,
    tooltip: {trigger:'axis', axisPointer:{type:'cross'}},
    legend: {data:['K-line','BBI','Buy','Sell']},
    dataZoom: [
      {type:'inside', startValue:startIdx, endValue:data.dates.length-1},
      {type:'slider', startValue:startIdx, endValue:data.dates.length-1}
    ],
    xAxis: {type:'category', data:data.dates, scale:true},
    yAxis: {type:'value', scale:true},
    series: [
      {name:'K-line', type:'candlestick', data:data.candles,
       itemStyle:{color:'#e74c3c',color0:'#2ecc71',borderColor:'#e74c3c',borderColor0:'#2ecc71'}},
      {name:'BBI', type:'line', data:data.bbi, smooth:true,
       lineStyle:{color:'#f39c12',width:1.5}, showSymbol:false},
      {name:'Buy',  type:'scatter', data:data.buys,
       symbol:'triangle', symbolSize:10, itemStyle:{color:'#e74c3c'}},
      {name:'Sell', type:'scatter', data:data.sells,
       symbol:'triangle', symbolRotate:180, symbolSize:10, itemStyle:{color:'#2ecc71'}}
    ]
  }, true);
  const trades = tradesData[code] || [];
  const tbody = document.getElementById('tradeBody');
  tbody.innerHTML = '';
  trades.forEach(t => {
    const color = t.return_pct >= 0 ? '#e74c3c' : '#2ecc71';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>'+t.buy_date+'</td><td>'+t.buy_price+'</td>'
      +'<td>'+t.sell_date+'</td><td>'+t.sell_price+'</td>'
      +'<td style="color:'+color+'">'+t.return_pct.toFixed(2)+'%</td>'
      +'<td>'+t.hold_days+'</td>'
      +'<td style="color:'+color+'">'+t.pnl.toFixed(2)+'</td>';
    tr.onclick = () => zoomToTrade(data.dates, t.buy_date, t.sell_date);
    tbody.appendChild(tr);
  });
}
function zoomToTrade(dates, buyDate, sellDate) {
  const bi = dates.indexOf(buyDate), si = dates.indexOf(sellDate);
  if (bi < 0 || si < 0) return;
  chart.dispatchAction({type:'dataZoom',
    startValue:Math.max(0,bi-10), endValue:Math.min(dates.length-1,si+10)});
}
const params = new URLSearchParams(window.location.search);
const initStock = params.get('stock');
if (initStock) loadStock(initStock);
else { const first = document.querySelector('.stock-item'); if (first) first.click(); }
"""

    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<title>BBI Detail</title>'
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
        '<style>' + css + '</style></head><body>'
        '<div class="header"><h3>BBI Backtest Detail</h3></div>'
        '<div class="main">'
        '<div class="left-panel" id="stockList">' + stock_list + '</div>'
        '<div class="right-panel">'
        '<div class="stats-cards">'
        '<div class="card"><div class="label">Trades</div><div class="value" id="c-trades">--</div></div>'
        '<div class="card"><div class="label">Win Rate</div><div class="value" id="c-winrate">--</div></div>'
        '<div class="card"><div class="label">Annual Ret</div><div class="value" id="c-annret">--</div></div>'
        '<div class="card"><div class="label">Max DD</div><div class="value" id="c-maxdd">--</div></div>'
        '<div class="card"><div class="label">Calmar</div><div class="value" id="c-calmar">--</div></div>'
        '</div>'
        '<div id="kline-chart"></div>'
        '<div class="trade-table-wrap">'
        '<table><thead><tr>'
        '<th>Buy Date</th><th>Buy Price</th><th>Sell Date</th><th>Sell Price</th>'
        '<th>Return%</th><th>Hold Days</th><th>PnL</th>'
        '</tr></thead><tbody id="tradeBody"></tbody></table>'
        '</div></div></div>'
        '<script>' + stats_js + '\n' + trades_js + js_main + '</script>'
        '</body></html>'
    )
    return html


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    KLINE_DATA_DIR.mkdir(parents=True, exist_ok=True)

    df_stats  = pd.read_csv(OUTPUT_DIR / 'stats_summary.csv')
    df_trades = pd.read_csv(OUTPUT_DIR / 'trades_detail.csv')

    for ts_code in df_stats['ts_code']:
        payload = build_kline_json(ts_code, df_trades)
        if payload:
            with open(KLINE_DATA_DIR / (ts_code + '.json'), 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)

    df_sorted = df_stats.sort_values('calmar_ratio', ascending=False).reset_index(drop=True)
    total_stocks   = len(df_stats)
    avg_win_rate   = round(df_stats['win_rate'].mean() * 100, 1)
    avg_annual_ret = round(df_stats['annual_return_pct'].mean(), 2)

    hist, edges = np.histogram(df_stats['win_rate'] * 100, bins=10, range=(0, 100))
    hist_labels = [str(int(edges[i])) + '-' + str(int(edges[i+1])) + '%' for i in range(len(hist))]

    ranking_html = make_ranking_html(df_sorted, total_stocks, avg_win_rate, avg_annual_ret,
                                     hist_labels, hist.tolist())
    with open(OUTPUT_DIR / 'report_ranking.html', 'w', encoding='utf-8') as f:
        f.write(ranking_html)
    print('report_ranking.html written')

    detail_html = make_detail_html(df_sorted, df_trades)
    with open(OUTPUT_DIR / 'report_detail.html', 'w', encoding='utf-8') as f:
        f.write(detail_html)
    print('report_detail.html written')


if __name__ == '__main__':
    main()
```

---

## Output CSV Schemas (Reference)

**stats_summary.csv**

| Column | Type | Description |
|--------|------|-------------|
| ts_code | str | Tushare stock code |
| name | str | Stock name |
| trade_count | int | Total closed trades |
| win_rate | float | Winning trades / total trades (0-1) |
| avg_return_pct | float | Average return per trade (%) |
| profit_loss_ratio | float | Gross profit / gross loss |
| annual_return_pct | float | Annualized return (%) |
| max_drawdown_pct | float | Maximum drawdown (%) |
| calmar_ratio | float | annual_return / max_drawdown |
| avg_hold_days | float | Average holding period (trading days) |

**trades_detail.csv**

| Column | Type | Description |
|--------|------|-------------|
| ts_code | str | Tushare stock code |
| name | str | Stock name |
| buy_date | str | Entry date YYYY-MM-DD |
| buy_price | float | Entry price (qfq adjusted) |
| sell_date | str | Exit date YYYY-MM-DD |
| sell_price | float | Exit price (qfq adjusted) |
| return_pct | float | Trade return (%) |
| hold_days | int | Holding period (trading days) |
| pnl | float | Net profit/loss (yuan) |

---

## Run Order

```bash
cd scripts/bbi/backtrader
python 10_prepare_data.py    # ~5-30 min depending on stock count
python 20_run_backtest.py    # ~2-10 min with N_WORKERS=8
python 30_generate_report.py
# Then open output/report_ranking.html in browser
```
