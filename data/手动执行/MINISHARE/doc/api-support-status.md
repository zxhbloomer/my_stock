# Minishare API 支持状态

测试时间：2026-04-23
测试方法：`POST https://minishare.wmlgg.com/api/v1/query`

## 支持的接口（13个）

| 接口名（英文） | 接口名（中文） | Tushare 文档 |
|---|---|---|
| `stock_basic` | 股票列表 | https://tushare.pro/document/2?doc_id=25 |
| `trade_cal` | 交易日历 | https://tushare.pro/document/2?doc_id=26 |
| `daily` | 日线行情 | https://tushare.pro/document/2?doc_id=27 |
| `weekly` | 周线行情 | https://tushare.pro/document/2?doc_id=144 |
| `monthly` | 月线行情 | https://tushare.pro/document/2?doc_id=145 |
| `adj_factor` | 复权因子 | https://tushare.pro/document/2?doc_id=28 |
| `daily_basic` | 每日指标 | https://tushare.pro/document/2?doc_id=32 |
| `income` | 利润表 | https://tushare.pro/document/2?doc_id=33 |
| `balancesheet` | 资产负债表 | https://tushare.pro/document/2?doc_id=36 |
| `cashflow` | 现金流量表 | https://tushare.pro/document/2?doc_id=44 |
| `fina_indicator` | 财务指标 | https://tushare.pro/document/2?doc_id=79 |
| `index_basic` | 指数基本信息 | https://tushare.pro/document/2?doc_id=94 |
| `index_daily` | 指数日线行情 | https://tushare.pro/document/2?doc_id=95 |

## 不支持的接口（33个）

返回 `403 Unregistered api_name is not allowed`，需联系 Minishare 管理员注册。

| 接口名（英文） | 接口名（中文） | Tushare 文档 |
|---|---|---|
| `stock_st` | ST股票列表 | https://tushare.pro/document/2?doc_id=397 |
| `st` | ST风险警示板股票 | https://tushare.pro/document/2?doc_id=423 |
| `stock_hsgt` | 沪深港通股票列表 | https://tushare.pro/document/2?doc_id=398 |
| `stock_company` | 上市公司基本信息 | https://tushare.pro/document/2?doc_id=112 |
| `stk_limit` | 每日涨跌停价格 | https://tushare.pro/document/2?doc_id=183 |
| `suspend_d` | 每日停复牌信息 | https://tushare.pro/document/2?doc_id=214 |
| `hsgt_top10` | 沪深股通十大成交股 | https://tushare.pro/document/2?doc_id=47 |
| `ggt_top10` | 港股通十大成交股 | https://tushare.pro/document/2?doc_id=48 |
| `forecast` | 业绩预告 | https://tushare.pro/document/2?doc_id=45 |
| `express` | 业绩快报 | https://tushare.pro/document/2?doc_id=46 |
| `dividend` | 分红送股 | https://tushare.pro/document/2?doc_id=103 |
| `fina_audit` | 财务审计意见 | https://tushare.pro/document/2?doc_id=80 |
| `cyq_perf` | 每日筹码及胜率 | https://tushare.pro/document/2?doc_id=293 |
| `cyq_chips` | 每日筹码分布 | https://tushare.pro/document/2?doc_id=294 |
| `stk_factor_pro` | 股票技术面因子(专业版) | https://tushare.pro/document/2?doc_id=328 |
| `hk_hold` | 沪深股通持股明细 | https://tushare.pro/document/2?doc_id=188 |
| `stk_auction_c` | 股票收盘集合竞价 | https://tushare.pro/document/2?doc_id=354 |
| `stk_nineturn` | 神奇九转指标 | https://tushare.pro/document/2?doc_id=364 |
| `margin` | 融资融券交易汇总 | https://tushare.pro/document/2?doc_id=58 |
| `margin_detail` | 融资融券交易明细 | https://tushare.pro/document/2?doc_id=59 |
| `margin_secs` | 融资融券标的（盘前） | https://tushare.pro/document/2?doc_id=326 |
| `slb_sec` | 转融券交易汇总 | https://tushare.pro/document/2?doc_id=332 |
| `slb_len` | 转融资交易汇总 | https://tushare.pro/document/2?doc_id=331 |
| `slb_sec_detail` | 转融券交易明细 | https://tushare.pro/document/2?doc_id=333 |
| `moneyflow` | 个股资金流向 | https://tushare.pro/document/2?doc_id=170 |
| `moneyflow_ths` | 个股资金流向（THS） | https://tushare.pro/document/2?doc_id=348 |
| `moneyflow_hsgt` | 沪深港通资金流向 | https://tushare.pro/document/2?doc_id=47 |
| `index_dailybasic` | 大盘指数每日指标 | https://tushare.pro/document/2?doc_id=128 |
| `ci_index_member` | 中信行业成分 | https://tushare.pro/document/2?doc_id=373 |
| `ci_daily` | 中信行业指数日行情 | https://tushare.pro/document/2?doc_id=308 |
| `idx_factor_pro` | 指数技术面因子(专业版) | https://tushare.pro/document/2?doc_id=358 |
