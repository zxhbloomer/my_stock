# v7 BBI 强势股轮动策略

v7 当前是 v6 当前代码的独立复制版本，用于后续重新演化。

## 当前状态

- 策略逻辑：以 v6 当前主策略为基础，已合入 `weak_lowvol_mom` 弱市低波动量过滤。
- 合入依据：`tmp_v7_weak_market_quality_momentum_experiment.py` 全周期验证显示，总收益从 v6/v7 baseline 的 180.10% 提升到 268.83%，最大回撤从 -35.56% 降至 -29.80%。
- 口径说明：当前 268.83% 结果保留 v7 baseline 原有 `bear_probe` 行为，summary 中 `bear_probe_buys=1` 属于 v7 既有逻辑，不是本轮新增的精炼 probe 实验。
- 风险说明：该逻辑不是 2018 熊市专门防守策略；2018 年收益为 -25.27%，弱于 v6/v7 baseline 的 -23.98%，后续仍需针对 2018 做退出/减仓优化。
- 隔离要求：v7 不 import v6，不读取 v6 的输出文件。
- 输出目录：所有 v7 产物只写入 `scripts/bbi/backtrader/v7/output`。
- 数据目录：`config.py` 使用 `Path(__file__).parent / "output"`，因此运行在 v7 时只使用 v7 本地 output。
- 未合入内容：未合入 `probe_05/10/15/ultra` 熊市反弹小仓位试探逻辑；该实验没有产生有效买入，收益略低于 `weak_lowvol_mom`。

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

回测后核对 summary 指标：

```powershell
Get-Content scripts\bbi\backtrader\v7\output\summary.json |
  Select-String "total_return_pct|max_drawdown_pct|trade_records|weak_lowvol_mom|bear_probe_buys"
```

当前目标口径：`total_return_pct=268.8279`、`max_drawdown_pct=-29.8042`、`trade_records=813`。

## 后续演化原则

后续如果重新加入熊市专门逻辑，应先在 `tmp` 中独立回测验证，再明确合入 v7。v7 正式代码不能读取 v6 的净值、交易记录、调仓日志或其他输出文件。
