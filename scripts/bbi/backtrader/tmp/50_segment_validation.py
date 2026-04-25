"""
分段验证：按市场环境切段，验证策略在不同市场下的稳健性
对比 v2(ATR) vs v1(基准) 在各段的表现
"""
import multiprocessing
import pandas as pd
import backtrader as bt
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import (
    STOCK_DATA_DIR, INIT_CASH, N_WORKERS,
    COMMISSION_BUY, COMMISSION_SELL, MIN_COMMISSION,
    MACD_FAST, MACD_SLOW, MACD_SIGNAL,
    PYRAMID_FIRST_RATIO, PYRAMID_ADD_TRIGGER,
    ATR_PERIOD, ATR_MULTIPLIER,
)

V1_STATS_PATH = Path(__file__).parent.parent / 'v1' / 'output' / 'stats_summary.csv'

# 四段市场环境
SEGMENTS = [
    ('2018熊市',       '2018-01-01', '2018-12-31'),
    ('2019-2021牛市',  '2019-01-01', '2021-12-31'),
    ('2022-2024震荡',  '2022-01-01', '2024-12-31'),
    ('2025-2026反弹',  '2025-01-01', '2026-12-31'),
]


class BBIData(bt.feeds.PandasData):
    lines = ('bbi', 'ma60',)
    params = (
        ('datetime', None),
        ('open',  'open_qfq'), ('high', 'high_qfq'),
        ('low',   'low_qfq'),  ('close', 'close_qfq'),
        ('volume', 'vol'), ('openinterest', -1),
        ('bbi', 'bbi_qfq'), ('ma60', 'ma60'),
    )


class AShareCommission(bt.CommInfoBase):
    params = (('stocklike', True), ('commtype', bt.CommInfoBase.COMM_PERC),)
    def _getcommission(self, size, price, pseudoexec):
        rate = COMMISSION_BUY if size > 0 else COMMISSION_SELL
        return max(abs(size) * price * rate, MIN_COMMISSION)


class BBIATRStrategy(bt.Strategy):
    def __init__(self):
        self.bbi_line   = self.data.bbi
        self.close_line = self.data.close
        self.ma60_line  = self.data.ma60
        macd = bt.indicators.MACD(self.data.close,
            period_me1=MACD_FAST, period_me2=MACD_SLOW, period_signal=MACD_SIGNAL)
        self.macd_line   = macd.macd
        self.signal_line = macd.signal
        self.atr_ind     = bt.indicators.ATR(self.data, period=ATR_PERIOD)
        self.state = 0; self.buy_bar = -1; self.add_order = None
        self.trail_stop = None; self.peak_close = None

    def _entry(self):
        if len(self) < 4: return False
        cross_up   = self.close_line[-1] < self.bbi_line[-1] and self.close_line[0] > self.bbi_line[0]
        bbi_slope  = self.bbi_line[0] > self.bbi_line[-3]
        above_ma60 = self.close_line[0] > self.ma60_line[0]
        macd_ok    = self.macd_line[0] > self.signal_line[0] or self.macd_line[0] > 0
        return cross_up and bbi_slope and above_ma60 and macd_ok

    def _exit(self):
        cross_down = self.close_line[-1] > self.bbi_line[-1] and self.close_line[0] < self.bbi_line[0]
        macd_dead  = self.macd_line[0] < self.signal_line[0] and self.macd_line[0] < 0
        return cross_down or macd_dead

    def _update_trail(self):
        c = self.close_line[0]
        if self.peak_close is None or c > self.peak_close: self.peak_close = c
        atr = self.atr_ind[0]
        if atr and atr > 0:
            ns = self.peak_close - ATR_MULTIPLIER * atr
            if self.trail_stop is None or ns > self.trail_stop: self.trail_stop = ns

    def _trail_hit(self):
        return self.trail_stop is not None and self.close_line[0] < self.trail_stop

    def notify_order(self, order):
        if order.status == order.Completed:
            if order.isbuy(): self.buy_bar = len(self)
            if self.add_order is not None and order.ref == self.add_order.ref:
                self.add_order = None; self.state = 2

    def next(self):
        if self.state == 0:
            if self._entry():
                cash = self.broker.getcash()
                size = int(cash * PYRAMID_FIRST_RATIO / self.close_line[0] / 100) * 100
                if size >= 100:
                    self.buy(size=size, exectype=bt.Order.Market)
                    self.buy_bar = len(self); self.state = 1
                    self.peak_close = self.close_line[0]; self.trail_stop = None
        elif self.state == 1:
            self._update_trail()
            if len(self) > self.buy_bar and (self._exit() or self._trail_hit()):
                self.order_target_size(target=0)
                self.state = 0; self.add_order = None
                self.trail_stop = None; self.peak_close = None; return
            pos = self.broker.getposition(self.data)
            if pos.size > 0:
                pct = (self.close_line[0] - pos.price) / pos.price
                if pct >= PYRAMID_ADD_TRIGGER and self.macd_line[0] > 0 and self.add_order is None:
                    cash = self.broker.getcash()
                    size = int(cash / self.close_line[0] / 100) * 100
                    if size >= 100: self.add_order = self.buy(size=size, exectype=bt.Order.Market)
        elif self.state == 2:
            self._update_trail()
            if len(self) > self.buy_bar and (self._exit() or self._trail_hit()):
                self.order_target_size(target=0)
                self.state = 0; self.add_order = None
                self.trail_stop = None; self.peak_close = None


