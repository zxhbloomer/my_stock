# Tushare 龙虎榜接口同步设计

## 背景

新增 `top_list` 与 `top_inst` 两个 Tushare 接口同步脚本，对应 `docs/tushare/接口清单.md` 中的 088 与 089。

## 数据结构

字段完全按本地 Tushare 文档定义：

- `top_list`: `trade_date,ts_code,name,close,pct_change,turnover_rate,amount,l_sell,l_buy,l_amount,net_amount,net_rate,amount_rate,float_values,reason`
- `top_inst`: `trade_date,ts_code,exalter,side,buy,buy_rate,sell,sell_rate,net_buy,reason`

两个表都使用数据库自增主键 `id BIGSERIAL PRIMARY KEY`。不使用 `trade_date + ts_code` 作为主键，因为官方样例和实测数据都显示同一交易日同一股票可能有多条龙虎榜记录。

## 同步策略

同步水位仍使用 `sync_status`，按交易日正序增量。每个交易日先标记 `ing`，拉取该日全量接口数据后，按 `trade_date` 删除目标表已有数据并重插当天结果，成功后标记 `ok`。如果某天接口无数据，也删除该日旧数据并标记成功。

## 查询索引

- `088_top_list`: `(trade_date, ts_code)`
- `089_top_inst`: `(trade_date, ts_code)` 与 `(trade_date, exalter)`

## 验证

新增静态测试约束脚本结构、主键策略和按日替换函数调用。由于当前环境没有安装 `pytest`，可用 `python -X utf8 -c` 直接调用测试函数。
