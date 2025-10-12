# FinHack Tushare API 调用清单

本文档列出 FinHack 框架中所有调用的 Tushare Pro API 接口。

## 📊 A股基础数据 (astockbasic.py)

### 股票基础信息
- **`pro.stock_basic()`** - 获取A股基本信息
  - 参数: list_status ('L'上市, 'D'退市, 'P'暂停)
  - 表: `astock_basic`

- **`pro.trade_cal()`** - 获取交易日历
  - 表: `astock_trade_cal`

- **`pro.namechange()`** - 获取股票名称变更历史
  - 表: `astock_namechange`

- **`pro.stock_company()`** - 获取上市公司基本信息
  - 参数: exchange ('SZSE'深交所, 'SSE'上交所)
  - 表: `astock_stock_company`

- **`pro.new_share()`** - 获取新股上市信息
  - 表: `astock_new_share`

---

## 💹 A股行情数据 (astockprice.py)

### 日线行情
- **`pro.daily()`** - 获取日线行情
  - 参数: trade_date (交易日期)
  - 表: `astock_price_daily`

- **`pro.weekly()`** - 获取周线行情
  - 表: `astock_price_weekly`

- **`pro.monthly()`** - 获取月线行情
  - 表: `astock_price_monthly`

### 复权与基本面
- **`pro.adj_factor()`** - 获取复权因子
  - 表: `astock_price_adj_factor`

- **`pro.suspend_d()`** - 获取停复牌信息
  - 表: `astock_price_suspend_d`

- **`pro.daily_basic()`** - 获取每日指标(市盈率、换手率等)
  - 表: `astock_price_daily_basic`

### 资金流向
- **`pro.moneyflow()`** - 获取个股资金流向
  - 表: `astock_price_moneyflow`

- **`pro.moneyflow_hsgt()`** - 获取沪深港通资金流向
  - 表: `astock_price_moneyflow_hsgt`

- **`pro.hsgt_top10()`** - 获取沪深港通十大成交股
  - 表: `astock_price_hsgt_top10`

- **`pro.ggt_top10()`** - 获取港股通十大成交股
  - 表: `astock_price_ggt_top10`

- **`pro.ggt_daily()`** - 获取港股通每日成交统计
  - 表: `astock_price_ggt_daily`

- **`pro.ggt_monthly()`** - 获取港股通每月成交统计
  - 表: `astock_price_ggt_monthly`

- **`pro.hk_hold()`** - 获取沪深港股通持股明细
  - 表: `astock_price_hk_hold`

### 涨跌停
- **`pro.stk_limit()`** - 获取每日涨跌停价格
  - 表: `astock_price_stk_limit`

- **`pro.limit_list()`** - 获取每日涨跌停统计
  - 表: `astock_price_limit_list`

---

## 📈 市场参考数据 (astockmarket.py)

### 融资融券
- **`pro.margin()`** - 获取融资融券交易汇总
  - 表: `astock_market_margin`

- **`pro.margin_detail()`** - 获取融资融券交易明细
  - 表: `astock_market_margin_detail`

### 龙虎榜
- **`pro.top_list()`** - 获取龙虎榜每日明细
  - 表: `astock_market_top_list`

- **`pro.top_inst()`** - 获取龙虎榜机构交易明细
  - 表: `astock_market_top_inst`

### 股权质押
- **`pro.pledge_stat()`** - 获取股权质押统计数据
  - 表: `astock_market_pledge_stat`

- **`pro.pledge_detail()`** - 获取股权质押明细
  - 表: `astock_market_pledge_detail`

### 其他市场数据
- **`pro.repurchase()`** - 获取股票回购数据
  - 表: `astock_market_repurchase`

- **`pro.concept()`** - 获取概念板块数据
  - 表: `astock_market_concept`

- **`pro.concept_detail()`** - 获取概念板块成分股
  - 表: `astock_market_concept_detail`

- **`pro.share_float()`** - 获取限售股解禁
  - 表: `astock_market_share_float`

- **`pro.block_trade()`** - 获取大宗交易
  - 表: `astock_market_block_trade`

- **`pro.stk_holdernumber()`** - 获取股东人数
  - 表: `astock_market_stk_holdernumber`

- **`pro.stk_holdertrade()`** - 获取股东增减持
  - 表: `astock_market_stk_holdertrade`

---

## 💰 财务数据 (astockfinance.py)

### 三大报表
- **`pro.income()`** - 获取利润表数据
  - 参数: report_type (1综合报表, 其他单季度)
  - 表: `astock_finance_income`

- **`pro.balancesheet()`** - 获取资产负债表
  - 表: `astock_finance_balancesheet`

- **`pro.cashflow()`** - 获取现金流量表
  - 表: `astock_finance_cashflow`

### 财务指标
- **`pro.fina_indicator()`** - 获取财务指标数据
  - 表: `astock_finance_indicator`

- **`pro.fina_audit()`** - 获取财务审计意见
  - 表: `astock_finance_audit`

