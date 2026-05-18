# v5 牛市预备状态自动进化实验

## 目标

在不修改 v5 正式代码、不操作 git 的前提下，测试能否通过更早识别牛市进攻窗口提升收益。

核心问题：

- v5 全区间收益和回撤优于 v4。
- v4 在 2019、2025、2026 等强行情年份明显更强。
- 需要测试“牛市或牛市预备状态用更进攻规则，其他状态保持 v5 防守”是否有效。

## 外部依据

通过 `tavily-search` 查询：

- 牛熊识别常见方法包括移动平均趋势、回撤阈值、市场宽度、Markov/HMM。
- 市场宽度用于确认上涨是否由多数股票参与，而不是少数权重股拉动。
- 中国 A 股牛熊周期研究常用峰谷/涨跌幅方法，财经语境中 20% 涨跌也常被用作牛熊参考。
- 复杂 HMM/机器学习模型解释性较差，第一轮不使用。

## 数据依据

当前 v5 已有：

- 上证指数 `close`
- `ma120`, `ma200`, `ma120_slope_20`, `dd_252`
- 可交易股票池 BBI 宽度 `breadth_above_bbi`
- 个股 BBI、收益、回撤、强趋势等字段

Tushare 可用但本轮暂不引入：

- `idx_factor_pro`, `index_dailybasic`, `daily_info`, `moneyflow`, `cyq_perf`

理由：本轮只验证状态识别和路由，先不增加数据对齐和未来函数风险。

## 设计

现有 v5 牛市：

```text
close > ma120
close > ma200
ma120_slope_20 > 0
dd_252 > -10%
breadth_above_bbi >= 55%
```

牛市预备状态 `bull_early`：

```text
close > ma120
ma120_slope_20 > 0
market_ret_63 > 0
breadth_above_bbi >= 55%
```

不要求：

```text
close > ma200
dd_252 > -10%
```

## 候选实验

1. `baseline_v5`
2. `bull_early_as_bull`
   - `bull_early` 使用 v5 牛市回撤阈值。
3. `bull_early_v4_drawdown`
   - `bull` / `bull_early` 使用原始长期策略回撤阈值：普通 `-5%`，强趋势 `-3%`。
4. `bull_early_exposure600`
   - `bull` / `bull_early` 允许最多 6 只、60 万总投入。
5. `bull_fast_no_slope_as_bull`
   - 放宽牛市预备状态，不要求 `ma120_slope_20 > 0`。
6. `bull_recent20_as_bull`
   - 使用最近 20 日内市场宽度曾达到 55% 作为宽度确认。
7. `bull_recent20_v4_drawdown`
   - 最近 20 日宽度确认 + 原始长期策略回撤阈值。

## 判断标准

优先级：

1. 全区间收益、年化收益高于 v5。
2. 最大回撤不能接近 v4 的 `-46.31%`。
3. 2019 和 2025 应有改善。
4. 2022 熊市不能明显恶化。
5. 与 v4 比，收益可以略低，但回撤必须明显更好。

## 当前进度

- [x] 使用 Tavily 搜索牛熊识别依据。
- [x] 读取 v4/v5 年度表现。
- [x] 读取 Tushare 数据清单。
- [x] 完成专家设计评审。
- [x] 编写 tmp 实验脚本。
- [x] 运行回测。
- [x] 完成 QA/未来函数审查。
- [x] 输出初步结论。

## 最新运行结果

运行命令：

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v5_bull_early_experiment.py
python -X utf8 scripts\bbi\backtrader\tmp\v5_bull_early_experiment.py
```

产物：

- `scripts/bbi/backtrader/tmp/v5_bull_early_output/results.csv`
- `scripts/bbi/backtrader/tmp/v5_bull_early_output/summary.md`

全周期排序：

| case | total | annual | max dd | Calmar | trades | bull_early_days |
|---|---:|---:|---:|---:|---:|---:|
| baseline_v5 | 140.92% | 11.08% | -31.18% | 0.3554 | 632 | 0 |
| bull_early_as_bull | 140.92% | 11.08% | -31.18% | 0.3554 | 632 | 1 |
| bull_early_v4_drawdown | 140.92% | 11.08% | -31.18% | 0.3554 | 632 | 1 |
| bull_recent20_v4_drawdown | 135.17% | 10.76% | -35.22% | 0.3055 | 668 | 378 |
| bull_recent20_as_bull | 119.90% | 9.88% | -36.36% | 0.2716 | 660 | 378 |
| bull_fast_no_slope_as_bull | 75.82% | 6.98% | -58.96% | 0.1183 | 873 | 120 |
| bull_early_exposure600 | 63.24% | 6.03% | -48.89% | 0.1234 | 808 | 1 |

## 初步结论

当前这轮“牛市预备状态”不建议并入 v5。

依据：

- 严格牛市预备状态只有 1 个交易日，无法改善 v5。
- `bull_recent20_as_bull` 是唯一有一定方向性的变体，2018、2021、2022、2025、2026 相对 v5 有改善，但 2020、2023、2024 明显拖累，全周期收益从 `140.92%` 降到 `119.90%`，最大回撤从 `-31.18%` 扩大到 `-36.36%`。
- `bull_recent20_v4_drawdown` 是本轮最接近 v5 的改进候选，但全周期收益仍从 `140.92%` 降到 `135.17%`，最大回撤扩大到 `-35.22%`，不满足合并标准。
- 激进放宽版本能改善 2025/2026，但会显著破坏 2019/2022 或全周期回撤，不符合“收益提升且不牺牲风控”的合并标准。

## QA 记录

- 未发现未来函数：市场状态、宽度、个股特征都来自 `signal_date`，交易在下一交易日开盘执行。
- 未修改 v5 生产代码和 v5 输出；tmp 脚本只动态加载 v5 模块并在上下文中临时 monkeypatch，退出后恢复。
- 初版 `no_state_ban` 实验名有误导，已删除。
- 初版 `use_v4_drawdown` 在候选评分阶段预过滤，和 v4 不一致；已修正为只替换 entry 阶段回撤阈值。
- 年度收益表是年内首个 NAV 到年内最后 NAV 的 in-period 口径，不是严格上一年末到当年末口径。
