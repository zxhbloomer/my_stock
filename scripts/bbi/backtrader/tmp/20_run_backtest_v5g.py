# BBI v5g — ADX趋势门控 + ATR间距过滤（在v5e基础上）
# 核心改动：BBI死叉出场增加两层过滤，减少震荡市假信号
#
# 过滤层1 — ADX门控：ADX < ADX_THRESHOLD 时市场无方向，忽略BBI死叉
#   原理：A股震荡市占比高，ADX<20时死叉多为噪音
#
# 过滤层2 — ATR间距：死叉时价格与BBI距离 < ATR_GAP_MULT * ATR，视为均线粘合假穿越
#   原理：真实趋势反转时价格会明显跌破BBI，粘合穿越不可信
#
# ATR移动止盈、硬止损、MACD双死叉、筹码出场不受影响，仍然立即触发
#
# v5e baseline: ATR=4.5x, MIN_HOLD=20d, chip_exit>85, calmar≈0.196
# v5g adds: ADX(14)<20 忽略BBI死叉 + 死叉时|close-BBI|<0.3*ATR 忽略
import csv
import multiprocessing
import pandas as pd
import backtrader as bt
from pathlib import Path
import sys
import importlib.util
_v2_config_path = Path(__file__).parent.parent / 'v2' / 'config.py'
_spec = importlib.util.spec_from_file_location('v2_config', _v2_config_path)
_v2_cfg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_v2_cfg)
N_WORKERS          = _v2_cfg.N_WORKERS
INIT_CASH          = _v2_cfg.INIT_CASH
COMMISSION_BUY     = _v2_cfg.COMMISSION_BUY
COMMISSION_SELL    = _v2_cfg.COMMISSION_SELL
MIN_COMMISSION     = _v2_cfg.MIN_COMMISSION
MACD_FAST          = _v2_cfg.MACD_FAST
MACD_SLOW          = _v2_cfg.MACD_SLOW
MACD_SIGNAL        = _v2_cfg.MACD_SIGNAL
PYRAMID_FIRST_RATIO  = _v2_cfg.PYRAMID_FIRST_RATIO
PYRAMID_ADD_TRIGGER  = _v2_cfg.PYRAMID_ADD_TRIGGER
ATR_PERIOD         = _v2_cfg.ATR_PERIOD
HARD_STOP_LOSS     = _v2_cfg.HARD_STOP_LOSS

ATR_MULTIPLIER_V5G  = 4.5
MIN_HOLD_DAYS_V5G   = 20
BBI_DECLINE_BARS    = 5
CHIP_EXIT_THRESHOLD = 85.0
ADX_PERIOD          = 14    # ADX计算周期
ADX_THRESHOLD       = 20    # ADX低于此值视为震荡市，忽略BBI死叉
ATR_GAP_MULT        = 0.3   # 死叉时|close-BBI| < ATR_GAP_MULT*ATR 视为粘合假穿越
TMP_OUTPUT_DIR      = Path(__file__).parent / "output"
V5_STOCK_DATA_DIR   = TMP_OUTPUT_DIR / "stock_data_fast"
OUTPUT_SUBDIR       = TMP_OUTPUT_DIR / "v5g"


class BBIDataV5(bt.feeds.PandasData):
    lines = ('bbi', 'ma60', 'winner_rate',)
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
        ('winner_rate',  'winner_rate'),
    )


class AShareCommission(bt.CommInfoBase):
    params = (('stocklike', True), ('commtype', bt.CommInfoBase.COMM_PERC),)

    def _getcommission(self, size, price, pseudoexec):
        rate = COMMISSION_BUY if size > 0 else COMMISSION_SELL
        return max(abs(size) * price * rate, MIN_COMMISSION)


class AShareAllInSizer(bt.Sizer):
    def _getsizing(self, comminfo, cash, data, isbuy):
        if isbuy:
            size = int(cash / data.close[0] / 100) * 100
            return size if size >= 100 else 0
        return self.broker.getposition(data).size


