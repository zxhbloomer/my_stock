import pandas as pd

v1  = pd.read_csv('v1/output/stats_summary.csv')
v2  = pd.read_csv('v2/output/stats_summary.csv')
tmp = pd.read_csv('tmp/output/stats_summary.csv')

def summary(df, label):
    h = df[df['trade_count'] > 0]
    return {
        'label':    label,
        'stocks':   len(h),
        'win_rate': round(h['win_rate'].mean()*100, 2),
        'annual':   round(h['annual_return_pct'].mean(), 4),
        'max_dd':   round(h['max_drawdown_pct'].mean(), 2),
        'trades':   round(h['trade_count'].mean(), 1),
        'hold':     round(h['avg_hold_days'].mean(), 1),
        'pl':       round(h['profit_loss_ratio'].mean(), 4),
        'calmar':   round(h['calmar_ratio'].mean(), 4),
        'win40':    int((h['win_rate'] > 0.4).sum()),
        'ann5':     int((h['annual_return_pct'] > 5).sum()),
        'dd40':     int((h['max_drawdown_pct'] < 40).sum()),
        'c01':      int((h['calmar_ratio'] > 0.1).sum()),
    }

r = [summary(v1,'v1'), summary(v2,'v2'), summary(tmp,'tmp')]
metrics = [
    ('有交易股票数','stocks'),
    ('平均胜率(%)','win_rate'),
    ('平均年化收益(%)','annual'),
    ('平均最大回撤(%)','max_dd'),
    ('平均交易次数','trades'),
    ('平均持仓天数','hold'),
    ('平均盈亏比','pl'),
    ('平均卡玛比率','calmar'),
    ('胜率>40%股票数','win40'),
    ('年化>5%股票数','ann5'),
    ('回撤<40%股票数','dd40'),
    ('卡玛>0.1股票数','c01'),
]
print(f"{'指标':<20} {'v1':>10} {'v2':>10} {'tmp(ATR)':>12} {'v2->tmp':>12}")
print('-'*66)
for name, key in metrics:
    v1v = r[0][key]
    v2v = r[1][key]
    tv  = r[2][key]
    if isinstance(tv, float):
        delta = round(tv - v2v, 4)
        sign  = '+' if delta >= 0 else ''
        print(f'{name:<20} {v1v:>10} {v2v:>10} {tv:>12} {sign+str(delta):>12}')
    else:
        delta = tv - v2v
        sign  = '+' if delta >= 0 else ''
        print(f'{name:<20} {v1v:>10} {v2v:>10} {tv:>12} {sign+str(delta):>12}')
