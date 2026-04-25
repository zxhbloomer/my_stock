"""
generate_standalone.py — 生成内嵌数据的单文件 HTML（无需服务器，直接双击打开）
用法: python scripts/bbi/html/generate_standalone.py
输出: scripts/bbi/html/standalone.html
"""
import json
import csv
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent  # my_stock root
DATA_DIR = ROOT / "data/手动执行/推荐结果"
HTML_DIR = Path(__file__).parent

def read_csv(path):
    rows = []
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows

summary = read_csv(DATA_DIR / "trade_summary.csv")
detail = read_csv(DATA_DIR / "trade_detail.csv")

template = (HTML_DIR / "index.html").read_text(encoding='utf-8')

# Replace the fetch-based loadData with embedded data
inject = f"""
<script>
window.SUMMARY_DATA = {json.dumps(summary, ensure_ascii=False)};
window.DETAIL_DATA = {json.dumps(detail, ensure_ascii=False)};
</script>
"""

# Insert before closing </body>
standalone = template.replace('</body>', inject + '</body>')

out = HTML_DIR / "standalone.html"
out.write_text(standalone, encoding='utf-8')
print(f"生成完成: {out}")
print(f"  股票数: {len(summary)}")
print(f"  交易数: {len(detail)}")
print(f"  文件大小: {out.stat().st_size / 1024:.0f} KB")
