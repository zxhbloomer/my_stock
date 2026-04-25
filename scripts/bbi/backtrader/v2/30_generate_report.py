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
    for col in ['open_qfq', 'high_qfq', 'low_qfq', 'close_qfq']:
        df[col] = df[col].ffill().fillna(0)
    dates   = [str(d) for d in df['trade_date'].tolist()]
    # ECharts candlestick order: [open, close, low, high]
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
        '<title>BBI回测排名</title>'
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
        '<style>' + css + '</style></head><body>'
        '<div class="header"><h2 style="margin:0">BBI回测排名</h2>'
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
        sub = df_trades[df_trades['ts_code'] == ts_code][
            ['buy_date', 'buy_price', 'sell_date', 'sell_price', 'return_pct', 'hold_days', 'pnl']
        ].to_dict('records')
        trades_parts.append('tradesData["' + ts_code + '"] = ' + json.dumps(sub) + ';')
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
const chart = echarts.init(document.getElementById('kline-chart'));
let currentData = null;
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
  return data.buys
    .filter(b => filterBuyDate == null || b[0] === filterBuyDate)
    .map(b => {
      const di = data.dates.indexOf(b[0]);
      const kline = di >= 0 ? data.candles[di] : null;
      const low = kline ? kline[2] : b[1];
      return { value: [b[0], low], label: { show: true, formatter: '买', position: 'bottom', color: '#e74c3c', fontSize: 11, fontWeight: 'bold' } };
    });
}

function makeSellPoints(data, filterSellDate) {
  return data.sells
    .filter(s => filterSellDate == null || s[0] === filterSellDate)
    .map(s => {
      const di = data.dates.indexOf(s[0]);
      const kline = di >= 0 ? data.candles[di] : null;
      const high = kline ? kline[3] : s[1];
      return { value: [s[0], high], label: { show: true, formatter: '卖', position: 'top', color: '#2ecc71', fontSize: 11, fontWeight: 'bold' } };
    });
}

function renderChart(data, buyDate, sellDate) {
  const startIdx = Math.max(0, data.dates.length - 504);
  const closes = data.candles.map(c => c[1]);
  const buyPoints  = makeBuyPoints(data, buyDate);
  const sellPoints = makeSellPoints(data, sellDate);
  chart.setOption({
    animation: false,
    tooltip: {trigger:'axis', axisPointer:{type:'cross'}},
    legend: {data:['K线','收盘价','BBI','买入','卖出']},
    dataZoom: [
      {type:'inside', startValue:startIdx, endValue:data.dates.length-1},
      {type:'slider', startValue:startIdx, endValue:data.dates.length-1}
    ],
    xAxis: {type:'category', data:data.dates, scale:true},
    yAxis: {type:'value', scale:true},
    series: [
      {name:'K线', type:'candlestick', data:data.candles,
       itemStyle:{color:'#e74c3c',color0:'#2ecc71',borderColor:'#e74c3c',borderColor0:'#2ecc71'}},
      {name:'收盘价', type:'line', data:closes,
       lineStyle:{color:'#8e44ad',width:1}, showSymbol:false, smooth:false},
      {name:'BBI', type:'line', data:data.bbi,
       lineStyle:{color:'#f39c12',width:1.5}, showSymbol:false, smooth:true},
      {name:'买入', type:'scatter', data:buyPoints,
       symbol:'triangle', symbolSize:10, itemStyle:{color:'#e74c3c'}, label:{show:true}},
      {name:'卖出', type:'scatter', data:sellPoints,
       symbol:'triangle', symbolRotate:180, symbolSize:10, itemStyle:{color:'#2ecc71'}, label:{show:true}}
    ]
  }, true);
}

function renderTrades(code, data) {
  const trades = tradesData[code] || [];
  const tbody = document.getElementById('tradeBody');
  tbody.innerHTML = '';
  trades.forEach(t => {
    const holding = t.sell_date === '持仓中';
    const up = t.return_pct >= 0;
    const color = holding ? '#2980b9' : (up ? '#e74c3c' : '#2ecc71');
    const tr = document.createElement('tr');
    if (holding) tr.style.background = '#eaf4fb';
    tr.innerHTML =
      '<td class="td-left">'+t.buy_date+'</td>'
      +'<td class="td-right">'+t.buy_price+'</td>'
      +'<td class="td-left" style="color:'+(holding?'#2980b9':'')+'">'+t.sell_date+'</td>'
      +'<td class="td-right">'+t.sell_price+'</td>'
      +'<td class="td-right" style="color:'+color+'">'+t.return_pct.toFixed(2)+'%</td>'
      +'<td class="td-center">'+t.hold_days+'</td>'
      +'<td class="td-right" style="color:'+color+'">'+fmt(t.pnl)+'</td>';
    tr.onclick = () => {
      if (holding) return;
      if (selectedRow === tr) {
        // 再次点击取消选中
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
    tbody.appendChild(tr);
  });
}

function zoomToTrade(dates, buyDate, sellDate) {
  const bi = dates.indexOf(buyDate), si = dates.indexOf(sellDate);
  if (bi < 0 || si < 0) return;
  chart.dispatchAction({type:'dataZoom',
    startValue:Math.max(0,bi-10), endValue:Math.min(dates.length-1,si+10)});
}

function zoomToDefault(data) {
  const startIdx = Math.max(0, data.dates.length - 504);
  chart.dispatchAction({type:'dataZoom', startValue:startIdx, endValue:data.dates.length-1});
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
        '<title>BBI回测详情</title>'
        '<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>'
        '<style>' + css + '</style></head><body>'
        '<div class="header">'
        '<h3 style="margin:0">BBI回测详情</h3>'
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
        '<th>买入日期</th><th>买入价格(元)</th><th>卖出日期</th><th>卖出价格(元)</th>'
        '<th>收益率</th><th>持仓天数</th><th>盈亏(元)</th>'
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
    port = 8080
    output_dir = str(OUTPUT_DIR)
    subprocess.Popen(
        ['python', '-m', 'http.server', str(port)],
        cwd=output_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    webbrowser.open(f'http://localhost:{port}/report_detail.html')
