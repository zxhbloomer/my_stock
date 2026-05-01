# sync_status 增量同步 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `tushare_v2` schema 新建 `sync_status` 表，改造所有增量脚本，实现精确断点续跑，去掉 LOOKBACK_DAYS 盲目回退。

**Architecture:** `_common.py` 新增3个函数（建表、读状态、写状态），B类脚本在日期循环内打 ing/ok 标记，C类脚本在脚本首尾打标记，A类不改动。`TODAY` 统一改为北京时间。

**Tech Stack:** Python 3.11, SQLAlchemy 2.x, psycopg2, PostgreSQL 17, pytz

---

## 文件改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| `data/手动执行/20260425/_common.py` | 修改 | 新增3个函数，TODAY改北京时间 |
| `data/手动执行/20260425/014_daily.py` | 修改 | B类代表，替换get_start+加mark_sync |
| `data/手动执行/20260425/004_stock_st.py` | 修改 | B类 |
| `data/手动执行/20260425/006_stock_hsgt.py` | 修改 | B类 |
| `data/手动执行/20260425/018_weekly.py` | 修改 | B类 |
| `data/手动执行/20260425/019_monthly.py` | 修改 | B类 |
| `data/手动执行/20260425/023_adj_factor.py` | 修改 | B类 |
| `data/手动执行/20260425/027_daily_basic.py` | 修改 | B类 |
| `data/手动执行/20260425/029_stk_limit.py` | 修改 | B类 |
| `data/手动执行/20260425/030_suspend_d.py` | 修改 | B类 |
| `data/手动执行/20260425/031_hsgt_top10.py` | 修改 | B类 |
| `data/手动执行/20260425/032_ggt_top10.py` | 修改 | B类 |
| `data/手动执行/20260425/063_stk_factor_pro.py` | 修改 | B类 |
| `data/手动执行/20260425/066_hk_hold.py` | 修改 | B类 |
| `data/手动执行/20260425/073_margin.py` | 修改 | B类 |
| `data/手动执行/20260425/074_margin_detail.py` | 修改 | B类 |
| `data/手动执行/20260425/075_margin_secs.py` | 修改 | B类 |
| `data/手动执行/20260425/076_slb_sec.py` | 修改 | B类 |
| `data/手动执行/20260425/077_slb_len.py` | 修改 | B类 |
| `data/手动执行/20260425/078_slb_sec_detail.py` | 修改 | B类 |
| `data/手动执行/20260425/080_moneyflow.py` | 修改 | B类 |
| `data/手动执行/20260425/081_moneyflow_ths.py` | 修改 | B类 |
| `data/手动执行/20260425/087_moneyflow_hsgt.py` | 修改 | B类 |
| `data/手动执行/20260425/129_index_dailybasic.py` | 修改 | B类 |
| `data/手动执行/20260425/135_ci_daily.py` | 修改 | B类 |
| `data/手动执行/20260425/061_cyq_perf.py` | 修改 | C1类 |
| `data/手动执行/20260425/062_cyq_chips.py` | 修改 | C1类 |
| `data/手动执行/20260425/069_stk_nineturn.py` | 修改 | C1类 |
| `data/手动执行/20260425/122_index_daily.py` | 修改 | C3类 |
| `data/手动执行/20260425/036_income.py` | 修改 | C2类 |
| `data/手动执行/20260425/037_balancesheet.py` | 修改 | C2类 |
| `data/手动执行/20260425/038_cashflow.py` | 修改 | C2类 |
| `data/手动执行/20260425/039_forecast.py` | 修改 | C2类 |
| `data/手动执行/20260425/040_express.py` | 修改 | C2类 |
| `data/手动执行/20260425/041_dividend.py` | 修改 | C2类 |
| `data/手动执行/20260425/042_fina_indicator.py` | 修改 | C2类 |
| `data/手动执行/20260425/043_fina_audit.py` | 修改 | C2类 |
| `data/手动执行/20260425/run_all.py` | 修改 | 003_trade_cal调整为第一位 |

---

## Task 1: 修改 `_common.py` — 新增3个函数，TODAY改北京时间

**Files:**
- Modify: `data/手动执行/20260425/_common.py`

- [ ] **Step 1: 修改 TODAY 为北京时间**

在 `_common.py` 顶部找到：
```python
from datetime import datetime
```
改为：
```python
from datetime import datetime
import pytz
```

找到：
```python
TODAY    = datetime.today().strftime("%Y%m%d")
```
改为：
```python
TODAY    = datetime.now(pytz.timezone('Asia/Shanghai')).strftime("%Y%m%d")
```

- [ ] **Step 2: 新增 `ensure_sync_status_table` 函数**

在 `_common.py` 的 `ensure_schema` 函数之后添加：

