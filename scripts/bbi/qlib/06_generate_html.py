"""
06_generate_html.py
读取最新每日推荐（04_daily_recommend.py输出）+ 历史交易明细（03_backtest.py输出）
生成单文件HTML看板，直接双击打开

用法:
    python scripts/bbi/06_generate_html.py

左侧: 最新日期推荐 top50（按模型分数排名，已过滤ST）
右侧: 点击股票 → 显示该股票历史交易明细
"""
import csv
import glob
import json
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
DATA_DIR = ROOT / "data/手动执行/推荐结果"
OUT_DIR = Path(__file__).parent / "html"
OUT_FILE = OUT_DIR / "index.html"


def read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    # 1. 找最新推荐文件
    rec_files = sorted(glob.glob(str(DATA_DIR / "20*.csv")))
    if not rec_files:
        print("[ERROR] 找不到推荐文件，请先运行 04_daily_recommend.py")
        return
    latest_file = rec_files[-1]
    latest_date = Path(latest_file).stem
    recommend = read_csv(latest_file)

    # 过滤ST
    recommend = [r for r in recommend if "ST" not in (r.get("name") or "")]
    print(f"推荐日期: {latest_date}，有效股票: {len(recommend)} 只（已过滤ST）")

    # 2. 读历史交易明细
    detail_path = DATA_DIR / "trade_detail.csv"
    if not detail_path.exists():
        print("[WARN] 找不到 trade_detail.csv，右侧历史记录将为空")
        detail = []
    else:
        detail = read_csv(detail_path)
        # 过滤ST
        detail = [r for r in detail if "ST" not in (r.get("name") or "")]

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rec_json    = json.dumps(recommend, ensure_ascii=False)
    detail_json = json.dumps(detail, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__DATE__", latest_date) \
                        .replace("__RECOMMEND_JSON__", rec_json) \
                        .replace("__DETAIL_JSON__", detail_json)

    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"生成完成: {OUT_FILE}  ({OUT_FILE.stat().st_size // 1024} KB)")

    webbrowser.open(OUT_FILE.as_uri())


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>BBI策略 · 今日推荐</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Microsoft YaHei', Arial, sans-serif; background: #0d1117; color: #e6edf3; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
.header { background: #161b22; border-bottom: 1px solid #30363d; padding: 10px 16px; display: flex; align-items: center; gap: 20px; flex-shrink: 0; }
.header h1 { font-size: 15px; font-weight: 600; color: #58a6ff; }
.header .date-badge { background: #1f6feb; color: #fff; font-size: 12px; padding: 2px 10px; border-radius: 10px; }
.header .sub { font-size: 12px; color: #8b949e; }
.main { display: flex; flex: 1; overflow: hidden; }

/* ── Left panel ── */
.left-panel { width: 33.333%; border-right: 1px solid #30363d; display: flex; flex-direction: column; overflow: hidden; }
.panel-hdr { background: #161b22; padding: 8px 12px; border-bottom: 1px solid #30363d; display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.panel-hdr span { font-size: 13px; font-weight: 600; }
.panel-hdr .cnt { font-size: 11px; color: #8b949e; background: #21262d; padding: 2px 7px; border-radius: 10px; }
.search-box { margin: 8px 12px; background: #21262d; border: 1px solid #30363d; border-radius: 6px; padding: 5px 10px; color: #e6edf3; font-size: 12px; outline: none; width: calc(100% - 24px); }
.search-box:focus { border-color: #58a6ff; }
.stock-list { flex: 1; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #30363d #0d1117; }
.stock-list::-webkit-scrollbar { width: 4px; }
.stock-list::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }
.stock-item { padding: 9px 12px; border-bottom: 1px solid #21262d; cursor: pointer; transition: background 0.1s; display: flex; align-items: center; gap: 10px; }
.stock-item:hover { background: #161b22; }
.stock-item.selected { background: #1f2d3d; border-left: 3px solid #58a6ff; padding-left: 9px; }
.rank-badge { font-size: 11px; font-weight: 700; min-width: 26px; text-align: center; padding: 2px 4px; border-radius: 4px; background: #21262d; color: #8b949e; }
.rank-badge.r1 { background: #b8860b; color: #fff; }
.rank-badge.r2 { background: #555; color: #fff; }
.rank-badge.r3 { background: #7b4f2e; color: #fff; }
.rank-badge.top10 { background: #1f6feb33; color: #58a6ff; }
.stock-info { flex: 1; min-width: 0; }
.stock-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stock-code { font-size: 11px; color: #8b949e; font-family: monospace; }
.score-bar-wrap { width: 60px; display: flex; flex-direction: column; align-items: flex-end; gap: 2px; }
.score-val { font-size: 11px; color: #58a6ff; font-weight: 600; }
.score-bar { height: 3px; background: #1f6feb; border-radius: 2px; }

/* ── Right panel ── */
.right-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.right-hdr { background: #161b22; padding: 10px 16px; border-bottom: 1px solid #30363d; flex-shrink: 0; }
.right-hdr .title { font-size: 15px; font-weight: 600; }
.right-hdr .sub { font-size: 12px; color: #8b949e; margin-top: 3px; }
.cards { display: flex; gap: 10px; padding: 12px 16px; background: #0d1117; border-bottom: 1px solid #21262d; flex-shrink: 0; flex-wrap: wrap; }
.card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 14px; min-width: 100px; flex: 1; }
.card-label { font-size: 11px; color: #8b949e; margin-bottom: 4px; }
.card-val { font-size: 18px; font-weight: 700; }
.card-sub { font-size: 11px; color: #8b949e; margin-top: 2px; }
.trade-hdr { padding: 8px 16px; background: #161b22; border-bottom: 1px solid #30363d; font-size: 12px; color: #8b949e; flex-shrink: 0; display: flex; justify-content: space-between; }
.table-wrap { flex: 1; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #30363d #0d1117; }
.table-wrap::-webkit-scrollbar { width: 4px; }
.table-wrap::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
thead th { background: #161b22; padding: 8px 12px; text-align: left; color: #8b949e; font-weight: 500; border-bottom: 1px solid #30363d; position: sticky; top: 0; z-index: 1; white-space: nowrap; }
tbody tr { border-bottom: 1px solid #21262d; }
tbody tr:hover { background: #161b22; }
tbody td { padding: 7px 12px; white-space: nowrap; }
.pos { color: #f85149 !important; }
.neg { color: #3fb950 !important; }
.status-open { color: #d29922; background: #2d2a1a; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
.status-closed { color: #8b949e; background: #21262d; padding: 2px 6px; border-radius: 3px; font-size: 11px; }
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #8b949e; gap: 10px; }
.empty-state .icon { font-size: 36px; opacity: 0.3; }
.no-history { padding: 40px; text-align: center; color: #8b949e; font-size: 13px; }
</style>
</head>
<body>
<div class="header">
  <h1>📈 BBI策略 · 今日推荐</h1>
  <span class="date-badge">__DATE__</span>
  <span class="sub">模型打分 Top50（已过滤ST）</span>
</div>
<div class="main">
  <div class="left-panel">
    <div class="panel-hdr">
      <span>今日推荐</span>
      <span class="cnt" id="list-cnt">0</span>
    </div>
    <input class="search-box" id="search" placeholder="搜索股票代码或名称..." oninput="filterList()">
    <div class="stock-list" id="stock-list"></div>
  </div>
  <div class="right-panel">
    <div class="empty-state" id="empty-state">
      <div class="icon">📊</div>
      <p>点击左侧股票查看历史交易记录</p>
    </div>
    <div id="detail-view" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
      <div class="right-hdr">
        <div class="title" id="d-title"></div>
        <div class="sub" id="d-sub"></div>
      </div>
      <div class="cards" id="d-cards"></div>
      <div class="trade-hdr">
        <span>历史交易明细（回测期内）</span>
        <span id="d-trade-cnt" style="color:#e6edf3;"></span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr>
            <th>#</th><th>买入日期</th><th>买入价</th>
            <th>卖出日期</th><th>卖出价</th>
            <th>收益率</th><th>持有天数</th><th>状态</th>
          </tr></thead>
          <tbody id="d-tbody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>
<script>
const recommend = __RECOMMEND_JSON__;
const detail    = __DETAIL_JSON__;
let filtered = [...recommend];
let selected = null;
const maxScore = Math.max(...recommend.map(r => parseFloat(r.score)));

(function init() {
  document.getElementById('list-cnt').textContent = recommend.length;
  renderList();
})();

function filterList() {
  const q = document.getElementById('search').value.trim().toLowerCase();
  filtered = recommend.filter(r =>
    !q || r.ts_code.toLowerCase().includes(q) || (r.name||'').toLowerCase().includes(q)
  );
  document.getElementById('list-cnt').textContent = filtered.length;
  renderList();
}

function renderList() {
  document.getElementById('stock-list').innerHTML = filtered.map(r => {
    const rank = parseInt(r.rank);
    const rc = rank===1?'r1':rank===2?'r2':rank===3?'r3':rank<=10?'top10':'';
    const sel = r.ts_code===selected?' selected':'';
    const score = parseFloat(r.score);
    const barW = Math.round(score / maxScore * 56);
    return `<div class="stock-item${sel}" onclick="selectStock('${r.ts_code}')">
      <span class="rank-badge ${rc}">${rank}</span>
      <div class="stock-info">
        <div class="stock-name">${r.name||r.ts_code}</div>
        <div class="stock-code">${r.ts_code}</div>
      </div>
      <div class="score-bar-wrap">
        <span class="score-val">${score.toFixed(4)}</span>
        <div class="score-bar" style="width:${barW}px"></div>
      </div>
    </div>`;
  }).join('');
}

function selectStock(code) {
  selected = code;
  renderList();
  const rec = recommend.find(r => r.ts_code === code);
  const trades = detail.filter(r => r.ts_code === code);
  if (!rec) return;

  document.getElementById('empty-state').style.display = 'none';
  const dv = document.getElementById('detail-view');
  dv.style.display = 'flex';

  document.getElementById('d-title').textContent = `${rec.name||code}  ${code}`;
  document.getElementById('d-sub').textContent = `今日排名 #${rec.rank} · 模型分数 ${parseFloat(rec.score).toFixed(6)}`;

  const closed = trades.filter(r => r.status==='已平仓');
  const open   = trades.filter(r => r.status==='持有中');
  const wins   = closed.filter(r => parseFloat(r.return_pct) > 0);
  const avgRet = closed.length ? closed.reduce((s,r)=>s+parseFloat(r.return_pct),0)/closed.length : 0;
  const totRet = closed.reduce((s,r)=>s+parseFloat(r.return_pct),0);
  const winRate = closed.length ? wins.length/closed.length*100 : 0;

  document.getElementById('d-cards').innerHTML = trades.length === 0 ? '' : `
    <div class="card"><div class="card-label">历史交易次数</div>
      <div class="card-val">${trades.length}</div>
      <div class="card-sub">${open.length>0?open.length+'笔持有中':'全部已平仓'}</div></div>
    <div class="card"><div class="card-label">历史胜率</div>
      <div class="card-val ${winRate>=50?'pos':'neg'}">${winRate.toFixed(1)}%</div>
      <div class="card-sub">${wins.length}/${closed.length} 盈利</div></div>
    <div class="card"><div class="card-label">平均收益率</div>
      <div class="card-val ${avgRet>=0?'pos':'neg'}">${avgRet>=0?'+':''}${avgRet.toFixed(2)}%</div>
      <div class="card-sub">每笔平均</div></div>
    <div class="card"><div class="card-label">累计收益率</div>
      <div class="card-val ${totRet>=0?'pos':'neg'}">${totRet>=0?'+':''}${totRet.toFixed(2)}%</div>
      <div class="card-sub">回测期内</div></div>`;

  document.getElementById('d-trade-cnt').textContent = trades.length ? `共 ${trades.length} 笔` : '';
  document.getElementById('d-tbody').innerHTML = trades.length === 0
    ? '<tr><td colspan="8" class="no-history">该股票在回测期内未被模型选中过</td></tr>'
    : trades.map((t,i) => {
        const ret = parseFloat(t.return_pct);
        const st = t.status==='持有中'
          ? '<span class="status-open">持有中</span>'
          : '<span class="status-closed">已平仓</span>';
        return `<tr>
          <td style="color:#8b949e">${i+1}</td>
          <td>${t.buy_date}</td>
          <td>${parseFloat(t.buy_price).toFixed(3)}</td>
          <td>${t.sell_date}</td>
          <td>${t.status==='持有中'?'<span style="color:#8b949e">-</span>':parseFloat(t.sell_price).toFixed(3)}</td>
          <td class="${ret>=0?'pos':'neg'}" style="font-weight:600">${ret>=0?'+':''}${ret.toFixed(2)}%</td>
          <td>${t.hold_days}天</td>
          <td>${st}</td>
        </tr>`;
      }).join('');
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
