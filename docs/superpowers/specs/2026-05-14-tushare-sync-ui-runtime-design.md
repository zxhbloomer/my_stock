# Tushare 同步 UI 任务总数与耗时设计

## 目标

在 `data/ui` 同步页面增加任务总数展示、调整顶部标题布局，并为每个脚本任务显示可动态更新的耗时。耗时使用 `sync_status` 表中的开始/结束时间保存，前端按时间差格式化显示。

## 顶部布局

- 第一行只显示标题：`数据同步窗口（X）`。
- `X` 来自当前 `/api/jobs` 返回的脚本任务数量，即 `run_all.py` 白名单数量。
- 第二行显示目标日期和操作按钮：目标日期、全部同步、选择脚本执行、校验今日同步、刷新。
- 标题和工具栏仍位于最上方，不改变下方表格/日志上下 50% 的布局目标。

## 数据库字段

在 `tushare_v2.sync_status` 增加两个字段：

```sql
last_start_at TIMESTAMP
last_end_at   TIMESTAMP
```

选择两个字段而不是一个耗时字段，原因是：

- 运行中可以用 `当前时间 - last_start_at` 动态显示耗时。
- 结束后可以用 `last_end_at - last_start_at` 显示最后一次运行耗时。
- 失败或强制停止也可以记录本次实际运行区间。

后端会执行轻量迁移：

```sql
CREATE SCHEMA IF NOT EXISTS tushare_v2;
CREATE TABLE IF NOT EXISTS tushare_v2.sync_status (..., last_start_at TIMESTAMP, last_end_at TIMESTAMP);
ALTER TABLE tushare_v2.sync_status ADD COLUMN IF NOT EXISTS last_start_at TIMESTAMP;
ALTER TABLE tushare_v2.sync_status ADD COLUMN IF NOT EXISTS last_end_at TIMESTAMP;
```

## 写入规则

- 脚本开始运行时：
  - 如果该脚本已有 `sync_status` 行，则写 `last_start_at = 当前时间`，`last_end_at = NULL`。
  - 如果没有该脚本行，不创建脚本行，避免错误改写 `sync_date` 并影响同步起点。
- 脚本结束、失败、强制停止时：
  - 写 `last_end_at = 当前时间`。
  - 如果脚本运行期间自身创建了 `sync_status` 行，同时补写本次 `last_start_at`。
- 不改写已有 `sync_date` 和 `status` 语义。

## 前端显示

表格“运行时间”列使用以下数据源：

- 后端任务状态中脚本正在运行时，优先使用任务内存中的开始时间动态计算。
- 否则使用 `last_start_at` 和 `last_end_at` 计算最后一次耗时。
- 如果缺少开始或结束时间，显示 `-`。

格式规则：

- 小于 60 秒：`xx秒`
- 小于 1 小时：`99.99分钟`
- 大于等于 1 小时：`99.99小时`

## 测试与验证

- 单元测试覆盖：
  - 读取 `sync_status` 时返回 `last_start_at` / `last_end_at`。
  - 启动脚本时记录开始时间并清空结束时间。
  - 脚本结束时记录结束时间。
  - 无脚本行时开始记录不插入新行。
  - 耗时格式化边界。
- 静态检查覆盖标题任务数、第二行目标日期、运行时间字段和新增 SQL 字段。
- 不运行真实 Tushare 同步脚本。

## 边界

- 不记录历史多次运行，只保留最后一次运行的 start/end。
- 直接运行单个同步脚本但不经过 UI 时，不会写 UI 的耗时字段，除非之后通过 UI 执行。
- 不执行任何 git 操作。