class BBIV5gStrategy(bt.Strategy):
    def __init__(self):
        self.bbi_line    = self.data.bbi
        self.close_line  = self.data.close
        self.winner_line = self.data.winner_rate
        macd_ind = bt.indicators.MACD(
            self.data.close,
            period_me1=MACD_FAST, period_me2=MACD_SLOW, period_signal=MACD_SIGNAL,
        )
        self.macd_line   = macd_ind.macd
        self.signal_line = macd_ind.signal
        self.atr_ind     = bt.indicators.ATR(self.data, period=ATR_PERIOD)

        # ADX指标：用于判断趋势强度
        dmi = bt.indicators.DirectionalMovement(self.data, period=ADX_PERIOD)
        self.adx_line = dmi.adx

        self.state      = 0
        self.buy_bar    = -1
        self.add_order  = None
        self.trail_stop = None
        self.peak_close = None

    def _entry_signal(self):
        if len(self) < BBI_DECLINE_BARS + 1:
            return False
        cross_up  = self.close_line[-1] < self.bbi_line[-1] and self.close_line[0] > self.bbi_line[0]
        bbi_slope = self.bbi_line[0] > self.bbi_line[-3]
        macd_ok   = self.macd_line[0] > self.signal_line[0] or self.macd_line[0] > 0
        return cross_up and bbi_slope and macd_ok

    def _chip_exit(self):
        wr = self.winner_line[0]
        if wr != wr:  # NaN check
            return False
        return wr > CHIP_EXIT_THRESHOLD

    def _bbi_death_cross_filtered(self):
        """
        BBI死叉 + 双重过滤：
        1. ADX门控：ADX >= ADX_THRESHOLD 才允许死叉出场（趋势市才有效）
        2. ATR间距：|close - BBI| >= ATR_GAP_MULT * ATR（非粘合穿越）
        """
        cross_down = (self.close_line[-1] > self.bbi_line[-1] and
                      self.close_line[0] < self.bbi_line[0])
        if not cross_down:
            return False

        # 过滤层1：ADX门控 — 震荡市忽略死叉
        adx_val = self.adx_line[0]
        if adx_val != adx_val or adx_val < ADX_THRESHOLD:
            return False

        # 过滤层2：ATR间距 — 粘合穿越忽略
        atr_val = self.atr_ind[0]
        if atr_val and atr_val > 0:
            gap = abs(self.close_line[0] - self.bbi_line[0])
            if gap < ATR_GAP_MULT * atr_val:
                return False

        return True

    def _macd_exit(self):
        bbi_sustained_decline = (len(self) >= BBI_DECLINE_BARS + 1 and
                                 self.bbi_line[0] < self.bbi_line[-BBI_DECLINE_BARS])
        return (self.macd_line[0] < self.signal_line[0]
                and self.macd_line[0] < 0
                and bbi_sustained_decline)

    def _exit_signal(self):
        return self._bbi_death_cross_filtered() or self._macd_exit() or self._chip_exit()

    def _update_trail(self):
        c = self.close_line[0]
        if self.peak_close is None or c > self.peak_close:
            self.peak_close = c
        atr_val = self.atr_ind[0]
        if atr_val and atr_val > 0:
            new_stop = self.peak_close - ATR_MULTIPLIER_V5G * atr_val
            if self.trail_stop is None or new_stop > self.trail_stop:
                self.trail_stop = new_stop

    def _trail_triggered(self):
        return self.trail_stop is not None and self.close_line[0] < self.trail_stop

    def _reset_state(self):
        self.trail_stop = None
        self.peak_close = None

    def notify_order(self, order):
        if order.status == order.Completed:
            if order.isbuy():
                self.buy_bar = len(self)
            if self.add_order is not None and order.ref == self.add_order.ref:
                self.add_order = None
                self.state = 2

    def _should_exit(self):
        pos = self.broker.getposition(self.data)
        if pos.size > 0:
            if (self.close_line[0] - pos.price) / pos.price <= -HARD_STOP_LOSS:
                return True
        held = len(self) - self.buy_bar
        if held < MIN_HOLD_DAYS_V5G:
            return False
        if self._trail_triggered():
            return True
        return self._exit_signal()

    def next(self):
        if self.state == 0:
            if self._entry_signal():
                cash = self.broker.getcash()
                size = int(cash * PYRAMID_FIRST_RATIO / self.close_line[0] / 100) * 100
                if size >= 100:
                    self.buy(size=size, exectype=bt.Order.Market)
                    self.buy_bar    = len(self)
                    self.state      = 1
                    self.peak_close = self.close_line[0]
                    self.trail_stop = None

        elif self.state == 1:
            self._update_trail()
            if len(self) > self.buy_bar and self._should_exit():
                self.order_target_size(target=0)
                self.state = 0
                self.add_order = None
                self._reset_state()
                return
            pos = self.broker.getposition(self.data)
            if pos.size > 0:
                profit_pct = (self.close_line[0] - pos.price) / pos.price
                if profit_pct >= PYRAMID_ADD_TRIGGER and self.macd_line[0] > 0:
                    if self.add_order is None:
                        cash = self.broker.getcash()
                        size = int(cash / self.close_line[0] / 100) * 100
                        if size >= 100:
                            self.add_order = self.buy(size=size, exectype=bt.Order.Market)

        elif self.state == 2:
            self._update_trail()
            if len(self) > self.buy_bar and self._should_exit():
                self.order_target_size(target=0)
                self.state = 0
                self.add_order = None
                self._reset_state()


