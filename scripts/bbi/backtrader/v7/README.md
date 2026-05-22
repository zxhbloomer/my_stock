# v7 BBI 强势股轮动策略

v7 当前是 v6 当前代码的独立复制版本，用于后续重新演化。

## 当前状态

- 策略逻辑：以 v6 当前主策略为基础，已合入“弱市低波动动量过滤”和“牛市提前买入”。
- 合入依据：弱市低波动动量过滤实验显示，总收益从 v6/v7 基准的 180.10% 提升到 268.83%，最大回撤从 -35.56% 降至 -29.80%；`tmp/v7_regime_hold_evolution.py` 进一步验证“牛市提前买入”将总收益从 268.83% 提升到 302.16%，最大回撤仍为 -29.80%。
- 口径说明：当前 302.16% 结果保留 v7 原有“熊市小仓位试探”行为，全周期仅触发 1 次熊市试探买入；本轮只改变牛市首买回撤阈值，不改变止损、熊市过滤、震荡市/熊市入场阈值。
- 风险说明：该逻辑不是 2018 熊市专门防守策略；2018 年收益为 -25.27%，弱于 v6/v7 基准的 -23.98%，后续仍需针对 2018 做退出/减仓优化。
- 隔离要求：v7 不 import v6，不读取 v6 的输出文件。
- 输出目录：所有 v7 产物只写入 `scripts/bbi/backtrader/v7/output`。
- 数据目录：`config.py` 使用 `Path(__file__).parent / "output"`，因此运行在 v7 时只使用 v7 本地 output。
- 未合入内容：未合入更激进的熊市反弹小仓位试探逻辑；该实验没有产生有效买入，收益略低于当前弱市低波动动量过滤版本。

## 运行

```powershell
cd scripts/bbi/backtrader/v7
python -X utf8 10_prepare_data.py
python -X utf8 20_run_backtest.py
python -X utf8 30_generate_report.py
```

## 验证

```powershell
python -X utf8 -m py_compile scripts\bbi\backtrader\v7\10_prepare_data.py scripts\bbi\backtrader\v7\20_run_backtest.py scripts\bbi\backtrader\v7\30_generate_report.py
python -X utf8 -m unittest discover -s scripts\bbi\backtrader\v7 -p "test*.py" -v
```

回测后核对核心指标：

```powershell
Get-Content scripts\bbi\backtrader\v7\output\summary.json |
  Select-String "total_return_pct|max_drawdown_pct|trade_records"
```

当前目标口径：`total_return_pct=302.1605`、`max_drawdown_pct=-29.8042`、`trade_records=765`。

## 后续演化原则

后续如果重新加入熊市专门逻辑，应先在 `tmp` 中独立回测验证，再明确合入 v7。v7 正式代码不能读取 v6 的净值、交易记录、调仓日志或其他输出文件。
宽止损、弱势修复期持有保护、评分重排在本轮实验中均弱于 v7，不合入正式代码；下一轮优先继续研究牛市入场后的加仓/持仓节奏。
