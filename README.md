# My Stock — A股量化投资研究平台

基于 Microsoft Qlib 框架的中国A股量化投资研究项目，集成完整的数据采集、因子分析、模型训练和策略回测功能。当前主要开发方向为 **BBI 指标驱动的轮动策略**。

---

## 项目概览

### 核心模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 数据采集 | `data/` | Tushare Pro → PostgreSQL，支持 230+ 接口 |
| 数据同步 | `data/手动执行/MINISHARE/` | Minishare API 增量/全量同步脚本 |
| BBI 回测 | `scripts/bbi/backtrader/` | BBI 策略多版本回测框架 |
| Qlib 工作流 | `scripts/` + `configs/` | LightGBM 因子模型训练与验证 |
| 报表生成 | `scripts/bbi/backtrader/v4_plan_1/30_generate_report.py` | HTML 交互式回测报表（端口 8085） |
| 交易跟踪 | `scripts/bbi/backtrader/v4_plan_1/40_trading_server.py` | 操作计划保存与执行跟踪（端口 8086，待实现） |

---

## BBI 策略

### 什么是 BBI

BBI（Bull and Bear Index，多空指标）= 四条均线的算术平均：

```
BBI = (MA5 + MA10 + MA20 + MA60) / 4
```

当收盘价 > BBI 时，认为股票处于多头趋势，可以持有。

### 策略逻辑

**选股条件**：收盘价（前复权）> BBI（前复权）  
**排序依据**：近 5 日涨幅（动量因子）  
**持仓数量**：Top N 只（默认 5 只）  
**换仓频率**：每周一换仓  
**排除范围**：688 科创板、ST 股、退市股、北交所  
**流动性过滤**：近 20 日均流通市值 ≥ 50 亿，均成交额 ≥ 5000 万  

### 防未来数据泄露

盘后数据（资金流向 `moneyflow`、筹码分布 `cyq_perf`）在 T 日收盘后才可获取，回测中统一做 `shift(1)` 处理，确保 T 日决策只使用 T-1 日盘后数据。

---

## 版本历史

### v1 — 基础验证
- 单股 BBI 信号验证
- 确认 BBI 指标计算逻辑

### v2 — 逐股回测
- 对每只股票独立回测 BBI 策略
- 统计胜率、盈亏比、持仓周期分布
- 输出：每股回测报告 + 汇总统计

### v3 — 组合回测（纯 Python）
- 全市场轮动，每周一换仓
- 资金分配：等权分配到 Top N
- 手续费模型：买入 0.03%，卖出 0.13%（含印花税），最低 5 元
- 输出：净值曲线、年化收益、最大回撤、夏普比率

### v4_plan — 基础版本
- 在 v3 基础上增加更完整的数据准备流程
- 新增 `cyq_perf`（筹码分布）和 `moneyflow`（资金流向）特征
- 完整的 HTML 交互式报表，包含：
  - 净值曲线 + 回撤图
  - 资金曲线（绝对金额）+ 月度收益明细表
  - 年度收益柱状图
  - 下周操作计划（基于最新数据自动生成）
  - 最近 10 周持仓周报
  - 历史交易明细

### v4_plan_1 — 当前主力版本
- 在 v4_plan 基础上新增完整止损逻辑：
  - ATR 追踪止损（`ATR_PERIOD=14`，`ATR_MULTIPLIER=4.5`）
  - 硬止损（亏损 8% 强制清仓）
  - 筹码止损（`winner_rate > 80%` 触发）
  - 最小持仓天数保护（20 天内不触发信号类止损）
- 流动性过滤更严格：流通市值 ≥ 100 亿，日均成交额 ≥ 5000 万
- 报表端口改为 8085（避免与 v4_plan 的 8084 冲突）
- 交易跟踪系统（设计完成，待实现）：
  - Flask 后端（端口 8086）保存每周操作计划到 PostgreSQL
  - 独立交易跟踪页面，支持录入实际成交、跟踪执行状态

---

## 快速运行 BBI v4_plan_1 策略

### 前置条件

1. PostgreSQL 数据库已启动（Docker）
2. `tushare_v2` schema 中有 `063_stk_factor_pro`、`061_cyq_perf`、`080_moneyflow` 等表
3. 已配置 `.env` 文件

```bash
# .env 示例（不提交到 git）
DATABASE_URL=postgresql://root:123456@localhost:5432/my_stock
TUSHARE_TOKEN=your_token_here
```

