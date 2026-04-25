"""
参数敏感性测试：ATR_MULTIPLIER × PYRAMID_ADD_TRIGGER 2D 网格搜索
验证策略是否对参数过拟合，找到稳健参数区间
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
    PYRAMID_FIRST_RATIO, ATR_PERIOD,
)

ATR_MULTIPLIERS     = [1.5, 2.0, 2.5, 3.0]
PYRAMID_TRIGGERS    = [0.03, 0.05, 0.08]


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


def make_strategy(atr_mult, pyramid_trigger):
    class S(bt.Strategy):
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
                ns = self.peak_close - atr_mult * atr
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
                    if pct >= pyramid_trigger and self.macd_line[0] > 0 and self.add_order is None:
                        cash = self.broker.getcash()
                        size = int(cash / self.close_line[0] / 100) * 100
                        if size >= 100: self.add_order = self.buy(size=size, exectype=bt.Order.Market)
            elif self.state == 2:
                self._update_trail()
                if len(self) > self.buy_bar and (self._exit() or self._trail_hit()):
                    self.order_target_size(target=0)
                    self.state = 0; self.add_order = None
                    self.trail_stop = None; self.peak_close = None
    return S


def run_one(args):
    ts_code, parquet_path, atr_mult, pyramid_trigger = args
    try:
        df = pd.read_parquet(parquet_path)
        df.index = pd.to_datetime(df['trade_date'])
        df = df.sort_index()
        cerebro = bt.Cerebro()
        cerebro.addstrategy(make_strategy(atr_mult, pyramid_trigger))
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


def run_grid(atr_mult, pyramid_trigger, parquet_files):
    args = [(p.stem, p, atr_mult, pyramid_trigger) for p in parquet_files]
    with multiprocessing.Pool(N_WORKERS) as pool:
        results = pool.map(run_one, args)
    valid = [r for r in results if r is not None and r['total'] > 0]
    if not valid:
        return {'win_rate': 0, 'annual': 0, 'max_dd': 0, 'calmar': 0, 'stocks': 0}
    return {
        'win_rate': round(sum(r['win_rate'] for r in valid) / len(valid) * 100, 2),
        'annual':   round(sum(r['annual']   for r in valid) / len(valid), 4),
        'max_dd':   round(sum(r['max_dd']   for r in valid) / len(valid), 2),
        'calmar':   round(sum(r['calmar']   for r in valid) / len(valid), 4),
        'stocks':   len(valid),
    }


def print_heatmap(metric_name, grid, atr_mults, triggers):
    col_w = 12
    header = f"{'ATR/Trigger':>14}" + "".join(f"{t*100:.0f}%".rjust(col_w) for t in triggers)
    print(f"\n  {metric_name}")
    print("  " + "-" * (14 + col_w * len(triggers)))
    print("  " + header)
    print("  " + "-" * (14 + col_w * len(triggers)))
    for am in atr_mults:
        row = f"  ATR×{am:<9}"
        for t in triggers:
            val = grid.get((am, t), {}).get(metric_name, 0)
            row += f"{val:>{col_w}}"
        print(row)
    print("  " + "-" * (14 + col_w * len(triggers)))


def main():
    parquet_files = sorted(STOCK_DATA_DIR.glob('*.parquet'))
    print(f"参数敏感性测试：{len(parquet_files)} 只股票，{len(ATR_MULTIPLIERS)*len(PYRAMID_TRIGGERS)} 组参数")
    print(f"ATR_MULTIPLIER: {ATR_MULTIPLIERS}")
    print(f"PYRAMID_ADD_TRIGGER: {PYRAMID_TRIGGERS}")

    grid = {}
    total_combos = len(ATR_MULTIPLIERS) * len(PYRAMID_TRIGGERS)
    done = 0
    for am in ATR_MULTIPLIERS:
        for pt in PYRAMID_TRIGGERS:
            done += 1
            print(f"  [{done}/{total_combos}] ATR×{am}, trigger={pt*100:.0f}% ...", end=' ', flush=True)
            r = run_grid(am, pt, parquet_files)
            grid[(am, pt)] = r
            print(f"calmar={r['calmar']:.4f}, win={r['win_rate']:.1f}%, dd={r['max_dd']:.1f}%")

    print("\n" + "="*60)
    print("  参数敏感性热力图")
    print("="*60)
    print_heatmap('calmar',   grid, ATR_MULTIPLIERS, PYRAMID_TRIGGERS)
    print_heatmap('win_rate', grid, ATR_MULTIPLIERS, PYRAMID_TRIGGERS)
    print_heatmap('annual',   grid, ATR_MULTIPLIERS, PYRAMID_TRIGGERS)
    print_heatmap('max_dd',   grid, ATR_MULTIPLIERS, PYRAMID_TRIGGERS)

    # 找最优参数组合
    best = max(grid.items(), key=lambda x: x[1]['calmar'])
    print(f"\n  最优参数（卡玛最高）：ATR_MULTIPLIER={best[0][0]}, PYRAMID_ADD_TRIGGER={best[0][1]*100:.0f}%")
    print(f"  calmar={best[1]['calmar']:.4f}, win_rate={best[1]['win_rate']:.1f}%, max_dd={best[1]['max_dd']:.1f}%")

    # 稳健性判断：calmar 标准差
    calmars = [v['calmar'] for v in grid.values()]
    import statistics
    std = statistics.stdev(calmars) if len(calmars) > 1 else 0
    mean = statistics.mean(calmars)
    cv = std / mean if mean != 0 else 0
    print(f"\n  卡玛变异系数 CV={cv:.3f}（<0.3 表示参数稳健，>0.5 表示过拟合风险）")


if __name__ == '__main__':
    main()
