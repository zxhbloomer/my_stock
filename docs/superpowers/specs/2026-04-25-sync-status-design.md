# sync_status 增量同步设计文档

**日期：** 2026-04-25  
**范围：** `data/手动执行/new/` 目录下所有同步脚本  
**状态：** 待实现

---

## 背景与问题

现有脚本通过 `get_max_date()` 查各自数据表的 `MAX(trade_date)` 来确定增量起点，并用 `LOOKBACK_DAYS`（3~90天）回退作为安全边际。

存在两个问题：
1. **无法区分中断与完成**：脚本中途崩溃时，数据库里可能只写了一半，但 `MAX(trade_date)` 看起来正常，下次运行会跳过该天
2. **LOOKBACK 浪费**：每次都回退 N 天重跑，产生大量无意义的重复 API 请求

---

## 解决方案：sync_status 表

新建一张集中管理同步状态的表，每个脚本一条记录，记录"同步到哪天"和"是否完成"。

---

## 一、数据库表结构

```sql
CREATE TABLE tushare_v2.sync_status (
    script_name  VARCHAR(64)  NOT NULL,
    table_name   VARCHAR(64)  NOT NULL,
    sync_date    DATE         NOT NULL,
    status       VARCHAR(8)   NOT NULL CHECK (status IN ('ing', 'ok')),
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (script_name)
);
```

字段说明：
- `script_name`：脚本文件名，如 `014_daily.py`，主键，每脚本唯一一条记录
- `table_name`：对应数据表名，如 `014_daily`，便于查询时关联
- `sync_date`：数据日期（B类=当天交易日；C类=本次同步的end日期）
- `status`：`ing`=正在处理或中途中断；`ok`=该日期数据已完整写入
- `updated_at`：记录最后更新时间，用于监控

---

## 二、脚本分类与处理策略

### A 类：全量刷新（6个脚本，不接入）

| 脚本 | 表名 | 行数 |
|---|---|---:|
| 001_stock_basic.py | 001_stock_basic | 5,834 |
| 003_trade_cal.py | 003_trade_cal | 12,000 |
| 005_st.py | 005_st | 998 |
| 008_stock_company.py | 008_stock_company | 6,272 |
| 121_index_basic.py | 121_index_basic | 12,456 |
| 134_ci_index_member.py | 134_ci_index_member | 7,893 |

数据量小（总计4.5万行），全量 truncate+insert 耗时秒级，无需增量状态管理，保持原有逻辑不变。

---

### B 类：按交易日循环（28个脚本）

**循环结构：** 外层按 `trade_cal` 交易日循环，每天拉全市场数据。

**sync_date 语义：** 当天交易日（如 `2026-04-24`）。

**状态流转：**
```
脚本启动 → 读 sync_status → 确定 start
  ↓
for d in dates:
    mark_sync(ing, d)   ← 开始处理该天
    upsert 全市场数据
    mark_sync(ok, d)    ← 该天完整写入
```

**增量起点逻辑：**
- 无记录（首次）→ `DEFAULT_START`（全量）
- `status=ok` → `sync_date + 1天`（精确增量）
- `status=ing` → `sync_date`（从中断日重跑）

**去掉 LOOKBACK_DAYS**，由 sync_status 精确控制，不再盲目回退。

B 类脚本清单（28个）：

| 脚本 | 最新日期 | 状态 |
|---|---|---|
| 004_stock_st.py | 2026-04-24 | 正常 |
| 006_stock_hsgt.py | NULL（空表） | 待同步 |
| 014_daily.py | 2026-04-24 | 正常 |
| 018_weekly.py | 2026-04-17 | 正常（周线） |
| 019_monthly.py | 2026-03-31 | 正常（月线） |
| 023_adj_factor.py | 2026-04-24 | 正常 |
| 027_daily_basic.py | 2026-04-24 | 正常 |
| 029_stk_limit.py | 2026-04-24 | 正常 |
| 030_suspend_d.py | 2026-04-24 | 正常 |
| 031_hsgt_top10.py | 2026-04-24 | 正常 |
| 032_ggt_top10.py | 2026-04-24 | 正常 |
| 063_stk_factor_pro.py | 2026-04-24 | 正常 |
| 066_hk_hold.py | 2026-04-13 | 落后 |
| 068_stk_auction_c.py | 无表 | 待建表 |
| 073_margin.py | 2026-04-17 | 落后 |
| 074_margin_detail.py | 2026-04-17 | 落后 |
| 075_margin_secs.py | 2026-04-17 | 落后 |
| 076_slb_sec.py | 2024-09-30 | 严重落后 |
| 077_slb_len.py | 2025-07-25 | 落后 |
| 078_slb_sec_detail.py | 2024-07-10 | 严重落后 |
| 080_moneyflow.py | 2026-04-17 | 落后 |
| 081_moneyflow_ths.py | 2026-04-17 | 落后 |
| 087_moneyflow_hsgt.py | 2026-04-17 | 落后 |
| 129_index_dailybasic.py | 2026-04-17 | 落后 |
| 135_ci_daily.py | 2016-04-22 | 严重落后 |
| 137_idx_factor_pro.py | 无表 | 待建表 |
| 138_daily_info.py | 无表 | 待建表 |
| 139_sz_daily_info.py | 无表 | 待建表 |

