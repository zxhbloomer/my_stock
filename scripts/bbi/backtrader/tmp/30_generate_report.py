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
    df['bbi_qfq'] = df['bbi_qfq'].bfill().fillna(0)
    df['ma60']    = df['ma60'].bfill().fillna(0)
    for col in ['open_qfq', 'high_qfq', 'low_qfq', 'close_qfq']:
        df[col] = df[col].ffill().fillna(0)

    # MACD(12,26,9) calculated from close
    close = df['close_qfq']
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif   = ema12 - ema26
    dea   = dif.ewm(span=9, adjust=False).mean()
    hist  = (dif - dea) * 2

    dates   = [str(d) for d in df['trade_date'].tolist()]
    candles = df[['open_qfq', 'close_qfq', 'low_qfq', 'high_qfq']].round(4).values.tolist()
    bbi     = df['bbi_qfq'].round(4).tolist()
    ma60    = df['ma60'].round(4).tolist()
    macd_dif  = dif.round(4).tolist()
    macd_dea  = dea.round(4).tolist()
    macd_hist = hist.round(4).tolist()

    sub = df_trades[df_trades['ts_code'] == ts_code]

    # Flatten per-order buy markers: [date, price, size, type]
    import ast
    buy_orders = []
    for _, row in sub.iterrows():
        orders = row.get('orders', []) if 'orders' in sub.columns else []
        if isinstance(orders, str):
            try:
                orders = ast.literal_eval(orders)
            except Exception:
                orders = []
        if not orders:
            # fallback: single entry from buy_date/buy_price
            buy_orders.append([row['buy_date'], row['buy_price'], 0, '建仓'])
        else:
            for o in orders:
                buy_orders.append([o['date'], o['price'], o['size'], o['type']])

    sells = sub[['sell_date', 'sell_price']].values.tolist()
    sell_sizes = sub['sell_size'].tolist() if 'sell_size' in sub.columns else [0] * len(sub)
    pyramided_flags = sub['pyramided'].tolist() if 'pyramided' in sub.columns else [False] * len(sub)

    return {
        'dates': dates, 'candles': candles,
        'bbi': bbi, 'ma60': ma60,
        'macd_dif': macd_dif, 'macd_dea': macd_dea, 'macd_hist': macd_hist,
        'buy_orders': buy_orders,
        'sells': sells, 'sell_sizes': sell_sizes,
        'pyramided': pyramided_flags,
    }


def make_ranking_html(df_sorted, total_stocks, avg_win_rate, avg_annual_ret,
                      hist_labels, hist_counts):
    rows = ''
    for i, row in df_sorted.iterrows():
        rows += (
            '<tr onclick="window.open(\'report_detail.html?stock='
            + row.ts_code + '\',\'_blank\')" style="cursor:pointer">'
            + '<td>' + str(i + 1) + '</td>'
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
        'title:{text:\'胜率分布\',left:\'center\'},'
        'xAxis:{type:\'category\',data:' + json.dumps(hist_labels) + '},'
        'yAxis:{type:\'value\',name:\'股票数\'},'
        'series:[{type:\'bar\',data:' + json.dumps(hist_counts) + ',itemStyle:{color:\'#3498db\'}}]'
        '});'
    )
    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<title>BBI tmp(ATR止盈)回测排名</title>'
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
        '<style>' + css + '</style></head><body>'
        '<div class="header"><h2 style="margin:0">BBI tmp(ATR止盈)回测排名</h2>'
        '<div class="stats-bar">'
        '<div class="stat">总股票数: <span>' + str(total_stocks) + '</span></div>'
        '<div class="stat">平均胜率: <span>' + str(avg_win_rate) + '%</span></div>'
        '<div class="stat">平均年化收益: <span>' + str(avg_annual_ret) + '%</span></div>'
        '</div></div>'
        '<input id="search" placeholder="搜索代码或名称..." oninput="filterTable(this.value)">'
        '<table id="rankTable"><thead><tr>'
        '<th onclick="sortTable(0)">排名</th>'
        '<th onclick="sortTable(1)">代码</th>'
        '<th onclick="sortTable(2)">名称</th>'
        '<th onclick="sortTable(3)">交易次数</th>'
        '<th onclick="sortTable(4)">胜率</th>'
        '<th onclick="sortTable(5)">平均收益率</th>'
        '<th onclick="sortTable(6)">盈亏比</th>'
        '<th onclick="sortTable(7)">年化收益率</th>'
        '<th onclick="sortTable(8)">最大回撤</th>'
        '<th onclick="sortTable(9)">卡玛比率</th>'
        '<th onclick="sortTable(10)">平均持仓天数</th>'
        '</tr></thead>'
        '<tbody id="tableBody">' + rows + '</tbody></table>'
        '<div id="histogram"></div>'
        '<script>' + js_filter + js_sort + js_chart + '</script>'
        '</body></html>'
    )
    return html