```python
SYNC_STATUS_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.sync_status (
    script_name  VARCHAR(64)  NOT NULL,
    table_name   VARCHAR(64)  NOT NULL,
    sync_date    DATE         NOT NULL,
    status       VARCHAR(8)   NOT NULL CHECK (status IN ('ing', 'ok')),
    updated_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (script_name)
);
"""

def ensure_sync_status_table(engine):
    with engine.begin() as conn:
        conn.execute(text(SYNC_STATUS_SQL))
```

- [ ] **Step 3: 新增 `get_sync_start` 函数**

紧接上面函数之后添加：

```python
def get_sync_start(engine, script_name: str, default_start: str) -> str:
    """
    读取 sync_status，返回本次应从哪天开始同步。
    - 无记录（首次）→ default_start（全量）
    - status=ing    → sync_date（从中断日重跑）
    - status=ok     → sync_date + 1天（精确增量，无 LOOKBACK）
    """
    try:
        with engine.connect() as conn:
            r = conn.execute(text(
                f"SELECT sync_date, status FROM {SCHEMA}.sync_status WHERE script_name=:s"
            ), {"s": script_name}).fetchone()
    except Exception:
        return default_start
    if r is None:
        return default_start
    if r[1] == 'ing':
        return pd.Timestamp(r[0]).strftime("%Y%m%d")
    # status='ok'，从下一个自然日开始（trade_cal 会过滤非交易日）
    return (pd.Timestamp(r[0]) + pd.Timedelta(days=1)).strftime("%Y%m%d")
```

- [ ] **Step 4: 新增 `mark_sync` 函数**

紧接上面函数之后添加：

```python
def mark_sync(engine, script_name: str, table_name: str, date, status: str):
    """
    upsert 一条 sync_status 记录。
    date 可以是 'YYYYMMDD' 字符串或 datetime/Timestamp。
    updated_at 显式赋值，不依赖 DEFAULT（DEFAULT 只在 INSERT 时生效）。
    """
    if isinstance(date, str):
        date = pd.Timestamp(date)
    with engine.begin() as conn:
        conn.execute(text(f"""
            INSERT INTO {SCHEMA}.sync_status
                (script_name, table_name, sync_date, status, updated_at)
            VALUES (:s, :t, :d, :st, CURRENT_TIMESTAMP)
            ON CONFLICT (script_name) DO UPDATE SET
                table_name = EXCLUDED.table_name,
                sync_date  = EXCLUDED.sync_date,
                status     = EXCLUDED.status,
                updated_at = CURRENT_TIMESTAMP
        """), {"s": script_name, "t": table_name, "d": date.date() if hasattr(date, 'date') else date, "st": status})
```

