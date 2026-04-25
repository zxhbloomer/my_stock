"""
serve.py — 启动本地服务器查看 BBI 交易分析 HTML
用法: python scripts/bbi/html/serve.py
然后打开浏览器访问 http://localhost:8888
"""
import http.server
import os
import webbrowser
from pathlib import Path

PORT = 8888
DIR = Path(__file__).parent

os.chdir(DIR)
handler = http.server.SimpleHTTPRequestHandler
handler.log_message = lambda *a: None  # suppress logs

print(f"启动服务器: http://localhost:{PORT}")
print("按 Ctrl+C 停止")
webbrowser.open(f"http://localhost:{PORT}")

with http.server.HTTPServer(("", PORT), handler) as httpd:
    httpd.serve_forever()
