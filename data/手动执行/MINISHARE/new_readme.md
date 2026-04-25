# new 目录 — Tushare V2 数据同步脚本

目标 schema：`tushare_v2`（PostgreSQL my_stock 数据库）

## 设计原则

- 表名格式：`编号_接口英文名`，如 `001_stock_basic`
- 每个脚本顶部注释包含接口描述、限量、权限、文档链接
- 自动建表：表不存在时自动创建；表已存在时比对字段，不一致则报错中断
- 增量策略：有日期维度的接口按天/按股票增量（upsert）；无日期维度的接口全删全插
- 导入顺序：按日期正序（从早到晚）

## 已完成接口

| 编号 | 接口名 | 中文名 | 同步策略 | 迁移说明 |
|------|--------|--------|----------|----------|
| 001 | stock_basic | 股票列表 | 全删全插 | tushare.stock_basic 有数据，见脚本末尾迁移 SQL |
| 002 | stk_premarket | 每日股本（盘前） | PASS | 自定义HTTP服务不支持 |
| 003 | trade_cal | 交易日历 | 全删全插 | 无需迁移 |
| 004 | stock_st | ST股票列表 | 按日增量 | 无需迁移 |
| 005 | st | ST风险警示板股票 | 全删全插 | 无需迁移 |
| 006 | stock_hsgt | 沪深港通股票列表 | PASS | 自定义HTTP服务不支持 |
| 007 | namechange | 股票曾用名 | PASS | 不需要此接口 |
| 008 | stock_company | 上市公司基本信息 | 全删全插 | 无需迁移 |
| 009 | stk_managers | 上市公司管理层 | PASS | 不需要此接口 |
| 010 | stk_rewards | 管理层薪酬和持股 | PASS | 不需要此接口 |
| 013 | bak_basic | 股票历史列表 | PASS | 不需要此接口 |
| 018 | weekly | 周线行情 | 按日增量 | 无需迁移 |
| 019 | monthly | 月线行情 | 按日增量 | 无需迁移 |
| 023 | adj_factor | 复权因子 | 按日增量 | ✅ 已迁移 14,135,961 行（tushare.stock_adjfactor） |
| 027 | daily_basic | 每日指标 | 按日增量 | ✅ 已迁移 13,685,551 行（tushare.stock_dailybasic） |
| 029 | stk_limit | 每日涨跌停价格 | 按日增量 | 无需迁移 |
| 030 | suspend_d | 每日停复牌信息 | 按日增量 | 无需迁移 |
| 031 | hsgt_top10 | 沪深股通十大成交股 | 按日增量 | 无需迁移 |
| 032 | ggt_top10 | 港股通十大成交股 | 按日增量 | 无需迁移 |
| 036 | income | 利润表 | 按股票循环 | ⏭️ 跳过迁移（源表缺10个字段），请手动执行脚本重拉 |
| 037 | balancesheet | 资产负债表 | 按股票循环 | ⏭️ 跳过迁移（源表缺end_type字段），请手动执行脚本重拉 |
| 038 | cashflow | 现金流量表 | 按股票循环 | ⏭️ 跳过迁移（源表缺5个字段），请手动执行脚本重拉 |
| 039 | forecast | 业绩预告 | 按股票循环 | ✅ 已迁移 86,348 行（tushare.fina_forecast） |
| 040 | express | 业绩快报 | 按股票循环 | ✅ 已迁移 26,449 行（tushare.fina_express） |
| 041 | dividend | 分红送股 | 按股票循环 | ✅ 已迁移 375 行（跳过10行NULL ann_date旧数据） |
| 042 | fina_indicator | 财务指标 | 按股票循环 | ⏭️ 跳过迁移（源表缺2个字段），请手动执行脚本重拉 |
| 043 | fina_audit | 财务审计意见 | 按股票循环 | 无需迁移 |
| 044 | fina_mainbz | 主营业务构成 | 按股票循环 | 无需迁移 |
| 045 | disclosure_date | 财报披露日期 | 按报告期 | 无需迁移 |
| 061 | cyq_perf | 每日筹码及胜率 | 按日增量 | ✅ 可迁移（tushare.stock_chips 字段匹配） |
| 062 | cyq_chips | 每日筹码分布 | 按日增量 | 无需迁移 |
| 063 | stk_factor_pro | 股票技术面因子(专业版) | 按日增量 | 无需迁移（200+字段，耗时长） |
| 066 | hk_hold | 沪深股通持股明细 | 按日增量 | 无需迁移 |
| 067 | stk_auction_o | 股票开盘集合竞价 | 按日增量 | 无需迁移 |
| 068 | stk_auction_c | 股票收盘集合竞价 | 按日增量 | 无需迁移 |
| 069 | stk_nineturn | 神奇九转指标 | 按股票循环 | 无需迁移 |
| 073 | margin | 融资融券交易汇总 | 按日增量 | 无需迁移 |
| 074 | margin_detail | 融资融券交易明细 | 按日增量 | 无需迁移 |
| 075 | margin_secs | 融资融券标的（盘前） | 按日增量 | 无需迁移 |
| 076 | slb_sec | 转融券交易汇总(停) | 按日增量 | 无需迁移 |
| 077 | slb_len | 转融资交易汇总 | 单批全量 | 无需迁移 |
| 078 | slb_sec_detail | 转融券交易明细(停) | 按日增量 | 无需迁移 |
| 080 | moneyflow | 个股资金流向 | 按日增量 | ⏭️ 跳过迁移（tushare.moneyflow 缺 *_vol 字段） |
| 081 | moneyflow_ths | 个股资金流向（THS） | 按日增量 | 无需迁移 |
| 087 | moneyflow_hsgt | 沪深港通资金流向 | 单批全量 | ✅ 可迁移（tushare.moneyflow_hsgt 字段匹配） |
| 121 | index_basic | 指数基本信息 | 全删全插 | 无需迁移 |
| 122 | index_daily | 指数日线行情 | 按指数循环 | 无需迁移 |
| 125 | index_weekly | 指数周线行情 | 按指数循环 | 无需迁移 |
| 129 | index_dailybasic | 大盘指数每日指标 | 按日增量 | 无需迁移 |
| 134 | ci_index_member | 中信行业成分 | 全删全插 | 无需迁移 |
| 135 | ci_daily | 中信行业指数日行情 | 按日增量 | 无需迁移 |
| 137 | idx_factor_pro | 指数技术面因子(专业版) | 按日增量 | 无需迁移（80+字段，耗时长） |
| 138 | daily_info | 沪深市场每日交易统计 | 按日增量 | 无需迁移 |
| 139 | sz_daily_info | 深圳市场每日交易概况 | 按日增量 | 无需迁移 |

