# 指数日线数据导入功能设计文档

## 文档信息

- **功能名称**: Tushare Pro指数日线数据导入
- **设计日期**: 2025-11-16
- **设计人员**: AI Assistant with User
- **开发流程阶段**: Stage 4 - 设计文档编写

---

## 1. 需求概述

### 1.1 业务背景

**问题描述**:
- Qlib量化回测系统需要指数数据作为基准(benchmark)进行策略评估
- 当前系统缺少指数日线数据,导致报错: `ValueError: The benchmark ['SH000300'] does not exist`
- 需要支持沪深300(SH000300)、中证500(SH000905)等主要指数的历史和实时数据导入

**业务价值**:
- ✅ 支持策略回测的基准对比分析
- ✅ 提供市场整体走势数据
- ✅ 完善数据采集系统的数据完整性

### 1.2 功能需求

#### 核心功能
1. **数据源集成**: 对接Tushare Pro `index_daily` API接口
2. **数据存储**: 存储指数日线OHLCV数据到PostgreSQL数据库
3. **更新模式支持**:
   - **智能增量更新**: 自动检测数据库最新日期,从最新日期+1开始更新(含3天回看窗口)
   - **手动增量更新**: 用户指定start_date和end_date范围更新
   - **全量更新**: 从历史起始日期到当前日期的完整数据导入
4. **GUI集成**: 在数据采集界面添加"指数日线"任务入口
5. **批量处理**: 支持多指数并发导入,自动分批避免API限制

#### 非功能需求
- **性能**: 单指数全量导入(约10年数据)< 5分钟
- **稳定性**: 支持断点续传,失败自动重试
- **兼容性**: 完全遵循项目现有架构和编码规范
- **可维护性**: 使用中文注释,清晰的日志记录

---

## 2. 技术设计

### 2.1 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    GUI Layer (主窗口)                     │
│  data/gui/main_window.py                               │
│  - 数据采集任务列表                                        │
│  - 任务执行控制面板                                        │
└──────────────────┬──────────────────────────────────────┘
                   │ async handle_request()
                   ↓
┌─────────────────────────────────────────────────────────┐
│              Controller Layer (控制器)                    │
│  data/gui/controller.py                                 │
│  - 任务调度与协调                                          │
│  - 进度反馈                                               │
└──────────────────┬──────────────────────────────────────┘
                   │ execute_task()
                   ↓
┌─────────────────────────────────────────────────────────┐
│           Task Layer (任务实现层)                         │
│  data/collectors/tasks/stock/tushare_index_daily.py     │
│                                                         │
│  [TushareIndexDailyTask]                                │
│  ├─ 继承: TushareTask → FetcherTask → BaseTask          │
│  ├─ get_batch_list(): 生成批次参数                        │
│  ├─ 配置: api_name, fields, validations                 │
│  └─ 自动注册: @task_register()                           │
└──────────────────┬──────────────────────────────────────┘
                   │
      ┌────────────┴────────────┐
      │                         │
      ↓                         ↓
┌──────────────┐     ┌──────────────────────┐
│  Tushare API │     │   PostgreSQL DB      │
│              │     │                      │
│ index_daily  │     │  tushare.index_daily │
│ 接口调用      │     │  表存储              │
└──────────────┘     └──────────────────────┘
```

### 2.2 类设计

#### 2.2.1 `TushareIndexDailyTask` 类定义

**文件路径**: `data/collectors/tasks/stock/tushare_index_daily.py`

**继承关系**:
```python
TushareIndexDailyTask → TushareTask → FetcherTask → BaseTask
```

**核心属性**:

| 属性名 | 类型 | 默认值 | 说明 |
|-------|-----|--------|------|
| `name` | str | `"tushare_index_daily"` | 任务唯一标识 |
| `description` | str | `"获取A股指数日线行情数据"` | 任务描述 |
| `table_name` | str | `"index_daily"` | 数据库表名 |
| `primary_keys` | List[str] | `["ts_code", "trade_date"]` | 复合主键 |
| `date_column` | str | `"trade_date"` | 日期列名 |
| `default_start_date` | str | `"19901219"` | 默认起始日期(A股开市日) |
| `smart_lookback_days` | int | `3` | 智能增量回看天数 |
| `api_name` | str | `"index_daily"` | Tushare API名称 |
| `fields` | List[str] | `["ts_code", "trade_date", ...]` | API返回字段 |
| `batch_trade_days_single_code` | int | `240` | 单指数批次大小(约1年) |
| `batch_trade_days_all_codes` | int | `5` | 全市场批次大小(1周) |

**核心方法**:

```python
async def get_batch_list(self, **kwargs) -> List[Dict]:
    """
    生成批处理参数列表

    Args:
        **kwargs: 包含start_date, end_date, ts_code等参数

    Returns:
        List[Dict]: 批处理参数列表,每个元素包含单批次的查询参数

    逻辑:
    1. 获取start_date和end_date,若未提供则使用默认值
    2. 根据是否指定ts_code选择批次大小
    3. 调用generate_trade_day_batches()生成交易日批次
    4. 返回批次列表供父类逐批调用API
    """
