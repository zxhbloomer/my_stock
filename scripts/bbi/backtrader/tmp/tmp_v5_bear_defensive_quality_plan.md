# tmp_v5 Bear Defensive Quality Plan

## 步骤

1. 复用 `v6_bear_probe_evolution.py` 骨架，锁定“只改熊市试探候选”的最小实现面。
2. 先写单元测试：
   - 财务字段按 `ann_date` 向后对齐，不得看未来。
   - 防御过滤只在熊市试探候选上生效。
   - 防御评分能改变候选排序，但不丢行。
3. 实现 `daily_basic` 与 `fina_indicator` 数据加载和 PIT 对齐。
4. 实现 `bear_defensive_score` 与 3 个实验变体。
5. 运行实验并生成对比：
   - 当前 `v4` / `v5` / `v6`
   - 新增变体
   - 年度、月度、全周期
6. 生成 HTML 报表，给出是否建议合并。
7. 做一次独立代码复审，再修正明显问题。

## 验证命令

```powershell
python -m py_compile scripts\bbi\backtrader\tmp\tmp_v5_bear_defensive_quality_experiment.py
python -m unittest scripts\bbi\backtrader\tmp\test_tmp_v5_bear_defensive_quality.py -v
python -X utf8 scripts\bbi\backtrader\tmp\tmp_v5_bear_defensive_quality_experiment.py
```

