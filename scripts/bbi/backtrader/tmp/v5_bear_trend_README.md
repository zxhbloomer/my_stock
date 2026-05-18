# v5 熊市趋势确认实验

## 目标

在不修改 v5 正式代码、不操作 git 的前提下，测试 v5 当前熊市判断是否需要从“单日成立”改为“趋势确认”。

## 外部依据

通过 `tavily-search` 查询：

- 熊市常见定义是指数从高点下跌 20% 以上，但更偏事后定义。
- 量化择时常用移动均线、均线斜率、市场宽度来判断趋势状态。
- 短周期均线或单日穿越容易产生 whipsaw，因此多日确认可以减少噪声。

## v5 当前熊市

```text
bear =
  dd_252 <= -20%
  OR
  (
    close < ma120
    AND ma120_slope_20 < 0
    AND breadth_above_bbi < 45%
  )
```

当前 v5 熊市动作：

- 熊市禁止开仓。
- 熊市确认后浮亏卖出。
- 不强制清空盈利仓。

## 本轮实验

1. `baseline_v5`
   - 原始 v5。
2. `bear_2of3_confirmed`
   - 最近 3 个交易日中至少 2 日为原始 bear，才作为熊市。
3. `bear_3of5_confirmed`
   - 最近 5 个交易日中至少 3 日为原始 bear，才作为熊市。
4. `bear_3of5_clear_all`
   - 最近 5 个交易日中至少 3 日为原始 bear。
   - 沿用 v5 的“前序确认熊市状态”退出机制，在下一次退出检查中，让可计算收益率的持仓都成为熊市退出候选。
   - 停牌、跌停开盘、缺失行情、无法计算收益率时，仍不会立即成交或入选。
5. `bear_state_6of10_exit_6of10`
   - 最近 10 个交易日中至少 6 日满足原始 bear，进入熊市状态。
   - 进入熊市后保持状态，直到最近 10 个交易日中至少 6 日满足反转条件才退出。
   - 反转条件：`close > ma120`、`ma120_slope_20 > 0`、`breadth_above_bbi > 55%`、`dd_252 > -10%`。

## 判断标准

- 优先看全周期收益、年化收益、最大回撤、Calmar。
- 2018、2022 熊市不能明显恶化。
- 2025、2026 强行情如果改善，不能以显著扩大回撤为代价。

## 当前进度

- [x] 完成设计。
- [x] 编写 tmp 实验脚本。
- [x] 运行回测。
- [x] 输出结论。
- [ ] QA/未来函数审查。

## 运行结果

运行命令：

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\v5_bear_trend_experiment.py
python -X utf8 scripts\bbi\backtrader\tmp\v5_bear_trend_experiment.py
```

产物：

- `scripts/bbi/backtrader/tmp/v5_bear_trend_output/results.csv`
- `scripts/bbi/backtrader/tmp/v5_bear_trend_output/summary.md`

全周期：

| case | total | annual | max dd | Calmar | bear block | bear exits | zero days |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline_v5 | 140.92% | 11.08% | -31.18% | 0.3554 | 443 | 61 | 6 |
| bear_3of5_confirmed | 108.13% | 9.16% | -32.47% | 0.2820 | 379 | 55 | 6 |
| bear_state_6of10_exit_6of10 | 105.31% | 8.98% | -56.14% | 0.1599 | 908 | 12 | 344 |
| bear_2of3_confirmed | 37.52% | 3.88% | -51.47% | 0.0754 | 401 | 65 | 6 |
| bear_3of5_clear_all | -34.05% | -4.85% | -58.06% | -0.0836 | 379 | 161 | 347 |

## 初步结论

不建议把当前 v5 熊市判断改成 2/3 或 3/5 趋势确认。

依据：

- `bear_3of5_confirmed` 确实减少了熊市禁止开仓天数，从 `443` 降到 `379`，但全周期收益从 `140.92%` 降到 `108.13%`，最大回撤从 `-31.18%` 扩大到 `-32.47%`。
- `bear_2of3_confirmed` 明显失效，全周期收益只有 `37.52%`，最大回撤扩大到 `-51.47%`。
- `bear_3of5_clear_all` 说明“确认熊市后尽量清仓”的方向不适合当前策略，收益转负，最大回撤扩大到 `-58.06%`。
- `bear_state_6of10_exit_6of10` 在 2018 年形态更贴近熊市：`2018-03-28` 到 `2018-12-28` 连续判熊，2018 年收益和回撤也优于基线；但全周期收益降到 `105.31%`，最大回撤扩大到 `-56.14%`，空仓天数增至 `344`，说明退出条件过滞后，牺牲了后续年份的进攻机会。
- 当前 v5 的原始熊市判断虽然是单日成立，但在这组回测里比趋势确认更有效，不能为了“看起来更平滑”牺牲实际收益和回撤。

## QA 记录

- 未发现未来函数：`bear_2of3` / `bear_3of5` 使用 trailing rolling window，v5 在交易日使用前一交易日 `signal_date` 决策。
- 未修改 v5 生产代码和 v5 输出；实验只写入 `tmp/v5_bear_trend_output`。
- monkeypatch 在 `finally` 中恢复。
- `baseline_v5` 已断言匹配 v5 `summary.json`。
- `bear_3of5_clear_all` 不是保证立即全清仓，而是让可计算收益率的持仓成为熊市退出候选，执行仍受停牌、跌停开盘、缺失行情限制。