```

### 2.3 数据库设计

#### 2.3.1 表结构: `tushare.index_daily`

```sql
CREATE TABLE IF NOT EXISTS tushare.index_daily (
    ts_code VARCHAR(15) NOT NULL,           -- Tushare指数代码
    trade_date DATE NOT NULL,               -- 交易日期
    open FLOAT,                             -- 开盘点位
    high FLOAT,                             -- 最高点位
    low FLOAT,                              -- 最低点位
    close FLOAT,                            -- 收盘点位
    pre_close FLOAT,                        -- 昨收盘点位
    change FLOAT,                           -- 涨跌点位
    pct_chg FLOAT,                          -- 涨跌幅(%)
    volume FLOAT,                           -- 成交量(手)
    amount FLOAT,                           -- 成交额(千元)
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,  -- 数据更新时间

    PRIMARY KEY (ts_code, trade_date)
);

-- 索引定义
CREATE INDEX IF NOT EXISTS idx_index_daily_code ON tushare.index_daily(ts_code);
CREATE INDEX IF NOT EXISTS idx_index_daily_date ON tushare.index_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_index_daily_update_time ON tushare.index_daily(update_time);
```

**字段说明**:

| 字段名 | 类型 | 约束 | 说明 |
|-------|-----|------|------|
| `ts_code` | VARCHAR(15) | NOT NULL, PK | Tushare指数代码,如`000300.SH` |
| `trade_date` | DATE | NOT NULL, PK | 交易日期,YYYY-MM-DD格式 |
| `open` | FLOAT | - | 开盘点位 |
| `high` | FLOAT | - | 最高点位 |
| `low` | FLOAT | - | 最低点位 |
| `close` | FLOAT | - | 收盘点位 |
| `pre_close` | FLOAT | - | 昨收盘点位 |
| `change` | FLOAT | - | 涨跌点位 |
| `pct_chg` | FLOAT | - | 涨跌幅(%) |
| `volume` | FLOAT | - | 成交量(手) |
| `amount` | FLOAT | - | 成交额(千元) |
| `update_time` | TIMESTAMP | DEFAULT NOW | 数据更新时间戳 |

**索引策略**:
- **PRIMARY KEY (ts_code, trade_date)**: 唯一约束,防止重复数据
- **idx_index_daily_code**: 按指数代码查询优化
- **idx_index_daily_date**: 按日期范围查询优化
- **idx_index_daily_update_time**: 数据追踪和增量更新优化

#### 2.3.2 数据示例

```
ts_code      | trade_date | open     | high     | low      | close    | volume    | amount
-------------|------------|----------|----------|----------|----------|-----------|--------
000300.SH    | 2025-01-15 | 3450.12  | 3478.56  | 3442.89  | 3465.34  | 123456789 | 98765432
000905.SH    | 2025-01-15 | 5234.67  | 5289.12  | 5220.34  | 5256.78  | 234567890 | 87654321
```

### 2.4 数据流设计

#### 2.4.1 三种更新模式流程

##### 模式1: 智能增量更新 (SMART)

```
[用户] 点击"运行任务"(不指定日期)
   ↓
