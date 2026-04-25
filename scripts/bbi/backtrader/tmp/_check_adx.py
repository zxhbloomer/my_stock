import backtrader as bt
adx_names = [x for x in dir(bt.indicators) if 'adx' in x.lower() or 'directional' in x.lower() or 'dmi' in x.lower()]
print('ADX-related:', adx_names)
