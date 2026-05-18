# v6 Acceleration Exhaustion Evolution

## 工作推进进度
- 头脑风暴专家：趋势专家判断，上涨加速不是卖点，加速后失速才是风险。
- 设计专家：量化专家把理论落到两个风险标签：`up_accel_exhaustion` 与 `bear_down_accel_risk`。
- 数据专家：检查 Tushare 接口清单，本轮使用 v6 已准备好的 063/137 等字段，不新增 061/080 盘后字段，避免未来函数和归因混杂。
- 开发专家：只在 tmp 下新增实验脚本和测试，复用 v6 引擎，不修改 v4/v5/v6 生产代码。
- Review 专家：baseline_v6 必须复现 v6 summary，HTML 必须给出 v4/v5/v6/候选对比。

## Web 复核
- 趋势跟随：强趋势应优先跟随，不应因为上涨加速本身就反向交易。 来源：https://www.investopedia.com/articles/active-trading/041814/four-most-commonlyused-indicators-trend-trading.asp
- 动量崩溃：熊市后期和高波动反弹阶段，动量策略容易遭遇反转损失。 来源：https://www.nber.org/system/files/working_papers/w20439/w20439.pdf
- 宽度 thrust：底部更可靠的确认来自市场宽度快速修复，而不是单纯下跌加速。 来源：https://www.investopedia.com/terms/b/breadth-thrust-indicator.asp
- ATR/动态退出：工程实现常用动态止损/跟踪止损管理趋势持仓风险。 来源：https://github.com/kernc/backtesting.py/discussions/238

## Tushare 数据判断
- 063 stk_factor_pro：已有日线、复权、BBI、成交额、技术因子，适合本轮价格/斜率/失速量化。
- 137 idx_factor_pro：已有上证指数技术面因子，v6 已用于市场状态和大盘风控。
- 061 cyq_perf、080 moneyflow：此前 v6_moneyflow 实验已验证不优于 v6；本轮不重复叠加。

## 全周期结果
| case | 总收益 | 年化 | 最大回撤 | Calmar | 交易数 | 过滤候选 |
|---|---:|---:|---:|---:|---:|---:|
| forbid_accel_exhaustion_buy | 261.27% | 16.59% | -30.26% | 0.5484 | 843 | 37606 |
| baseline_v6 | 214.56% | 14.68% | -30.61% | 0.4795 | 782 | 32206 |
| forbid_and_exit_exhaustion | 191.74% | 13.65% | -28.16% | 0.4848 | 1031 | 37606 |
| exit_up_exhaustion_profit | 149.22% | 11.53% | -25.34% | 0.4550 | 927 | 32206 |
| forbid_up_exhaustion_buy | 99.67% | 8.62% | -37.95% | 0.2270 | 772 | 3892 |
| forbid_bear_down_accel_buy | 90.29% | 7.99% | -38.72% | 0.2064 | 614 | 5892 |

## v4/v5/v6 对比
- v4：总收益 118.02%，最大回撤 -46.31%。
- v5：总收益 140.92%，最大回撤 -31.18%。
- v6：总收益 214.56%，最大回撤 -30.61%。

## baseline_v6 复现校验
| 字段 | 实验值 | v6 summary | 差值 |
|---|---:|---:|---:|
| final_nav | 1572816.080000 | 1572816.080000 | 0.00000000 |
| total_return_pct | 214.563216 | 214.563200 | 0.00001600 |
| annual_return_pct | 14.678963 | 14.679000 | -0.00003679 |
| max_drawdown_pct | -30.614305 | -30.614300 | -0.00000518 |
| calmar_ratio | 0.479481 | 0.479500 | -0.00001947 |
| trade_records | 782.000000 | 782.000000 | 0.00000000 |

## Walk-forward
- 训练期选择：exit_up_exhaustion_profit，训练收益 170.28%，Calmar 1.1143。
- 验证期收益：-12.18%，Calmar -0.1912。
- 确认期收益：8.64%，Calmar 0.4706。

## 建议
- 全周期最佳：forbid_accel_exhaustion_buy。
- 暂不建议合并：收益、回撤或 walk-forward 稳定性没有同时超过当前 v6。

## 候选基线版本，后续不要遗忘

当前值得保留的候选版本是 `forbid_accel_exhaustion_buy`：

- 规则：当前 v6 的 `early_weakness_downtrend` 基础上，额外禁止买入/加仓 `up_accel_exhaustion` 或 `bear_down_accel_risk`。
- 全周期收益：261.27%。
- 年化收益：16.59%。
- 最大回撤：-30.26%。
- Calmar：0.5484。
- 交易数：843。
- 结论：比 v6 的 214.56% 收益更高，回撤略优，但 walk-forward 尚未证明稳定，必须作为候选继续压力测试，不可直接丢弃，也不可直接合并。
