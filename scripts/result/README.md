# 回测结果查看工具

本目录包含回测结果的分析和可视化工具。

## 📁 文件说明

| 文件名 | 原文件名 | 功能描述 | 输出格式 |
|--------|---------|---------|---------|
| `查看结果.py` | view_results.py | 在终端查看回测指标和Top股票 | 终端文字 |
| `生成图表.py` | view_charts.py | 生成静态分析图表 | PNG图片 |
| `生成HTML报告.py` | view_charts_html.py | 生成交互式分析报告 | HTML网页 |
| `检查数据范围.py` | check_data_range.py | 检查Qlib数据时间范围 | 终端文字 |

## 🚀 使用方法

### 1️⃣ 查看终端结果
```bash
python scripts/result/查看结果.py
```
**输出**：
- 超额收益分析（无/含交易成本）
- 年化收益率、信息比率、最大回撤
- Top 15 看涨/看跌股票

### 2️⃣ 生成PNG图表
```bash
python scripts/result/生成图表.py
```
**输出**：
- 文件：`backtest_analysis.png`（3×3 九宫格图表）
- 包含：IC时间序列、IC分布、累积收益、超额收益、回撤、换手率等

### 3️⃣ 生成HTML交互报告
```bash
python scripts/result/生成HTML报告.py
```
**输出**：
- 文件：`backtest_report.html`（自动在浏览器打开）
- 交互式图表，可缩放、悬停查看数据
- 包含指标摘要卡片

### 4️⃣ 检查数据范围
```bash
python scripts/result/检查数据范围.py
```
**输出**：
- Qlib数据的起止时间
- 可用交易日数量

## ⚙️ 自动化

运行 `python scripts/30_运行工作流.py configs/xxx.yaml` 后，会**自动生成HTML报告**并打开浏览器。

如果自动生成失败，可以手动运行上述脚本。

## 📊 输出文件位置

- `backtest_analysis.png` - 项目根目录
- `backtest_report.html` - 项目根目录
- MLflow实验记录 - `mlruns/` 目录

## 💡 提示

1. **中文文件名**：这些文件使用中文命名，便于识别，但**不能被其他Python模块import**
2. **独立运行**：每个脚本都可以独立运行，会自动查找最新的回测记录
3. **数据来源**：所有脚本从 `mlruns/backtest_analysis` 实验中读取数据

## 🔧 技术说明

- **数据路径**：`D:/Data/my_stock`（Qlib数据目录）
- **结果路径**：`mlruns/`（MLflow实验记录）
- **Python环境**：`mystock` conda环境