def make_detail_html(df_sorted, df_trades, total_stocks, avg_win_rate, avg_annual_ret):
    # 左侧排名表格行
    rank_rows = ''
    for i, row in df_sorted.iterrows():
        up = row.annual_return_pct >= 0
        ret_color = '#e74c3c' if up else '#2ecc71'
        rank_rows += (
            '<tr onclick="loadStock(\'' + row.ts_code + '\')" data-code="' + row.ts_code + '">'
            + '<td>' + str(i + 1) + '</td>'
            + '<td>' + row.ts_code + '</td>'
            + '<td>' + row['name'] + '</td>'
            + '<td>' + str(int(row.trade_count)) + '</td>'
            + '<td>' + f'{row.win_rate:.1%}' + '</td>'
            + '<td>' + f'{row.avg_return_pct:.2f}%' + '</td>'
            + '<td>' + f'{row.profit_loss_ratio:.2f}' + '</td>'
            + '<td style="color:' + ret_color + '">' + f'{row.annual_return_pct:.2f}%' + '</td>'
            + '<td>' + f'{row.max_drawdown_pct:.2f}%' + '</td>'
            + '<td>' + f'{row.calmar_ratio:.2f}' + '</td>'
            + '<td>' + f'{row.avg_hold_days:.1f}' + '</td>'
            + '</tr>'
        )

    stats_js = ('const statsData = '
        + json.dumps(
            df_sorted.set_index('ts_code')[
                ['trade_count', 'win_rate', 'annual_return_pct', 'max_drawdown_pct', 'calmar_ratio']
            ].to_dict('index')
        ) + ';')

    trades_parts = ['const tradesData = {};']
    for ts_code in df_sorted['ts_code']:
        cols = ['buy_date', 'buy_price', 'sell_date', 'sell_price', 'return_pct', 'hold_days', 'pnl']
        for extra in ['pyramided', 'orders', 'sell_size']:
            if extra in df_trades.columns:
                cols.append(extra)
        sub_df = df_trades[df_trades['ts_code'] == ts_code][cols]
        # parse orders column if stored as string
        import ast as _ast
        records = []
        for _, row in sub_df.iterrows():
            rec = row.to_dict()
            if 'orders' in rec and isinstance(rec['orders'], str):
                try:
                    rec['orders'] = _ast.literal_eval(rec['orders'])
                except Exception:
                    rec['orders'] = []
            records.append(rec)
        trades_parts.append('tradesData["' + ts_code + '"] = ' + json.dumps(records) + ';')
    trades_js = '\n'.join(trades_parts)

    css = (
        '*{box-sizing:border-box;margin:0;padding:0}'
        'body{font-family:Arial,sans-serif;display:flex;flex-direction:column;height:100vh;background:#f0f2f5}'
        '.header{background:#2c3e50;color:white;padding:12px 20px;flex-shrink:0}'
        '.header-bar{display:flex;align-items:baseline;gap:32px;margin-top:4px}'
        '.header-stat{font-size:1em}.header-stat span{font-weight:bold;color:#f39c12}'
        '.main{display:flex;flex:1;overflow:hidden}'
        '.left-panel{width:42%;border-right:1px solid #ddd;display:flex;flex-direction:column;background:white;min-width:0}'
        '.left-toolbar{padding:6px 8px;border-bottom:1px solid #eee;flex-shrink:0}'
        '.left-toolbar input{width:100%;padding:5px 8px;border:1px solid #ccc;border-radius:4px;font-size:.85em}'
        '.left-table-wrap{flex:1;overflow:auto}'
        '.left-table-wrap table{width:max-content;min-width:100%;border-collapse:collapse;font-size:.82em}'
        '.left-table-wrap th{background:#34495e;color:white;padding:7px 6px;position:sticky;top:0;text-align:center;cursor:pointer;white-space:nowrap;user-select:none;z-index:1}'
        '.left-table-wrap th:hover{background:#2c3e50}'
        '.left-table-wrap td{padding:6px 6px;border-bottom:1px solid #eee;white-space:nowrap}'
        '.left-table-wrap tr{cursor:pointer}'
        '.left-table-wrap tr:hover td{background:#ecf0f1}'
        '.left-table-wrap tr.active td{background:#d5e8f7 !important}'
        '.right-panel{flex:1;display:flex;flex-direction:column;overflow:hidden;padding:12px;gap:12px}'
        '.stats-cards{display:flex;gap:10px;flex-shrink:0}'
        '.card{background:white;border-radius:8px;padding:10px 16px;flex:1;text-align:center}'
        '.card .label{font-size:.75em;color:#888}'
        '.card .value{font-size:1.3em;font-weight:bold;color:#2c3e50}'
        '#kline-chart{background:white;border-radius:8px;flex:0 0 60%;min-height:0}'
        '.trade-table-wrap{background:white;border-radius:8px;flex:1;overflow-y:auto;min-height:0}'
        '.table-toolbar{display:flex;justify-content:flex-end;padding:6px 8px;border-bottom:1px solid #eee}'
        '.btn-reset{padding:4px 12px;background:#34495e;color:white;border:none;border-radius:4px;cursor:pointer;font-size:.82em}'
        '.btn-reset:hover{background:#2c3e50}'
        '.trade-table-wrap table{width:100%;border-collapse:collapse;font-size:.85em}'
        '.trade-table-wrap th{background:#34495e;color:white;padding:8px;position:sticky;top:0;text-align:center}'
        'td{padding:7px 8px;border-bottom:1px solid #eee;cursor:pointer}'
        'td.td-left{text-align:left}'
        'td.td-right{text-align:right}'
        'td.td-center{text-align:center}'
        '.trade-table-wrap tr:hover td{background:#f5f5f5}'
        'tr.selected td{background:#fff3cd !important}'
    )

    js_main = r"""
const chartMain = echarts.init(document.getElementById('kline-chart'));
let currentData = null;
let currentCode = null;
let selectedRow = null;
let rankSortDir = {};

function fmt(n) { return n.toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2}); }

function loadStock(code) {
  document.querySelectorAll('#rankBody tr').forEach(r => r.classList.remove('active'));
  const el = document.querySelector('#rankBody tr[data-code="' + code + '"]');
  if (el) { el.classList.add('active'); el.scrollIntoView({block:'nearest'}); }
  selectedRow = null;
  const s = statsData[code] || {};
  document.getElementById('c-trades').textContent  = s.trade_count != null ? s.trade_count : '--';
  document.getElementById('c-winrate').textContent = s.win_rate    != null ? (s.win_rate*100).toFixed(1)+'%' : '--';
  document.getElementById('c-annret').textContent  = s.annual_return_pct != null ? s.annual_return_pct.toFixed(2)+'%' : '--';
  document.getElementById('c-maxdd').textContent   = s.max_drawdown_pct  != null ? s.max_drawdown_pct.toFixed(2)+'%'  : '--';
  document.getElementById('c-calmar').textContent  = s.calmar_ratio      != null ? s.calmar_ratio.toFixed(2)           : '--';
  fetch('kline_data/' + code + '.json').then(r => r.json()).then(data => {
    currentData = data;
    renderChart(data, null, null);
    renderTrades(code, data);
  });
}

function filterRank(q) {
  q = q.toLowerCase();
  document.querySelectorAll('#rankBody tr').forEach(r => {
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

function sortRank(col) {
  const tbody = document.getElementById('rankBody');
  const rows = Array.from(tbody.rows).filter(r => r.style.display !== 'none');
  rankSortDir[col] = !rankSortDir[col];
  rows.sort((a, b) => {
    const av = a.cells[col].textContent.replace('%','').replace(/,/g,'');
    const bv = b.cells[col].textContent.replace('%','').replace(/,/g,'');
    const an = parseFloat(av), bn = parseFloat(bv);
    if (!isNaN(an) && !isNaN(bn)) return rankSortDir[col] ? bn - an : an - bn;
    return rankSortDir[col] ? bv.localeCompare(av) : av.localeCompare(bv);
  });
  rows.forEach(r => tbody.appendChild(r));
}

function makeBuyPoints(data, filterBuyDate) {
  const orders = data.buy_orders || [];
  return orders
    .filter(o => filterBuyDate == null || o[0] === filterBuyDate)
    .map(o => {
      const di = data.dates.indexOf(o[0]);
      const kline = di >= 0 ? data.candles[di] : null;
      const low = kline ? kline[2] : o[1];
      const isAdd = o[3] === '加仓';
      const sizeLabel = o[2] > 0 ? (isAdd ? '+'+o[2]+'(加)' : '+'+o[2]) : (isAdd ? '加仓' : '建仓');
      return {
        value: [o[0], low],
        itemStyle: { color: isAdd ? '#f39c12' : '#e74c3c' },
        label: { show: true, formatter: sizeLabel, position: 'bottom',
                 color: isAdd ? '#f39c12' : '#e74c3c', fontSize: 10, fontWeight: 'bold' }
      };
    });
}

function makeSellPoints(data, filterSellDate) {
  const sellSizes = data.sell_sizes || [];
  return data.sells
    .filter(s => filterSellDate == null || s[0] === filterSellDate)
    .map((s, i) => {
      const di = data.dates.indexOf(s[0]);
      const kline = di >= 0 ? data.candles[di] : null;
      const high = kline ? kline[3] : s[1];
      const sz = sellSizes[i] > 0 ? '-'+sellSizes[i] : '卖出';
      return { value: [s[0], high], label: { show: true, formatter: sz, position: 'top', color: '#2ecc71', fontSize: 10, fontWeight: 'bold' } };
    });
}

function renderChart(data, buyDate, sellDate) {
  const startIdx = Math.max(0, data.dates.length - 504);
  const closes = data.candles.map(c => c[1]);
  const buyPoints  = makeBuyPoints(data, buyDate);
  const sellPoints = makeSellPoints(data, sellDate);

  // MACD histogram colors: positive=red, negative=green (A-share convention)
  const macdHistData = (data.macd_hist || []).map((v, i) => ({
    value: v,
    itemStyle: { color: v >= 0 ? '#e74c3c' : '#2ecc71' }
  }));

  chartMain.setOption({
    animation: false,
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['K线', '收盘价', 'BBI', 'MA60', '买入', '卖出', 'DIF', 'DEA'], top: 4 },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], startValue: startIdx, endValue: data.dates.length - 1 },
      { type: 'slider', xAxisIndex: [0, 1], startValue: startIdx, endValue: data.dates.length - 1, bottom: 4 }
    ],
    grid: [
      { left: 60, right: 20, top: 36, bottom: '32%' },
      { left: 60, right: 20, top: '72%', bottom: 48 }
    ],
    xAxis: [
      { type: 'category', data: data.dates, scale: true, gridIndex: 0, axisLabel: { show: false } },
      { type: 'category', data: data.dates, scale: true, gridIndex: 1 }
    ],
    yAxis: [
      { type: 'value', scale: true, gridIndex: 0, splitNumber: 4 },
      { type: 'value', scale: true, gridIndex: 1, splitNumber: 3 }
    ],
    series: [
      { name: 'K线', type: 'candlestick', data: data.candles, xAxisIndex: 0, yAxisIndex: 0,
        itemStyle: { color: '#e74c3c', color0: '#2ecc71', borderColor: '#e74c3c', borderColor0: '#2ecc71' } },
      { name: '收盘价', type: 'line', data: data.candles.map(c => c[1]), xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { color: '#8e44ad', width: 1 }, showSymbol: false, smooth: false },
      { name: 'BBI', type: 'line', data: data.bbi, xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { color: '#f39c12', width: 1.5 }, showSymbol: false, smooth: true },
      { name: 'MA60', type: 'line', data: data.ma60, xAxisIndex: 0, yAxisIndex: 0,
        lineStyle: { color: '#3498db', width: 1.2, type: 'dashed' }, showSymbol: false },
      { name: '买入', type: 'scatter', data: buyPoints, xAxisIndex: 0, yAxisIndex: 0,
        symbol: 'triangle', symbolSize: 10, itemStyle: { color: '#e74c3c' }, label: { show: true } },
      { name: '卖出', type: 'scatter', data: sellPoints, xAxisIndex: 0, yAxisIndex: 0,
        symbol: 'triangle', symbolRotate: 180, symbolSize: 10, itemStyle: { color: '#2ecc71' }, label: { show: true } },
      { name: 'MACD柱', type: 'bar', data: macdHistData, xAxisIndex: 1, yAxisIndex: 1,
        barMaxWidth: 6 },
      { name: 'DIF', type: 'line', data: data.macd_dif, xAxisIndex: 1, yAxisIndex: 1,
        lineStyle: { color: '#e74c3c', width: 1 }, showSymbol: false },
      { name: 'DEA', type: 'line', data: data.macd_dea, xAxisIndex: 1, yAxisIndex: 1,
        lineStyle: { color: '#2ecc71', width: 1 }, showSymbol: false }
    ]
  }, true);
}

// tradeRowMap: date -> [{tr, tradeIdx}] for chart->table linking
let tradeRowMap = {};

function highlightTableRow(date) {
  const entries = tradeRowMap[date];
  if (!entries || !entries.length) return;
  // clear previous
  if (selectedRow) { selectedRow.classList.remove('selected'); selectedRow = null; }
  const {tr, tradeIdx} = entries[0];
  selectedRow = tr;
  tr.classList.add('selected');
  tr.scrollIntoView({block: 'nearest', behavior: 'smooth'});
  // zoom chart to trade group
  const trades = tradesData[currentCode] || [];
  const t = trades[tradeIdx];
  if (t && currentData) zoomToTrade(currentData.dates, t.buy_date, t.sell_date);
}

function renderTrades(code, data) {
  const trades = tradesData[code] || [];
  const tbody = document.getElementById('tradeBody');
  tbody.innerHTML = '';
  tradeRowMap = {};
  currentCode = code;

  function registerRow(date, tr, tradeIdx) {
    if (!tradeRowMap[date]) tradeRowMap[date] = [];
    tradeRowMap[date].push({tr, tradeIdx});
  }

  function makeClickHandler(tr, t, tradeIdx) {
    return () => {
      if (t.sell_date === '持仓中') return;
      if (selectedRow === tr) {
        selectedRow.classList.remove('selected');
        selectedRow = null;
        renderChart(data, null, null);
        zoomToDefault(data);
      } else {
        if (selectedRow) selectedRow.classList.remove('selected');
        selectedRow = tr;
        tr.classList.add('selected');
        renderChart(data, t.buy_date, t.sell_date);
        zoomToTrade(data.dates, t.buy_date, t.sell_date);
      }
    };
  }

  trades.forEach((t, tradeIdx) => {
    const holding = t.sell_date === '持仓中';
    const up = t.return_pct >= 0;
    const retColor = holding ? '#2980b9' : (up ? '#e74c3c' : '#2ecc71');
    const orders = t.orders || [];

    // Group header separator
    const groupSep = document.createElement('tr');
    groupSep.innerHTML = '<td colspan="9" style="padding:0;background:#34495e;border:none;height:3px"></td>';
    tbody.appendChild(groupSep);

    // Buy rows (建仓/加仓)
    let runningCost = 0, runningSize = 0;
    orders.forEach(o => {
      const isAdd = o.type === '加仓';
      runningSize += o.size;
      runningCost = isAdd
        ? (runningCost * (runningSize - o.size) + o.price * o.size) / runningSize
        : o.price;
      const amount = o.price * o.size;
      const bgColor = isAdd ? '#fff8ee' : '#f0f7ff';
      const badge = isAdd
        ? '<span style="background:#f39c12;color:white;border-radius:3px;padding:1px 5px;font-size:.8em">加仓</span>'
        : '<span style="background:#3498db;color:white;border-radius:3px;padding:1px 5px;font-size:.8em">建仓</span>';
      const tr = document.createElement('tr');
      tr.style.background = bgColor;
      tr.style.cursor = 'pointer';
      tr.innerHTML =
        '<td class="td-center">'+badge+'</td>'
        +'<td class="td-center">'+o.date+'</td>'
        +'<td class="td-right">'+o.price.toFixed(4)+'</td>'
        +'<td class="td-right" style="color:#27ae60">+'+o.size+'</td>'
        +'<td class="td-right">'+fmt(amount)+'</td>'
        +'<td class="td-right" style="color:#888">'+runningCost.toFixed(4)+'</td>'
        +'<td></td><td></td><td></td>';
      tr.onclick = makeClickHandler(tr, t, tradeIdx);
      registerRow(o.date, tr, tradeIdx);
      tbody.appendChild(tr);
    });

    // Sell row
    const sellAmount = t.sell_price * (t.sell_size || 0);
    const sellBg = holding ? '#eaf4fb' : (up ? '#fff5f5' : '#f5fff5');
    const sellBadge = holding
      ? '<span style="background:#2980b9;color:white;border-radius:3px;padding:1px 5px;font-size:.8em">持仓中</span>'
      : '<span style="background:#e74c3c;color:white;border-radius:3px;padding:1px 5px;font-size:.8em">卖出</span>';
    const sellRow = document.createElement('tr');
    sellRow.style.background = sellBg;
    sellRow.style.cursor = holding ? 'default' : 'pointer';
    sellRow.innerHTML =
      '<td class="td-center">'+sellBadge+'</td>'
      +'<td class="td-center" style="color:'+(holding?'#2980b9':'')+'">'+t.sell_date+'</td>'
      +'<td class="td-right">'+t.sell_price+'</td>'
      +'<td class="td-right" style="color:#e74c3c">'+(t.sell_size>0?'-'+t.sell_size:'—')+'</td>'
      +'<td class="td-right">'+(sellAmount>0?fmt(sellAmount):'—')+'</td>'
      +'<td></td>'
      +'<td class="td-right" style="color:'+retColor+'">'+t.return_pct.toFixed(2)+'%</td>'
      +'<td class="td-center">'+t.hold_days+'</td>'
      +'<td class="td-right" style="color:'+retColor+'">'+fmt(t.pnl)+'</td>';
    sellRow.onclick = makeClickHandler(sellRow, t, tradeIdx);
    registerRow(t.sell_date, sellRow, tradeIdx);
    tbody.appendChild(sellRow);
  });

  // Wire up chart click -> table highlight
  chartMain.off('click');
  chartMain.on('click', params => {
    if (params.componentType === 'series' && params.seriesName !== 'K线'
        && params.seriesName !== '收盘价' && params.seriesName !== 'BBI'
        && params.seriesName !== 'MA60' && params.seriesName !== 'MACD柱'
        && params.seriesName !== 'DIF' && params.seriesName !== 'DEA') {
      const date = Array.isArray(params.value) ? params.value[0] : null;
      if (date) highlightTableRow(date);
    }
  });
}

function zoomToTrade(dates, buyDate, sellDate) {
  const bi = dates.indexOf(buyDate), si = dates.indexOf(sellDate);
  if (bi < 0) return;
  const end = si >= 0 ? si : bi;
  chartMain.dispatchAction({type:'dataZoom',
    startValue:Math.max(0,bi-10), endValue:Math.min(dates.length-1,end+10)});
}

function zoomToDefault(data) {
  const startIdx = Math.max(0, data.dates.length - 504);
  chartMain.dispatchAction({type:'dataZoom', startValue:startIdx, endValue:data.dates.length-1});
}

function resetSelection() {
  if (selectedRow) { selectedRow.classList.remove('selected'); selectedRow = null; }
  if (currentData) { renderChart(currentData, null, null); zoomToDefault(currentData); }
}

const params = new URLSearchParams(window.location.search);
const initStock = params.get('stock');
if (initStock) loadStock(initStock);
else { const first = document.querySelector('#rankBody tr'); if (first) first.click(); }
"""

    html = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">'
        '<title>BBI tmp(ATR止盈)回测详情</title>'
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
        '<style>' + css + '</style></head><body>'
        '<div class="header">'
        '<h3 style="margin:0">BBI tmp(ATR止盈)回测详情</h3>'
        '<div class="header-bar">'
        '<div class="header-stat">总股票数: <span>' + str(total_stocks) + '</span></div>'
        '<div class="header-stat">平均胜率: <span>' + str(avg_win_rate) + '%</span></div>'
        '<div class="header-stat">平均年化收益: <span>' + str(avg_annual_ret) + '%</span></div>'
        '</div></div>'
        '<div class="main">'
        '<div class="left-panel">'
        '<div class="left-toolbar"><input placeholder="搜索代码或名称..." oninput="filterRank(this.value)"></div>'
        '<div class="left-table-wrap">'
        '<table><thead><tr>'
        '<th onclick="sortRank(0)">排名</th>'
        '<th onclick="sortRank(1)">代码</th>'
        '<th onclick="sortRank(2)">名称</th>'
        '<th onclick="sortRank(3)">交易次数</th>'
        '<th onclick="sortRank(4)">胜率</th>'
        '<th onclick="sortRank(5)">平均收益率</th>'
        '<th onclick="sortRank(6)">盈亏比</th>'
        '<th onclick="sortRank(7)">年化收益率</th>'
        '<th onclick="sortRank(8)">最大回撤</th>'
        '<th onclick="sortRank(9)">卡玛比率</th>'
        '<th onclick="sortRank(10)">平均持仓天数</th>'
        '</tr></thead>'
        '<tbody id="rankBody">' + rank_rows + '</tbody></table>'
        '</div></div>'
        '<div class="right-panel">'
        '<div class="stats-cards">'
        '<div class="card"><div class="label">交易次数</div><div class="value" id="c-trades">--</div></div>'
        '<div class="card"><div class="label">胜率</div><div class="value" id="c-winrate">--</div></div>'
        '<div class="card"><div class="label">年化收益</div><div class="value" id="c-annret">--</div></div>'
        '<div class="card"><div class="label">最大回撤</div><div class="value" id="c-maxdd">--</div></div>'
        '<div class="card"><div class="label">卡玛比率</div><div class="value" id="c-calmar">--</div></div>'
        '</div>'
        '<div id="kline-chart"></div>'
        '<div class="trade-table-wrap">'
        '<div class="table-toolbar"><button class="btn-reset" onclick="resetSelection()">显示全部</button></div>'
        '<table><thead><tr>'
        '<th>操作</th><th>日期</th><th>价格(元)</th><th>股数</th>'
        '<th>金额(元)</th><th>持仓成本</th><th>收益率</th><th>持仓天数</th><th>盈亏(元)</th>'
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

    print(f'Building kline JSON for {len(df_stats)} stocks...')
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
    hist_labels = [str(int(edges[i])) + '-' + str(int(edges[i + 1])) + '%' for i in range(len(hist))]

    ranking_html = make_ranking_html(df_sorted, total_stocks, avg_win_rate, avg_annual_ret,
                                     hist_labels, hist.tolist())
    with open(OUTPUT_DIR / 'report_ranking.html', 'w', encoding='utf-8') as f:
        f.write(ranking_html)
    print('report_ranking.html written')

    detail_html = make_detail_html(df_sorted, df_trades, total_stocks, avg_win_rate, avg_annual_ret)
    with open(OUTPUT_DIR / 'report_detail.html', 'w', encoding='utf-8') as f:
        f.write(detail_html)
    print('report_detail.html written')


if __name__ == '__main__':
    main()
    import subprocess, time, webbrowser
    port = 8083
    output_dir = str(OUTPUT_DIR)
    subprocess.Popen(
        ['python', '-m', 'http.server', str(port)],
        cwd=output_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    webbrowser.open(f'http://localhost:{port}/report_detail.html')
