# Missing Tushare Sync Scripts Design

## Scope

Add backend-only Tushare V2 sync coverage for missing interfaces in
`data/手动执行/20260425`. No frontend entry, strategy logic, database migration from
old schemas, or git operation is included.

## Interfaces

Create scripts for:

- `021_stk_weekly_monthly`
- `022_stk_week_month_adj`
- `082_moneyflow_dc`
- `083_moneyflow_cnt_ths`
- `084_moneyflow_ind_ths`
- `085_moneyflow_ind_dc`
- `086_moneyflow_mkt_dc`
- `091_limit_list_d`
- `092_limit_step`

## Architecture

Each new script follows the existing one-file-per-interface pattern. Scripts use
`_common.py` for Tushare initialization, schema creation, field validation,
trade-date enumeration, upserts, whole-day replacement, and `sync_status`
tracking.

`021` and `022` loop over `freq in ["week", "month"]` for each eligible trade
date. `085` loops over `content_type in ["行业", "概念", "地域"]`. `091` loops
over `limit_type in ["U", "D", "Z"]`.

## Incremental Behavior

All scripts support `--start YYYYMMDD` and `--end YYYYMMDD`. Without `--start`,
they read `sync_status` through `get_sync_start()`. During each date, the script
marks status `ing`; after successful writes it marks the date `ok`.

## Tables and Keys

- `021`: primary key `(ts_code, trade_date, freq)`
- `022`: primary key `(ts_code, trade_date, freq)`
- `082`: primary key `(trade_date, ts_code)`
- `083`: primary key `(trade_date, ts_code)`
- `084`: primary key `(trade_date, ts_code)`
- `085`: primary key `(trade_date, content_type, ts_code)`
- `086`: primary key `(trade_date)`
- `091`: primary key `(trade_date, ts_code, limit)`
- `092`: primary key `(trade_date, ts_code, nums)`

Where the interface response is naturally a full-day snapshot with duplicated
rows possible, use conservative keys only when the local Tushare docs identify
stable business dimensions. Otherwise preserve the existing whole-day replace
pattern used by `088_top_list.py` and `089_top_inst.py`.

## Integration

Update:

- `run_all.py`
- `run_all-001~040.py`
- `run_all-041~139.py`
- `_check_status.py`
- `_check_status2.py`
- `_check_status3.py`
- `_check_dates.py`
- `_check_dates2.py`
- `new_readme.md`

## Verification

Use a static metadata verification script before and after implementation. Then
run `python -m py_compile` on the new and modified Python files. Runtime database
verification should use a narrow date range per script because some interfaces
require high Tushare points.