def run_single_stock(args):
    ts_code, name, parquet_path = args
    try:
        df = pd.read_parquet(parquet_path)
        df.index = pd.to_datetime(df['trade_date'])
        df = df.sort_index()

        if 'winner_rate' not in df.columns:
            return None, []

        cerebro = bt.Cerebro()
        cerebro.addstrategy(BBIV5gStrategy)
        data = BBIDataV5(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(INIT_CASH)
        cerebro.broker.addcommissioninfo(AShareCommission())
        cerebro.addsizer(AShareAllInSizer)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer,  _name='trade')
        cerebro.addanalyzer(bt.analyzers.Returns,        _name='returns', tann=252)
        cerebro.addanalyzer(bt.analyzers.DrawDown,       _name='drawdown')
        cerebro.addanalyzer(bt.analyzers.Transactions,   _name='txn')

        results  = cerebro.run()
        strat    = results[0]
        trade_an = strat.analyzers.trade.get_analysis()
        ret_an   = strat.analyzers.returns.get_analysis()
        dd_an    = strat.analyzers.drawdown.get_analysis()
        txn_an   = strat.analyzers.txn.get_analysis()

        total_trades = trade_an.get('total', {}).get('closed', 0)
        won          = trade_an.get('won',   {}).get('total',  0)
        win_rate     = won / total_trades if total_trades > 0 else 0.0
        gross_won    = trade_an.get('won',  {}).get('pnl', {}).get('total', 0.0)
        gross_lost   = abs(trade_an.get('lost', {}).get('pnl', {}).get('total', 0.0))
        pl_ratio     = gross_won / gross_lost if gross_lost > 0 else 0.0
        annual_ret   = ret_an.get('rnorm100', 0.0)
        max_dd       = dd_an.get('max', {}).get('drawdown', 0.0)
        calmar       = annual_ret / max_dd if max_dd > 0 else 0.0
        avg_hold     = trade_an.get('len', {}).get('average', 0.0)

        trades_out = []
        open_trade = None
        for dt_obj in sorted(txn_an.keys()):
            for txn in txn_an[dt_obj]:
                size, price = txn[0], txn[1]
                date_str = dt_obj.strftime('%Y-%m-%d')
                if size > 0:
                    if open_trade is None:
                        open_trade = {'buy_date': date_str, 'buy_price': round(price, 4),
                                      'size': abs(size), 'pyramided': False,
                                      'orders': [{'date': date_str, 'price': round(price, 4),
                                                  'size': abs(size), 'type': 'open'}]}
                    else:
                        total_size = open_trade['size'] + abs(size)
                        avg_price  = (open_trade['buy_price'] * open_trade['size'] + price * abs(size)) / total_size
                        open_trade.update({'buy_price': round(avg_price, 4), 'size': total_size, 'pyramided': True})
                        open_trade['orders'].append({'date': date_str, 'price': round(price, 4),
                                                     'size': abs(size), 'type': 'add'})
                elif size < 0 and open_trade:
                    hold    = (dt_obj - pd.Timestamp(open_trade['buy_date'])).days
                    ret_pct = round((price - open_trade['buy_price']) / open_trade['buy_price'] * 100, 4)
                    pnl     = round((price - open_trade['buy_price']) * open_trade['size'], 2)
                    trades_out.append({'ts_code': ts_code, 'name': name,
                                       'buy_date': open_trade['buy_date'], 'buy_price': open_trade['buy_price'],
                                       'sell_date': date_str, 'sell_price': round(price, 4),
                                       'return_pct': ret_pct, 'hold_days': hold, 'pnl': pnl,
                                       'pyramided': open_trade['pyramided'],
                                       'orders': open_trade['orders'], 'sell_size': abs(size)})
                    open_trade = None

        if open_trade:
            try:
                df_last    = pd.read_parquet(parquet_path, columns=['trade_date', 'close_qfq'])
                last_price = round(float(df_last.sort_values('trade_date')['close_qfq'].iloc[-1]), 4)
                last_date  = pd.Timestamp(df_last['trade_date'].max())
            except Exception:
                last_price = open_trade['buy_price']
                last_date  = pd.Timestamp(open_trade['buy_date'])
            ret_pct = round((last_price - open_trade['buy_price']) / open_trade['buy_price'] * 100, 4)
            trades_out.append({'ts_code': ts_code, 'name': name,
                               'buy_date': open_trade['buy_date'], 'buy_price': open_trade['buy_price'],
                               'sell_date': 'open', 'sell_price': last_price, 'return_pct': ret_pct,
                               'hold_days': (last_date - pd.Timestamp(open_trade['buy_date'])).days,
                               'pnl': round((last_price - open_trade['buy_price']) * open_trade['size'], 2),
                               'pyramided': open_trade.get('pyramided', False),
                               'orders': open_trade.get('orders', []), 'sell_size': 0})

        closed      = [t for t in trades_out if t['sell_date'] != 'open']
        avg_ret_pct = round(sum(t['return_pct'] for t in closed) / len(closed), 4) if closed else 0.0

        return {'ts_code': ts_code, 'name': name, 'trade_count': total_trades,
                'win_rate': round(win_rate, 4), 'avg_return_pct': avg_ret_pct,
                'profit_loss_ratio': round(pl_ratio, 4), 'annual_return_pct': round(annual_ret, 4),
                'max_drawdown_pct': round(max_dd, 4), 'calmar_ratio': round(calmar, 4),
                'avg_hold_days': round(avg_hold, 1)}, trades_out

    except Exception as e:
        print('ERROR {}: {}'.format(ts_code, e))
        return None, []