[FetcherTask._determine_date_range()]
   ├─ 查询DB: SELECT MAX(trade_date) FROM tushare.index_daily WHERE ts_code = ?
   ├─ 若有数据: start_date = max_date + 1 - 3天
   ├─ 若无数据: start_date = 19901219
   └─ end_date = 今天
   ↓
[TushareIndexDailyTask.get_batch_list()]
   └─ 生成批次: [(20250110-20250115), (20250116-20250120), ...]
   ↓
[逐批调用] pro.index_daily(ts_code=?, start_date=?, end_date=?)
   ↓
[数据验证与存储]
   ├─ 验证: close > 0, high >= low, etc.
   ├─ 转换: vol → volume
   └─ INSERT INTO tushare.index_daily ON CONFLICT DO UPDATE
```

##### 模式2: 手动增量更新 (MANUAL)

```
[用户] 在GUI选择日期范围: start_date=20240101, end_date=20241231
   ↓
[FetcherTask._determine_date_range()]
   └─ 直接使用用户提供的start_date和end_date
   ↓
[后续流程同SMART模式]
```

##### 模式3: 全量更新 (FULL)

```
[用户] 点击"全量更新"按钮
   ↓
[FetcherTask._determine_date_range()]
   └─ start_date = 19901219, end_date = 今天
   ↓
[后续流程同SMART模式,但数据量更大,分批次更多]
```

#### 2.4.2 批量处理机制

**批次生成逻辑**:
```python
if ts_code:  # 单指数查询
    batch_size = 240交易日  # 约1年数据
else:  # 全市场查询
    batch_size = 5交易日    # 1周数据,降低单次请求负担
```

**批次示例**:
```
# 单指数(000300.SH) 2024年全年更新
batch_1: {ts_code: "000300.SH", start_date: "20240101", end_date: "20240930"}  # 240交易日
batch_2: {ts_code: "000300.SH", start_date: "20241001", end_date: "20241231"}  # 剩余交易日

# 全市场(所有指数) 某周更新
batch_1: {start_date: "20250113", end_date: "20250117"}  # 5个交易日,所有指数
```

#### 2.4.3 数据转换与验证

**列名映射**:
```python
column_mapping = {"vol": "volume"}  # Tushare返回vol,存储为volume
```

**数据验证规则**:
```python
validations = [
    (lambda df: df["close"] > 0, "收盘价必须为正数"),
    (lambda df: df["open"] > 0, "开盘价必须为正数"),
    (lambda df: df["high"] > 0, "最高价必须为正数"),
    (lambda df: df["low"] > 0, "最低价必须为正数"),
    (lambda df: df["volume"] >= 0, "成交量不能为负数"),
    (lambda df: df["amount"] >= 0, "成交额不能为负数"),
    (lambda df: df["high"] >= df["low"], "最高价不能低于最低价"),
    (lambda df: df["high"] >= df["open"], "最高价不能低于开盘价"),
    (lambda df: df["high"] >= df["close"], "最高价不能低于收盘价"),
    (lambda df: df["low"] <= df["open"], "最低价不能高于开盘价"),
    (lambda df: df["low"] <= df["close"], "最低价不能高于收盘价"),
]
```

**验证模式**: `validation_mode = "report"` (记录验证结果但保留所有数据)

### 2.5 API集成设计

#### 2.5.1 Tushare Pro API调用

**速率控制**:
- 默认: 每分钟120次请求
- 并发: 默认20个并发连接
- 可在`TushareAPI._api_max_requests_per_minute`中为index_daily定制速率

**调用示例**:
```python
# TushareAPI自动处理分页和速率限制
async with TushareAPI(token=TUSHARE_TOKEN) as api:
    df = await api.query(
        api_name="index_daily",
        fields=["ts_code", "trade_date", "open", "high", "low", "close", ...],
        ts_code="000300.SH",
        start_date="20240101",
        end_date="20241231"
    )