class BBIv1Strategy(bt.Strategy):
    """v1 基准策略：仅收盘价穿越 BBI"""
    def __init__(self):
        self.bbi_line   = self.data.bbi
        self.close_line = self.data.close

    def next(self):
        pos = self.broker.getposition(self.data)
        cross_up   = self.close_line[-1] < self.bbi_line[-1] and self.close_line[0] > self.bbi_line[0]
        cross_down = self.close_line[-1] > self.bbi_line[-1] and self.close_line[0] < self.bbi_line[0]
        if pos.size == 0 and cross_up:
            self.buy()
        elif pos.size > 0 and cross_down:
            self.sell()


def run_segment(args):
    ts_code, parquet_path, start_date, end_date, strategy_cls = args
    try:
        df = pd.read_parquet(parquet_path)
        df.index = pd.to_datetime(df['trade_date'])
        df = df.sort_index()
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        if len(df) < 60:
            return None
        cerebro = bt.Cerebro()
        cerebro.addstrategy(strategy_cls)
        cerebro.adddata(BBIData(dataname=df))
        cerebro.broker.setcash(INIT_CASH)
        cerebro.broker.addcommissioninfo(AShareCommission())
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade')
        cerebro.addanalyzer(bt.analyzers.Returns, _name='returns', tann=252)
        cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        results = cerebro.run()
        strat = results[0]
        trade_an = strat.analyzers.trade.get_analysis()
        ret_an   = strat.analyzers.returns.get_analysis()
        dd_an    = strat.analyzers.drawdown.get_analysis()
        total = trade_an.get('total', {}).get('closed', 0)
        won   = trade_an.get('won', {}).get('total', 0)
        win_rate   = won / total if total > 0 else 0.0
        annual_ret = ret_an.get('rnorm100', 0.0)
        max_dd     = dd_an.get('max', {}).get('drawdown', 0.0)
        calmar     = annual_ret / max_dd if max_dd > 0 else 0.0
        return {'total': total, 'win_rate': win_rate, 'annual': annual_ret, 'max_dd': max_dd, 'calmar': calmar}
    except Exception:
        return None


def aggregate(results):
    valid = [r for r in results if r is not None and r['total'] > 0]
    if not valid:
        return {'stocks': 0, 'win_rate': 0, 'annual': 0, 'max_dd': 0, 'calmar': 0, 'trades': 0}
    return {
        'stocks':   len(valid),
        'win_rate': round(sum(r['win_rate'] for r in valid) / len(valid) * 100, 2),
        'annual':   round(sum(r['annual']   for r in valid) / len(valid), 4),
        'max_dd':   round(sum(r['max_dd']   for r in valid) / len(valid), 2),
        'calmar':   round(sum(r['calmar']   for r in valid) / len(valid), 4),
        'trades':   round(sum(r['total']    for r in valid) / len(valid), 1),
    }


