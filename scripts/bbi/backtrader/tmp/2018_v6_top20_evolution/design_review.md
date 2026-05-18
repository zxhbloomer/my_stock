# 2018 v6 Top20 漏买诊断与熊市条件放行设计

## 设计结论
量化策略专家审阅认为，v6 漏买 2018 强票的最高概率原因是 bear regime 硬阻断，其次是 early_weakness_downtrend 误杀熊市中的早期强股。代码审阅专家要求把诊断和策略严格分层：Top20 只能用于事后解释，不能进入新策略规则。

## 本轮最小方案
1. 用 v6 panel 重建 2018 非游资非新股收益 Top20。
2. 对 Top20 做逐日归因，识别是否被市场 regime、downtrend、基础候选、pullback/排名等拦截。
3. 实验两个候选：关闭市场硬阻断的诊断版本、bear defensive allow 的条件放行版本。
4. 新策略只使用 signal date 已经在 panel 中存在的历史技术/流动性字段，不使用 Top20 标签，不使用未 shift 的 moneyflow/cyq/fina 数据。

## Web 证据摘要
Tavily 搜索得到的公开资料一致指向：熊市/不确定环境中，quality/profitability、low volatility/defensive、momentum 的组合更适合防守和捕捉相对强势；但防御因子可能在牛市跑输，所以本轮只在 bear regime 中条件放行，不替换全局逻辑。