- [ ] **Step 5: 验证语法**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -c "from _common import get_sync_start, mark_sync, ensure_sync_status_table; print('OK')"
```

期望输出：`OK`

- [ ] **Step 6: 验证建表和读写**

```bash
python -X utf8 -c "
from _common import get_engine, ensure_schema, ensure_sync_status_table, get_sync_start, mark_sync
engine = get_engine()
ensure_schema(engine)
ensure_sync_status_table(engine)
# 首次读取应返回 default_start
start = get_sync_start(engine, '_test_.py', '20200101')
print('首次start:', start)
assert start == '20200101', f'期望20200101，得到{start}'
# 写入 ing
mark_sync(engine, '_test_.py', '_test_', '20260424', 'ing')
start = get_sync_start(engine, '_test_.py', '20200101')
print('ing后start:', start)
assert start == '20260424', f'期望20260424，得到{start}'
# 写入 ok
mark_sync(engine, '_test_.py', '_test_', '20260424', 'ok')
start = get_sync_start(engine, '_test_.py', '20200101')
print('ok后start:', start)
assert start == '20260425', f'期望20260425，得到{start}'
# 清理测试数据
from sqlalchemy import text
from _common import SCHEMA
with engine.begin() as conn:
    conn.execute(text(f\"DELETE FROM {SCHEMA}.sync_status WHERE script_name='_test_.py'\"))
print('全部断言通过')
"
```

期望输出：
```
首次start: 20200101
ing后start: 20260424
ok后start: 20260425
全部断言通过
```

---

## Task 2: 修改 B 类代表脚本 `014_daily.py`

**Files:**
- Modify: `data/手动执行/20260425/014_daily.py`

- [ ] **Step 1: 删除 LOOKBACK_DAYS，修改 get_start 函数**

找到并删除：
```python
LOOKBACK_DAYS = 3
```

找到整个 `get_start` 函数：
```python
def get_start(engine):
    max_d = get_max_date(engine, TABLE)
    if max_d:
        start = (pd.Timestamp(max_d) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        print(f"[增量] {TABLE} 最新={max_d}，从 {start} 开始")
        return start
    return DEFAULT_START
```

替换为：
```python
def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start
```

- [ ] **Step 2: 在 main() 中加入建表调用**

找到：
```python
    ensure_schema(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)
```

改为：
```python
    ensure_schema(engine)
    ensure_sync_status_table(engine)
    check_or_create_table(engine, TABLE, CREATE_SQL, COLS)
```

- [ ] **Step 3: 在日期循环内加 mark_sync**

找到：
```python
    for i, d in enumerate(dates, 1):
        try:
            df = pro.daily(trade_date=d, fields=FIELDS)
```

改为：
```python
    for i, d in enumerate(dates, 1):
        mark_sync(engine, f"{TABLE}.py", TABLE, d, "ing")
        try:
            df = pro.daily(trade_date=d, fields=FIELDS)
```

找到循环内 upsert 之后、except 之前的位置：
```python
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
        except Exception as e:
```

改为：
```python
                rows = upsert_df(engine, df, TABLE, COLS, PK)
                total_rows += rows
            else:
                rows = 0
            mark_sync(engine, f"{TABLE}.py", TABLE, d, "ok")
        except Exception as e:
```

注意：`mark_sync ok` 放在 `else` 之后、`except` 之前，确保只有成功时才标 ok；异常时保持 ing 状态。

- [ ] **Step 4: 验证脚本语法**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -m py_compile 014_daily.py && echo "语法OK"
```

期望输出：`语法OK`

---

## Task 3: 批量改造其余 B 类脚本（27个）

每个脚本的改动模式与 Task 2 完全相同：
1. 删除 `LOOKBACK_DAYS = N` 这一行
2. 替换 `get_start` 函数体为 `get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)`
3. `ensure_sync_status_table(engine)` 加到 `ensure_schema` 之后
4. 循环内 `mark_sync(ing)` 加在 `try:` 之前
5. `mark_sync(ok)` 加在 upsert 成功之后、`except` 之前

**Files:** 以下27个脚本，逐一按上述模式修改：

`004_stock_st.py`, `006_stock_hsgt.py`, `018_weekly.py`, `019_monthly.py`,
`023_adj_factor.py`, `027_daily_basic.py`, `029_stk_limit.py`, `030_suspend_d.py`,
`031_hsgt_top10.py`, `032_ggt_top10.py`, `063_stk_factor_pro.py`, `066_hk_hold.py`,
`073_margin.py`, `074_margin_detail.py`, `075_margin_secs.py`, `076_slb_sec.py`,
`077_slb_len.py`, `078_slb_sec_detail.py`, `080_moneyflow.py`, `081_moneyflow_ths.py`,
`087_moneyflow_hsgt.py`, `129_index_dailybasic.py`, `135_ci_daily.py`

- [ ] **Step 1: 批量修改所有 B 类脚本**

逐一打开每个脚本，按 Task 2 的模式修改。

- [ ] **Step 2: 批量验证语法**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -m py_compile 004_stock_st.py 006_stock_hsgt.py 018_weekly.py 019_monthly.py 023_adj_factor.py 027_daily_basic.py 029_stk_limit.py 030_suspend_d.py 031_hsgt_top10.py 032_ggt_top10.py 063_stk_factor_pro.py 066_hk_hold.py 073_margin.py 074_margin_detail.py 075_margin_secs.py 076_slb_sec.py 077_slb_len.py 078_slb_sec_detail.py 080_moneyflow.py 081_moneyflow_ths.py 087_moneyflow_hsgt.py 129_index_dailybasic.py 135_ci_daily.py && echo "全部语法OK"
```

期望输出：`全部语法OK`

---

## Task 4: 改造 C1/C3 类脚本（4个）

C 类脚本的 `mark_sync` 在脚本级别打标，不在日期循环内。

**Files:**
- Modify: `data/手动执行/20260425/061_cyq_perf.py`
- Modify: `data/手动执行/20260425/062_cyq_chips.py`
- Modify: `data/手动执行/20260425/069_stk_nineturn.py`
- Modify: `data/手动执行/20260425/122_index_daily.py`

- [ ] **Step 1: 修改 `061_cyq_perf.py`**

删除：
```python
LOOKBACK_DAYS = 7
```

替换 `get_start` 函数：
```python
def get_start(engine):
    start = get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)
    print(f"[增量] {TABLE} 从 {start} 开始")
    return start
```

在 `main()` 的 `ensure_schema` 之后加：
```python
    ensure_sync_status_table(engine)
```

在股票循环开始前加 `ing` 标记（找到 `total_rows, t0 = 0, datetime.now()` 之后）：
```python
    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")
    total_rows, t0 = 0, datetime.now()
    for i, code in enumerate(codes, 1):
```

在 `print(f"\n[完成]...")` 之前加 `ok` 标记：
```python
    mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")
    print(f"\n[完成] upsert {total_rows:,} 条")
```

- [ ] **Step 2: 同样模式修改 `062_cyq_chips.py`、`069_stk_nineturn.py`、`122_index_daily.py`**

模式完全相同：删 LOOKBACK_DAYS，替换 get_start，加 ensure_sync_status_table，循环前 mark ing，完成后 mark ok。

- [ ] **Step 3: 批量验证语法**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -m py_compile 061_cyq_perf.py 062_cyq_chips.py 069_stk_nineturn.py 122_index_daily.py && echo "全部语法OK"
```

期望输出：`全部语法OK`

---

## Task 5: 改造 C2 类财务脚本（8个）

C2 类与 C1 相同，区别是 `get_sync_start` 的 `default_start` 用各脚本自己的 `DEFAULT_START`，`mark_sync` 的 `date` 用 `args.end`。

**Files:**
- Modify: `data/手动执行/20260425/036_income.py`
- Modify: `data/手动执行/20260425/037_balancesheet.py`
- Modify: `data/手动执行/20260425/038_cashflow.py`
- Modify: `data/手动执行/20260425/039_forecast.py`
- Modify: `data/手动执行/20260425/040_express.py`
- Modify: `data/手动执行/20260425/041_dividend.py`
- Modify: `data/手动执行/20260425/042_fina_indicator.py`
- Modify: `data/手动执行/20260425/043_fina_audit.py`

- [ ] **Step 1: 逐一修改8个财务脚本**

每个脚本的改动：
1. 删除 `LOOKBACK_DAYS = 90`
2. 替换 `get_start` 函数体为 `get_sync_start(engine, f"{TABLE}.py", DEFAULT_START)`
3. `ensure_sync_status_table(engine)` 加到 `ensure_schema` 之后
4. 股票循环前加 `mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ing")`
5. `print("[完成]...")` 前加 `mark_sync(engine, f"{TABLE}.py", TABLE, args.end, "ok")`

- [ ] **Step 2: 批量验证语法**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -m py_compile 036_income.py 037_balancesheet.py 038_cashflow.py 039_forecast.py 040_express.py 041_dividend.py 042_fina_indicator.py 043_fina_audit.py && echo "全部语法OK"
```

期望输出：`全部语法OK`

---

## Task 6: 修改 `run_all.py` — 调整执行顺序

**Files:**
- Modify: `data/手动执行/20260425/run_all.py`

- [ ] **Step 1: 将 `003_trade_cal.py` 调整为第一位**

找到 `SCRIPTS` 列表，将：
```python
SCRIPTS = [
    # ── 基础数据 ──────────────────────────────────────────────
    "001_stock_basic.py",
    # ...
    "003_trade_cal.py",
```

改为：
```python
SCRIPTS = [
    # ── 基础数据（003_trade_cal 必须第一个，B类脚本依赖它确定交易日）──
    "003_trade_cal.py",
    "001_stock_basic.py",
```

- [ ] **Step 2: 验证语法**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -m py_compile run_all.py && echo "语法OK"
```

---

## Task 7: 端到端验证

- [ ] **Step 1: 验证 sync_status 表存在**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 -c "
from _common import get_engine, SCHEMA
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    r = conn.execute(text(
        f\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='{SCHEMA}' AND table_name='sync_status'\"
    )).fetchone()
    print('sync_status表存在:', r[0] == 1)
"
```

期望输出：`sync_status表存在: True`

- [ ] **Step 2: 用 014_daily.py 跑单天验证**

```bash
cd "D:\2026_project\10_quantify\00_py\my_stock\data\手动执行\new"
python -X utf8 014_daily.py --start 20260424 --end 20260424
```

期望：正常完成，无报错。

- [ ] **Step 3: 验证 sync_status 记录写入正确**

```bash
python -X utf8 -c "
from _common import get_engine, SCHEMA
from sqlalchemy import text
engine = get_engine()
with engine.connect() as conn:
    rows = conn.execute(text(
        f\"SELECT script_name, table_name, sync_date, status, updated_at FROM {SCHEMA}.sync_status ORDER BY updated_at DESC LIMIT 5\"
    )).fetchall()
    for r in rows:
        print(r)
"
```

期望：看到 `014_daily.py` 的记录，`status=ok`，`sync_date=2026-04-24`，`updated_at` 是刚才的时间。

- [ ] **Step 4: 验证再次运行时从正确日期开始**

```bash
python -X utf8 014_daily.py
```

期望：输出 `[增量] 014_daily 从 20260425 开始`（即 ok日期+1天），不再从 20260421（LOOKBACK 3天）开始。