---

### C1/C3 类：按股票/指数循环（4个脚本，trade_date）

**循环结构：** 外层按 `ts_code` 循环，每只股票拉一段日期范围。

**sync_date 语义：** 本次同步的 `end` 日期（即 `args.end`，通常为今天）。

**状态流转：**
```
脚本启动 → mark_sync(ing, end_date)
  ↓
for code in all_codes:
    upsert(ts_code=code, start~end)
  ↓
mark_sync(ok, end_date)
```

中断后重跑：`sync_date` 是上次 `end` 日期，`get_sync_start` 返回该日期作为新的 `start`，重跑全部股票，upsert 幂等无害。

| 脚本 | 总行数 | 最新日期 |
|---|---:|---|
| 061_cyq_perf.py | 9,094,225 | 2026-04-16 |
| 062_cyq_chips.py | 4,656,722 | 2026-04-16 |
| 069_stk_nineturn.py | 4,067,259 | 2026-04-17 |
| 122_index_daily.py | 3,544,024 | 2026-04-17 |

---

### C2 类：财务类按股票循环（8个脚本，ann_date）

**循环结构：** 外层按 `ts_code` 循环，日期字段为 `ann_date`（公告日），不走 `trade_cal`。

**sync_date 语义：** 本次同步的 `end` 日期（`args.end`，通常为今天）。

**增量起点：** `get_sync_start` 返回上次 `sync_date`，作为新的 `start`，LOOKBACK 由各脚本自身的 90 天窗口保证。

| 脚本 | 总行数 | 最新ann_date |
|---|---:|---|
| 036_income.py | 265,021 | 2026-04-24 |
| 037_balancesheet.py | 257,772 | 2026-04-24 |
| 038_cashflow.py | 254,695 | 2026-04-25 |
| 039_forecast.py | 87,396 | 2026-04-24 |
| 040_express.py | 26,451 | 2026-04-11 |
| 041_dividend.py | 89,248 | 2026-04-14 |
| 042_fina_indicator.py | 268,503 | 2026-04-14 |
| 043_fina_audit.py | 75,137 | 2026-04-14 |

---

## 三、`_common.py` 新增函数

### `ensure_sync_status_table(engine)`
建表函数，在 `ensure_schema` 之后调用一次。

### `get_sync_start(engine, script_name, default_start, date_col='trade_date')`

```
无记录       → default_start          （首次全量）
status=ok   → sync_date + 1天        （精确增量）
status=ing  → sync_date              （从中断日重跑）
```

### `mark_sync(engine, script_name, table_name, date, status)`

upsert 一条记录，`date` 格式为 `YYYYMMDD` 或 `datetime`。
`updated_at` 必须在 upsert SQL 里显式写 `updated_at = CURRENT_TIMESTAMP`，不能依赖 `DEFAULT`（DEFAULT 只在 INSERT 时生效）。

---

## 四、各类脚本改动量

| 类型 | 脚本数 | 改动内容 |
|---|---|---|
| A 类 | 6 | 不改动 |
| B 类 | 28 | 替换 `get_start()` + 循环内加 2 行 `mark_sync` |
| C1/C3 类 | 4 | 替换 `get_start()` + 脚本首尾各加 1 行 `mark_sync` |
| C2 类 | 8 | 替换 `get_start()` + 脚本首尾各加 1 行 `mark_sync` |
| `_common.py` | 1 | 新增 3 个函数 |

---

## 五、首次运行（无数据）行为

1. `sync_status` 无记录 → `get_sync_start` 返回 `DEFAULT_START`
2. 脚本从历史起点全量拉取
3. B 类：每天写 `ing`→`ok`，中断可从断点续跑
4. C 类：启动写 `ing`，完成写 `ok`，中断后重跑全部股票

---

## 六、边界情况补充

- 今天是非交易日：B 类 `dates` 列表为空直接跳过；C 类 `end=today` 无影响
- 某天数据 Tushare 端异常：现有 `except` 直接 SKIP 跳过，不会卡住，该天数据缺失但不阻塞后续日期
- 时区：`TODAY` 统一用北京时间 `datetime.now(pytz.timezone('Asia/Shanghai')).strftime('%Y%m%d')`
- `003_trade_cal` 必须第一个执行，B 类脚本依赖它确定交易日列表

---

## 七、不在本次范围内

- `068_stk_auction_c`、`137_idx_factor_pro`、`138_daily_info`、`139_sz_daily_info` 四个无表脚本：先建表再接入，逻辑同 B 类
- `135_ci_daily` 严重落后（2016年）：接入后首次运行会触发全量补数，耗时较长，属正常行为