def main():
    parquet_files = sorted(STOCK_DATA_DIR.glob('*.parquet'))
    print(f"分段验证：{len(parquet_files)} 只股票，{len(SEGMENTS)} 个市场环境段")

    seg_results = {}
    for seg_name, start, end in SEGMENTS:
        print(f"\n  [{seg_name}] {start} ~ {end}")
        # v2 ATR 策略
        args_v2 = [(p.stem, p, start, end, BBIATRStrategy) for p in parquet_files]
        with multiprocessing.Pool(N_WORKERS) as pool:
            r_v2 = pool.map(run_segment, args_v2)
        # v1 基准策略
        args_v1 = [(p.stem, p, start, end, BBIv1Strategy) for p in parquet_files]
        with multiprocessing.Pool(N_WORKERS) as pool:
            r_v1 = pool.map(run_segment, args_v1)
        seg_results[seg_name] = {
            'v2': aggregate(r_v2),
            'v1': aggregate(r_v1),
        }
        v2 = seg_results[seg_name]['v2']
        v1 = seg_results[seg_name]['v1']
        print(f"    v2: stocks={v2['stocks']}, win={v2['win_rate']:.1f}%, annual={v2['annual']:.2f}%, dd={v2['max_dd']:.1f}%, calmar={v2['calmar']:.4f}")
        print(f"    v1: stocks={v1['stocks']}, win={v1['win_rate']:.1f}%, annual={v1['annual']:.2f}%, dd={v1['max_dd']:.1f}%, calmar={v1['calmar']:.4f}")

    # 汇总对比表
    print("\n" + "="*90)
    print("  分段验证汇总：v2(ATR止盈) vs v1(基准)")
    print("="*90)
    col = 10
    header = f"  {'市场环境':<16} {'策略':>6} {'有效股':>{col}} {'胜率%':>{col}} {'年化%':>{col}} {'最大回撤%':>{col}} {'卡玛':>{col}} {'均交易':>{col}}"
    print(header)
    print("  " + "-"*84)
    for seg_name, _start, _end in SEGMENTS:
        for label, key in [('v2', 'v2'), ('v1', 'v1')]:
            r = seg_results[seg_name][key]
            prefix = f"  {seg_name:<16}" if label == 'v2' else f"  {'':16}"
            print(f"{prefix} {label:>6} {r['stocks']:>{col}} {r['win_rate']:>{col}.1f} {r['annual']:>{col}.2f} {r['max_dd']:>{col}.1f} {r['calmar']:>{col}.4f} {r['trades']:>{col}.1f}")
        # delta 行
        v2 = seg_results[seg_name]['v2']
        v1 = seg_results[seg_name]['v1']
        dwin = round(v2['win_rate'] - v1['win_rate'], 2)
        dann = round(v2['annual'] - v1['annual'], 4)
        ddd  = round(v2['max_dd'] - v1['max_dd'], 2)
        dcal = round(v2['calmar'] - v1['calmar'], 4)
        def fmt(v): return ('+' if v >= 0 else '') + str(v)
        print(f"  {'':16} {'Δ':>6} {'':>{col}} {fmt(dwin):>{col}} {fmt(dann):>{col}} {fmt(ddd):>{col}} {fmt(dcal):>{col}}")
        print("  " + "-"*84)

    print("\n  结论：")
    wins = 0
    for seg_name, _start, _end in SEGMENTS:
        v2 = seg_results[seg_name]['v2']
        v1 = seg_results[seg_name]['v1']
        if v2['calmar'] > v1['calmar']:
            wins += 1
            print(f"  ✅ {seg_name}：v2 卡玛优于 v1（{v2['calmar']:.4f} vs {v1['calmar']:.4f}）")
        else:
            print(f"  ⚠️  {seg_name}：v2 卡玛弱于 v1（{v2['calmar']:.4f} vs {v1['calmar']:.4f}）")
    print(f"\n  v2 在 {wins}/{len(SEGMENTS)} 个市场环境中优于 v1")


if __name__ == '__main__':
    main()
