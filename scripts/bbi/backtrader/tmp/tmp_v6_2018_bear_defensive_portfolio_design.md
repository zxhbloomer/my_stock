# tmp_v6 2018 独立熊市防御组合设计

## 目标

只针对 2018 年 A 股熊市，做一个独立的 long-only 防御组合回测，并和正式 `v6` 的 2018 结果直接对比。

## 设计边界

- 不修改正式 `v4`、`v5`、`v6`。
- 不复用 `v6` 的强势 BBI 轮动逻辑作为核心信号。
- 组合按月调仓，使用上一交易日收盘后可见数据，在下一个交易日开盘成交。
- 先做最小可验证版本，不做参数网格暴力搜索。

## 公开研究映射

本轮按公开 defensive equity 研究做本地化近似：

- 低风险/低波动：主因子
- 高股息：防御收益来源
- 质量：过滤股息陷阱
- 价值：估值保护
- 温和动量：避免接飞刀

## 数据

- 价格/流动性/可交易口径：`v6/output/panel.parquet`
- 大盘指数：`v6/output/market_index.parquet`
- 日度基本面：`027_daily_basic`，取 `dv_ttm`、`pb`
- 财务指标：`042_fina_indicator`，按 `ann_date` backward merge

## 因子定义

- 低风险：`volatility_63`、自算 `volatility_126`、`beta_126`、`drawdown_126`
- 股息：`dv_ttm`
- 质量：`roe_dt`、`grossprofit_margin`、`ocf_to_or`、`debt_to_assets`
- 价值：`pb`
- 温和动量：`ret_21`、`ret_63`

组合总分：

```text
0.35 * low_risk_score
+0.25 * dividend_score
+0.20 * quality_score
+0.10 * value_score
+0.10 * momentum_score
```

## 选股与持仓

- 股票池：`is_eligible == True`
- 额外过滤：
  - `hot_money_risk_hits < 2`
  - `recent_limit_down_20 == 0`
  - `ret_21 > -0.18`
  - `pb > 0`
  - `dv_ttm > 0`
  - 财务质量至少有部分可用
- 每月第一个交易日开盘调仓
- 持有 20 只，等权目标

## 验证标准

- 先确认 PIT 合并逻辑无未来函数
- 回测能稳定跑完
- 输出 2018 年度收益、最大回撤、月度收益，并和 `v6` 对比
- 结果无论好坏都出 HTML 报告，不强行合并