def main():
    OUTPUT_SUBDIR.mkdir(parents=True, exist_ok=True)
    parquet_files = sorted(V5_STOCK_DATA_DIR.glob('*.parquet'))
    if not parquet_files:
        print('ERROR: No parquet files in {}'.format(V5_STOCK_DATA_DIR))
        return

    args_list = []
    for p in parquet_files:
        ts_code = p.stem
        try:
            name = pd.read_parquet(p, columns=['name'])['name'].iloc[0]
        except Exception:
            name = ''
        args_list.append((ts_code, name, p))

    print('[v5g] {} stocks | ATR={}x | MIN_HOLD={}d | chip_exit>{} | ADX_thresh={} | ATR_gap={}x'.format(
        len(args_list), ATR_MULTIPLIER_V5G, MIN_HOLD_DAYS_V5G, CHIP_EXIT_THRESHOLD,
        ADX_THRESHOLD, ATR_GAP_MULT))

    with multiprocessing.Pool(N_WORKERS) as pool:
        all_results = pool.map(run_single_stock, args_list)

    stats_rows  = [s for s, _ in all_results if s is not None]
    trades_rows = [t for _, tl in all_results for t in tl]

    fields_s = ['ts_code','name','trade_count','win_rate','avg_return_pct',
                'profit_loss_ratio','annual_return_pct','max_drawdown_pct','calmar_ratio','avg_hold_days']
    fields_t = ['ts_code','name','buy_date','buy_price','sell_date','sell_price',
                'return_pct','hold_days','pnl','pyramided','orders','sell_size']

    with open(OUTPUT_SUBDIR / 'stats_summary.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields_s); w.writeheader(); w.writerows(stats_rows)
    with open(OUTPUT_SUBDIR / 'trades_detail.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields_t); w.writeheader(); w.writerows(trades_rows)

    print('Done. {} stocks, {} trades.'.format(len(stats_rows), len(trades_rows)))
    print('  stats -> {}'.format(OUTPUT_SUBDIR / 'stats_summary.csv'))


if __name__ == '__main__':
    main()