- **`pro.fina_mainbz()`** - 获取主营业务构成
  - 表: `astock_finance_mainbz`

### 业绩预告
- **`pro.forecast()`** - 获取业绩预告
  - 表: `astock_finance_forecast`

- **`pro.express()`** - 获取业绩快报
  - 表: `astock_finance_express`

- **`pro.disclosure_date()`** - 获取财报披露计划
  - 表: `astock_finance_disclosure_date`

---

## 📊 指数数据 (astockindex.py)

- **`pro.index_basic()`** - 获取指数基础信息
  - 表: `astock_index_basic`

- **`pro.index_daily()`** - 获取指数日线行情
  - 参数: ts_code, start_date, end_date
  - 表: `astock_index_daily`

- **`pro.index_weight()`** - 获取指数成分和权重
  - 参数: index_code, start_date, end_date
  - 表: `astock_index_weight`

- **`pro.index_classify()`** - 获取申万行业分类 (已注释)
  - 参数: level ('L1', 'L2', 'L3'), src='SW2021'

---

## 🔖 可转债数据 (cb.py)

- **`pro.cb_basic()`** - 获取可转债基本信息
  - 表: `cb_basic`

- **`pro.cb_issue()`** - 获取可转债发行信息
  - 表: `cb_issue`

- **`pro.cb_call()`** - 获取可转债赎回信息
  - 表: `cb_call`

- **`pro.cb_daily()`** - 获取可转债日线行情
  - 表: `cb_daily`

- **`pro.cb_price_chg()`** - 获取可转债转股价变动
  - 表: `cb_price_chg`

- **`pro.cb_share()`** - 获取可转债转股结果
  - 表: `cb_share`

---

## 💼 基金数据 (fund.py)

### 基金基础
- **`pro.fund_basic()`** - 获取基金基本信息
  - 参数: market ('E'场内, 'O'场外), status ('D'正常, 'I'发行, 'L'清盘)
  - 表: `fund_basic`

- **`pro.fund_company()`** - 获取基金公司信息
  - 表: `fund_company`

- **`pro.fund_manager()`** - 获取基金经理信息
  - 表: `fund_manager`

### 基金行情
- **`pro.fund_nav()`** - 获取基金净值数据
  - 表: `fund_nav`

- **`pro.fund_div()`** - 获取基金分红数据
  - 表: `fund_div`

- **`pro.fund_portfolio()`** - 获取基金持仓数据
  - 表: `fund_portfolio`

- **`pro.fund_daily()`** - 获取场内基金日线行情
  - 表: `fund_daily`

---

## 🎯 其他特色数据 (astockother.py)

### 筹码分布
- **`pro.cyq_perf()`** - 获取筹码分布(需高级权限, 已注释)

- **`pro.cyq_chips()`** - 获取筹码细分数据
  - 参数: ts_code
  - 表: `astock_other_cyq_chips`

---

## 📍 期货数据 (futures.py)

### 期货基础信息
- **`pro.fut_basic()`** - 获取期货合约基础信息
  - 参数: exchange (CFFEX/DCE/CZCE/SHFE/INE)
  - 表: `futures_basic`

- **`pro.trade_cal()`** - 获取期货交易日历
  - 参数: exchange (交易所代码)
  - 表: `futures_trade_cal`

### 期货行情
- **`pro.fut_daily()`** - 获取期货日线行情
  - 表: `futures_daily`

- **`pro.fut_holding()`** - 获取期货持仓数据
  - 表: `futures_holding`

---

## 📊 统计说明

### 按模块分类统计
- **A股基础**: 5个API
- **A股行情**: 15个API
- **市场数据**: 13个API
- **财务数据**: 10个API
- **指数数据**: 3个API
- **可转债**: 6个API
- **基金**: 7个API
- **期货**: 4个API
- **其他**: 1个API (筹码分布)

**总计**: ~64个 Tushare Pro API 接口

---

## 🔑 权限说明

部分API需要特定的Tushare积分权限：

### 已注释(需高级权限)
- `cyq_perf` - 筹码分布汇总 (需5000积分)
- `ccass_hold_detail` - 港股CCASS持股明细
- `top10_holders` - 十大股东
- `top10_floatholders` - 十大流通股东
- `broker_recommend` - 券商荐股

### 数据获取模式
1. **按日期增量**: daily, weekly, monthly, adj_factor等
2. **按股票代码全量**: pledge_detail, concept_detail等
3. **全量替换**: stock_basic, concept, cb_basic等
4. **按披露日期**: 财务数据根据disclosure_date表智能更新

---

## 📝 使用示例

```python
# 获取股票基本信息
df = pro.stock_basic(exchange='', list_status='L')

# 获取日线行情
df = pro.daily(trade_date='20240101')

# 获取财务指标
df = pro.fina_indicator(ts_code='000001.SZ', start_date='20230101')

# 获取基金经理信息
df = pro.fund_manager(ts_code='159915.SZ')
```

---

**生成时间**: 2025-10-10
**框架版本**: FinHack 1.0
**数据源**: Tushare Pro API
