# scripts/bbi/backtrader/20_run_backtest.py
import csv
import multiprocessing
import pandas as pd
import backtrader as bt
from config import (
    STOCK_DATA_DIR, OUTPUT_DIR, N_WORKERS, INIT_CASH,
    COMMISSION_BUY, COMMISSION_SELL, MIN_COMMISSION,
)


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


class AShareCommission(bt.CommInfoBase):
    params = (
        ('stocklike', True),
        ('commtype',  bt.CommInfoBase.COMM_PERC),
    )

    def _getcommission(self, size, price, pseudoexec):
        rate = COMMISSION_BUY if size > 0 else COMMISSION_SELL
        return max(abs(size) * price * rate, MIN_COMMISSION)


class AShareAllInSizer(bt.Sizer):
    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            size = int(cash / data.close[0] / 100) * 100
            return size if size >= 100 else 0
        return self.broker.getposition(data).size


class BBIStrategy(bt.Strategy):
    def __init__(self):
        self.bbi_line   = self.data.bbi
        self.close_line = self.data.close

    def next(self):
        if not self.position:
            # golden cross: close crossed above BBI
            if self.close_line[-1] < self.bbi_line[-1] and self.close_line[0] > self.bbi_line[0]:
                self.buy(exectype=bt.Order.Market)
        else:
            # death cross: close crossed below BBI
            if self.close_line[-1] > self.bbi_line[-1] and self.close_line[0] < self.bbi_line[0]:
                self.close()


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
        cerebro.addsizer(AShareAllInSizer)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,  _name='trade')
        cerebro.addanalyzer(bt.analyzers.Returns,        _name='returns', tann=252)
        cerebro.addanalyzer(bt.analyzers.DrawDown,       _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Transactions,   _name='txn')

        results = cerebro.run()
        strat = results[0]

        trade_an = strat.analyzers.trade.get_analysis()
        ret_an   = strat.analyzers.returns.get_analysis()
        dd_an    = strat.analyzers.drawdown.get_analysis()
        txn_an   = strat.analyzers.txn.get_analysis()

        total_trades = trade_an.get('total', {}).get('closed', 0)
        won          = trade_an.get('won',   {}).get('total',  0)
        win_rate     = won / total_trades if total_trades > 0 else 0.0

        gross_won   = trade_an.get('won',  {}).get('pnl', {}).get('total', 0.0)
        gross_lost  = abs(trade_an.get('lost', {}).get('pnl', {}).get('total', 1.0))
        pl_ratio    = gross_won / gross_lost if gross_lost > 0 else 0.0

        annual_ret = ret_an.get('rnorm100', 0.0)
        max_dd     = dd_an.get('max', {}).get('drawdown', 0.0)
        calmar     = annual_ret / max_dd if max_dd > 0 else 0.0

        avg_hold = trade_an.get('len', {}).get('average', 0.0)

        # build trades list using Transactions analyzer
        trades_out = []
        open_trade = None
        for dt_obj in sorted(txn_an.keys()):
            for txn in txn_an[dt_obj]:
                # txn format: [size, price, value, data_name, pnlcomm]
                size, price, pnlcomm = txn[0], txn[1], txn[4]
                date_str = dt_obj.strftime('%Y-%m-%d')
                if size > 0:
                    open_trade = {'buy_date': date_str, 'buy_price': round(price, 4), 'size': abs(size)}
                elif size < 0 and open_trade:
                    hold = (dt_obj - pd.Timestamp(open_trade['buy_date'])).days
                    ret_pct = round(
                        (price - open_trade['buy_price']) / open_trade['buy_price'] * 100, 4
                    )
                    pnl = round((price - open_trade['buy_price']) * open_trade['size'], 2)
                    trades_out.append({
                        'ts_code':    ts_code,
                        'name':       name,
                        'buy_date':   open_trade['buy_date'],
                        'buy_price':  open_trade['buy_price'],
                        'sell_date':  date_str,
                        'sell_price': round(price, 4),
                        'return_pct': ret_pct,
                        'hold_days':  hold,
                        'pnl':        pnl,
                    })
                    open_trade = None

        # append open position as unrealized trade
        if open_trade:
            try:
                df_last = pd.read_parquet(parquet_path, columns=['trade_date', 'close_qfq'])
                last_price = round(float(df_last.sort_values('trade_date')['close_qfq'].iloc[-1]), 4)
            except Exception:
                last_price = open_trade['buy_price']
            ret_pct = round((last_price - open_trade['buy_price']) / open_trade['buy_price'] * 100, 4)
            pnl = round((last_price - open_trade['buy_price']) * open_trade['size'], 2)
            trades_out.append({
                'ts_code':    ts_code,
                'name':       name,
                'buy_date':   open_trade['buy_date'],
                'buy_price':  open_trade['buy_price'],
                'sell_date':  '持仓中',
                'sell_price': last_price,
                'return_pct': ret_pct,
                'hold_days':  (pd.Timestamp(df_last['trade_date'].max()) - pd.Timestamp(open_trade['buy_date'])).days,
                'pnl':        pnl,
            })

        # avg_return_pct: mean of per-trade return_pct (%), closed trades only
        closed = [t for t in trades_out if t['sell_date'] != '持仓中']
        avg_ret_pct = round(
            sum(t['return_pct'] for t in closed) / len(closed), 4
        ) if closed else 0.0

        stats = {
            'ts_code':           ts_code,
            'name':              name,
            'trade_count':       total_trades,
            'win_rate':          round(win_rate, 4),
            'avg_return_pct':    avg_ret_pct,
            'profit_loss_ratio': round(pl_ratio, 4),
            'annual_return_pct': round(annual_ret, 4),
            'max_drawdown_pct':  round(max_dd, 4),
            'calmar_ratio':      round(calmar, 4),
            'avg_hold_days':     round(avg_hold, 1),
        }

        return stats, trades_out

    except Exception as e:
        print(f'ERROR {ts_code}: {e}')
        return None, []


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    parquet_files = sorted(STOCK_DATA_DIR.glob('*.parquet'))
    args_list = []
    for p in parquet_files:
        ts_code = p.stem
        try:
            df_meta = pd.read_parquet(p, columns=['name'])
            name = df_meta['name'].iloc[0] if len(df_meta) > 0 else ''
        except Exception:
            name = ''
        args_list.append((ts_code, name, p))

    print(f'Running backtest on {len(args_list)} stocks with {N_WORKERS} workers...')

    with multiprocessing.Pool(N_WORKERS) as pool:
        all_results = pool.map(run_single_stock, args_list)

    stats_rows  = [s for s, _ in all_results if s is not None]
    trades_rows = [t for _, tl in all_results for t in tl]

    stats_fields = [
        'ts_code', 'name', 'trade_count', 'win_rate', 'avg_return_pct',
        'profit_loss_ratio', 'annual_return_pct', 'max_drawdown_pct',
        'calmar_ratio', 'avg_hold_days',
    ]
    trades_fields = [
        'ts_code', 'name', 'buy_date', 'buy_price', 'sell_date',
        'sell_price', 'return_pct', 'hold_days', 'pnl',
    ]

    with open(OUTPUT_DIR / 'stats_summary.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=stats_fields)
        w.writeheader()
        w.writerows(stats_rows)

    with open(OUTPUT_DIR / 'trades_detail.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=trades_fields)
        w.writeheader()
        w.writerows(trades_rows)

    print(f'Done. {len(stats_rows)} stocks, {len(trades_rows)} trades.')
    print(f'  stats_summary.csv  -> {OUTPUT_DIR / "stats_summary.csv"}')
    print(f'  trades_detail.csv  -> {OUTPUT_DIR / "trades_detail.csv"}')


if __name__ == '__main__':
    main()