### 运行步骤

```bash
cd scripts/bbi/backtrader/v4_plan_1

# Step 1: 准备数据（从 PostgreSQL 生成 parquet）
python -X utf8 10_prepare_data.py

# Step 2: 运行回测
python -X utf8 20_run_backtest.py

# Step 3: 生成 HTML 报表（自动打开浏览器，端口 8085）
python -X utf8 30_generate_report.py
```

### 关键参数（`config.py`）

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `START_DATE` | `2018-01-01` | 回测开始日期 |
| `END_DATE` | `None`（今日） | 回测结束日期 |
| `INIT_CASH` | `500,000` | 初始资金（元） |
| `REAL_CASH` | `500,000` | 实盘可用资金（每次换仓后从券商 App 更新） |
| `TOP_N` | `5` | 持仓股票数量 |
| `COMM_BUY` | `0.0005` | 买入手续费率 |
| `COMM_SELL` | `0.0015` | 卖出手续费率（含印花税） |
| `FILTER_MIN_CIRC_MV` | `100亿` | 最小流通市值过滤 |
| `FILTER_MIN_AMOUNT` | `5000万` | 最小日均成交额过滤 |
| `ATR_PERIOD` | `14` | ATR 计算周期 |
| `ATR_MULTIPLIER` | `4.5` | ATR 追踪止损倍数 |
| `HARD_STOP_LOSS` | `8%` | 硬止损阈值 |
| `CHIP_EXIT_THRESHOLD` | `80%` | 筹码止损 winner_rate 阈值 |

---

## 数据流水线

```
Tushare Pro API
      ↓
PostgreSQL (my_stock DB, tushare_v2 schema)
      ↓  data/手动执行/MINISHARE/ 同步脚本
      ↓
scripts/bbi/backtrader/v4_plan_1/10_prepare_data.py
      ↓  过滤 + BBI 计算 + shift(1) 防泄露
      ↓
output/stock_data/*.parquet（每股一个文件）
      ↓
20_run_backtest.py → output/{nav_series.csv, trade_records.csv, weekly_records.json, last_holdings.json}
      ↓
30_generate_report.py → output/report.html（端口 8085）
      ↓（可选）
40_trading_server.py → 交易跟踪页面（端口 8086）
```

---

## Qlib 机器学习工作流

除 BBI 策略外，项目也支持基于 Qlib 的 LightGBM 因子模型：

```bash
# 数据准备
python scripts/10_数据准备/10_Tushare转Qlib.py

# 因子分析
python scripts/20_因子分析/20_IC分析.py

# 模型训练
python scripts/30_模型训练/30_单模型训练.py configs/workflow_config_lightgbm_Alpha158.yaml

# 滚动验证
python scripts/40_模型验证/40_滚动窗口验证.py

# 查看结果
mlflow ui  # http://localhost:5000
```

---

## 环境配置

```bash
# 创建 Conda 环境
conda env create -f environment.yml
conda activate mystock

# 安装依赖
pip install -r requirements.txt

# 下载 Qlib 基础数据（一次性）
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

### Docker PostgreSQL

```bash
cd D:\2025_project\00_docker\postgresql
docker-compose up -d
```

---

## 技术栈

- **量化框架**: Microsoft Qlib
- **回测引擎**: 纯 Python（v4_plan 自研，无 Backtrader 依赖）
- **数据源**: Tushare Pro API / Minishare API
- **数据库**: PostgreSQL（Docker）
- **报表**: Plotly 交互式 HTML
- **机器学习**: LightGBM
- **实验追踪**: MLflow

---

## 项目文档

| 文档 | 路径 |
|------|------|
| 数据库表结构 | `docs/数据库表结构清单_带注释.md` |
| Tushare 接口清单 | `docs/tushare/接口清单.md` |
| 参数优化指南 | `docs/参数优化使用指南.md` |
| 滚动验证说明 | `docs/滚动窗口验证使用说明.md` |
| BBI 设计文档 | `docs/superpowers/specs/` |
| 实现计划 | `docs/superpowers/plans/` |

---

## 参考资料

- [Qlib 官方文档](https://qlib.readthedocs.io/)
- [Tushare Pro](https://tushare.pro/)
- [CLAUDE.md](./CLAUDE.md) — Claude Code 工作说明