```

**错误处理**:
- HTTP 40203 (速率限制): 自动等待65秒后重试
- 连续3次空页: 提前结束分页
- 网络错误: 最多重试3次

#### 2.5.2 数据字段映射

| Tushare字段 | 数据库字段 | 数据类型 | 转换逻辑 |
|------------|-----------|---------|---------|
| ts_code | ts_code | VARCHAR(15) | 直接映射 |
| trade_date | trade_date | DATE | str→date |
| open | open | FLOAT | str→float |
| high | high | FLOAT | str→float |
| low | low | FLOAT | str→float |
| close | close | FLOAT | str→float |
| pre_close | pre_close | FLOAT | str→float |
| change | change | FLOAT | str→float |
| pct_chg | pct_chg | FLOAT | str→float |
| vol | volume | FLOAT | str→float + rename |
| amount | amount | FLOAT | str→float |

### 2.6 GUI集成设计

#### 2.6.1 任务注册

**文件**: `data/collectors/tasks/stock/__init__.py`

```python
from .tushare_index_daily import TushareIndexDailyTask

__all__ = [
    "TushareStockDailyTask",
    "TushareIndexDailyTask",  # 新增
    # ... 其他任务
]
```

**自动注册**: 通过`@task_register()`装饰器,任务自动注册到`UnifiedTaskFactory`

#### 2.6.2 UI显示

**位置**: 数据采集标签页 → 任务列表

**任务信息显示**:
- 任务名称: `tushare_index_daily`
- 描述: `获取A股指数日线行情数据`
- 状态: 待运行 / 运行中 / 已完成 / 失败
- 进度: 0% → 100%

**用户操作**:
1. 勾选"指数日线"任务
2. 选择更新模式: 智能增量 / 手动增量 / 全量更新
3. (手动模式)设置start_date和end_date
4. 点击"运行任务"按钮
5. 查看实时日志和进度条

#### 2.6.3 日志输出示例

```
[INFO] 任务 tushare_index_daily: 开始执行
[INFO] 任务 tushare_index_daily: 使用智能增量模式,检测到数据库最新日期: 2025-01-10
[INFO] 任务 tushare_index_daily: 更新日期范围: 2025-01-08 到 2025-01-16 (含3天回看)
[INFO] 任务 tushare_index_daily: 使用 BatchPlanner 生成批处理列表,范围: 20250108 到 20250116
[INFO] 任务 tushare_index_daily: 成功生成 1 个批次
[INFO] 📡 Tushare API请求: URL=http://api.tushare.pro, Payload={api_name: 'index_daily', ...}
[INFO] API index_daily (参数: {...}) 通过分页共获取 6 条记录。
[INFO] 数据验证: 6 条记录通过验证
[INFO] 数据库插入: 成功插入 6 条新记录,更新 0 条已有记录
[INFO] 任务 tushare_index_daily: 执行完成
```

---

## 3. 实现计划

### 3.1 开发步骤

#### Step 1: 数据库表创建
- [ ] 编写SQL脚本: `scripts/sql/create_index_daily_table.sql`
- [ ] 通过docker exec执行SQL创建表和索引
- [ ] 验证表结构: `\d tushare.index_daily`

#### Step 2: 任务类实现
- [ ] 创建文件: `data/collectors/tasks/stock/tushare_index_daily.py`
- [ ] 实现`TushareIndexDailyTask`类
- [ ] 配置所有必要属性(api_name, fields, validations等)
- [ ] 实现`get_batch_list()`方法

#### Step 3: 任务注册
- [ ] 在`data/collectors/tasks/stock/__init__.py`中导入并导出新任务
- [ ] 验证任务工厂能够发现和加载任务

#### Step 4: 单元测试
- [ ] 测试智能增量更新(空数据库场景)
- [ ] 测试智能增量更新(已有数据场景)
- [ ] 测试手动增量更新
- [ ] 测试全量更新
- [ ] 验证数据验证规则

#### Step 5: GUI集成验证
- [ ] 启动GUI,确认任务列表显示"指数日线"
- [ ] 执行任务,验证日志输出
- [ ] 验证进度条更新
- [ ] 验证数据库记录

#### Step 6: 文档更新
- [ ] 更新README.md或用户手册
- [ ] 补充API文档注释

### 3.2 测试计划

#### 功能测试

| 测试场景 | 预期结果 | 验证方法 |
|---------|---------|---------|
| 空库智能增量 | 从19901219开始导入全量数据 | 查询DB,确认最早日期 |
| 有数据智能增量 | 从最新日期+1-3天开始 | 验证start_date计算 |
| 手动增量(指定范围) | 仅导入指定范围数据 | 查询DB,确认日期范围 |
| 全量更新 | 导入全部历史数据 | 统计总记录数 |
| 单指数导入 | 仅导入指定指数数据 | WHERE ts_code = ? |
| 批量指数导入 | 导入多个指数 | COUNT DISTINCT ts_code |
| 数据验证失败 | 记录warning但不中断 | 查看日志 |
| API速率限制 | 自动等待后重试 | 监控日志中的速率限制警告 |

#### 性能测试

| 测试场景 | 数据量 | 目标时间 |
|---------|-------|---------|
| 单指数10年全量 | ~2400条 | < 2分钟 |
| 单指数1年增量 | ~240条 | < 30秒 |
| 10个指数1周 | ~50条 | < 1分钟 |

#### 稳定性测试

- 网络中断恢复: 模拟网络中断,验证重试机制
- 数据库锁: 并发写入测试
- 异常数据: 测试NaN, NULL, 负数等异常值处理

---

## 4. 风险与对策

### 4.1 技术风险

| 风险 | 影响 | 概率 | 对策 |
|-----|------|------|------|
| Tushare API速率限制 | 导入速度慢 | 中 | 使用批处理,调整batch_size |
| 网络不稳定导致失败 | 数据不完整 | 低 | 实现重试机制,断点续传 |
| 数据库主键冲突 | 重复数据 | 低 | 使用UPSERT(ON CONFLICT UPDATE) |
| 指数代码映射错误 | 数据匹配失败 | 低 | 文档明确说明代码转换规则 |

### 4.2 数据质量风险

| 风险 | 影响 | 对策 |
|-----|------|------|
| Tushare返回脏数据 | 验证失败 | 使用validation_mode="report"记录 |
| 交易日缺失 | 数据不连续 | 通过交易日历验证完整性 |
| 指数调整导致历史数据变化 | 数据不一致 | 定期全量更新校验 |

---

## 5. 附录

### 5.1 主要指数代码对照表

| 指数名称 | Tushare代码 | Qlib代码 | 说明 |
|---------|------------|---------|------|
| 沪深300 | 000300.SH | SH000300 | 主要大盘股指数 |
| 中证500 | 000905.SH | SH000905 | 中盘股指数 |
| 上证综指 | 000001.SH | SH000001 | 上海证券交易所综合指数 |
| 深证成指 | 399001.SZ | SZ399001 | 深圳成分股指数 |
| 创业板指 | 399006.SZ | SZ399006 | 创业板市场指数 |
| 上证50 | 000016.SH | SH000016 | 上海证券市场规模大、流动性好的50只股票 |
| 中证1000 | 000852.SH | SH000852 | 小盘股指数 |

**代码转换规则**:
- Tushare格式: `[6位代码].[交易所]` (如 `000300.SH`)
- Qlib格式: `[交易所][6位代码]` (如 `SH000300`)
- 交易所代码: `SH`(上海), `SZ`(深圳)

### 5.2 参考资料

1. **Tushare Pro官方文档**:
   - 指数日线接口: https://tushare.pro/document/2_doc_id=95

2. **项目内部参考**:
   - 参考实现: `data/collectors/tasks/stock/tushare_stock_daily.py`
   - 基类实现: `data/collectors/sources/tushare/tushare_task.py`
   - 批处理工具: `data/collectors/sources/tushare/batch_utils.py`

3. **数据库文档**:
   - PostgreSQL表结构: 参考`tushare.stock_daily`表
   - 表结构清单: `docs/数据库表结构清单_带注释.md`

---

## 6. 设计评审检查清单

- [x] 需求明确,覆盖三种更新模式
- [x] 架构设计遵循项目现有模式
- [x] 数据库设计合理,主键和索引完备
- [x] API集成考虑速率限制和错误处理
- [x] GUI集成方案清晰
- [x] 测试计划完整
- [x] 风险识别与对策充分
- [x] 文档使用中文,符合项目规范

**设计完成,等待Stage 5评审批准**