## 文件结构

```
new/
├── _common.py              # 公共工具（DB连接、建表检查、upsert、全删全插）
├── 001_stock_basic.py
├── 003_trade_cal.py
├── 004_stock_st.py
├── 005_st.py
├── 008_stock_company.py
├── 018_weekly.py
├── 019_monthly.py
├── 023_adj_factor.py
├── 027_daily_basic.py
├── 029_stk_limit.py
├── 030_suspend_d.py
├── 031_hsgt_top10.py
├── 032_ggt_top10.py
├── 036_income.py
├── 037_balancesheet.py
├── 038_cashflow.py
├── 039_forecast.py
├── 040_express.py
├── 041_dividend.py
├── 042_fina_indicator.py
├── 043_fina_audit.py
├── 044_fina_mainbz.py
├── 045_disclosure_date.py
├── 061_cyq_perf.py
├── 062_cyq_chips.py
├── 063_stk_factor_pro.py
├── 066_hk_hold.py
├── 067_stk_auction_o.py
├── 068_stk_auction_c.py
├── 069_stk_nineturn.py
├── 073_margin.py
├── 074_margin_detail.py
├── 075_margin_secs.py
├── 076_slb_sec.py
├── 077_slb_len.py
├── 078_slb_sec_detail.py
├── 080_moneyflow.py
├── 081_moneyflow_ths.py
├── 087_moneyflow_hsgt.py
├── 121_index_basic.py
├── 122_index_daily.py
├── 125_index_weekly.py
├── 129_index_dailybasic.py
├── 134_ci_index_member.py
├── 135_ci_daily.py
├── 137_idx_factor_pro.py
├── 138_daily_info.py
├── 139_sz_daily_info.py
├── run_all.py              # 批量执行入口
└── new_readme.md           # 本文件
```

## 使用方法

```bash
# 执行全部脚本
python run_all.py

# 只执行指定编号
python run_all.py --only 001 003 027

# 跳过耗时长的按股票循环脚本
python run_all.py --skip 036 037 038 039 040 041 042 043 044 063 137

# 单独执行某个脚本（支持增量参数）
python 027_daily_basic.py --start 20240101 --end 20241231
```

## 注意事项

- 036~044 按股票循环，全量约需数小时，建议在非交易时段运行
- 063 stk_factor_pro 字段200+，按日期循环，全量耗时极长
- 137 idx_factor_pro 字段80+，按日期循环，全量耗时较长
- 所有脚本支持断点续传：自动检测数据库最新日期，从断点继续
- 表不存在时自动建表；表已存在时校验字段，不一致则报错中断
- 所有数据写入 `tushare_v2` schema

## 迁移说明

以下接口在旧 `tushare` schema 中有历史数据，可执行迁移 SQL 导入：

| 接口 | 源表 | 目标表 | 状态 |
|------|------|--------|------|
| cyq_perf | tushare.stock_chips | tushare_v2."061_cyq_perf" | ✅ 字段匹配，可迁移 |
| moneyflow_hsgt | tushare.moneyflow_hsgt | tushare_v2."087_moneyflow_hsgt" | ✅ 字段匹配，可迁移 |
| moneyflow | tushare.moneyflow | tushare_v2."080_moneyflow" | ⏭️ 跳过（缺 *_vol 字段） |
