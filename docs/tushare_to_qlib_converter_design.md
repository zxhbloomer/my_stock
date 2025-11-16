# Tushare转Qlib数据转换工具 - 开发文档

**创建日期**: 2025-11-14
**开发环境**: mystock conda环境
**Python版本**: 3.8

---

## 1. 需求概述

### 1.1 核心功能
将PostgreSQL数据库中的Tushare格式股票数据转换为Qlib标准二进制格式（.bin文件）

### 1.2 关键特性
- ✅ 智能增量更新：自动检测上次转换时间，只转换新增数据
- ✅ 全量转换：首次运行或强制重建模式
- ✅ 元数据跟踪：记录转换历史和状态
- ✅ 进度显示：实时显示转换进度
- ✅ 日志记录：完整的操作日志

---

## 2. 数据源规格

### 2.1 PostgreSQL配置
```yaml
Host: 127.0.0.1
Port: 5432
Database: my_stock
Schema: tushare
User: root
Password: 123456
```

### 2.2 核心表结构

#### stock_basic（股票基本信息）
- **主键**: ts_code
- **关键字段**:
  - ts_code: TS股票代码（如 000001.SZ）
  - list_status: 上市状态（L=上市, D=退市, P=暂停）
  - list_date: 上市日期
  - delist_date: 退市日期

#### stock_daily（日线行情）
- **主键**: ts_code, trade_date
- **数据量**: 17,082,406条记录（全库）
- **股票数**: 5,764只（全库）
- **时间跨度**: 1990-12-19 至 2025-11-14（全库）
- **⭐ 转换范围**: **2008-01-01 至最新交易日** （用户指定）
- **关键字段**:
  - ts_code: 股票代码
  - trade_date: 交易日期
  - open, high, low, close: OHLC价格
  - vol: 成交量（手）
  - amount: 成交额（千元）

#### stock_adjfactor（复权因子）
- **主键**: ts_code, trade_date
- **数据量**: 17,873,714条记录
- **关键字段**:
  - ts_code: 股票代码
  - trade_date: 交易日期
  - adj_factor: 复权因子

#### trade_cal（交易日历）
- **主键**: exchange, cal_date
- **关键字段**:
  - cal_date: 日期
  - is_open: 是否交易（0=休市, 1=交易）

---

## 3. 目标格式规格

### 3.1 Qlib数据结构
```
D:\Data\my_stock\
├── .metadata.yaml              # 转换元数据
├── calendars/
│   └── day.txt                # 交易日历（每行一个日期）
├── instruments/
│   └── all.txt                # 股票列表（格式：股票代码 上市日期 退市日期）
└── features/
    ├── SH600000/
    │   ├── open.day.bin
    │   ├── high.day.bin
    │   ├── low.day.bin
    │   ├── close.day.bin
    │   ├── volume.day.bin
    │   ├── amount.day.bin
    │   └── factor.day.bin      # 复权因子
    └── SZ000001/
        └── ...
```

### 3.2 股票代码转换规则

**Tushare → Qlib**:
```python
600000.SH → SH600000  # 上海交易所
000001.SZ → SZ000001  # 深圳交易所
```

**转换函数**:
```python
def convert_ts_code_to_qlib(ts_code):
    """
    转换Tushare股票代码为Qlib格式

    Args:
        ts_code: Tushare格式代码（如 000001.SZ）

    Returns:
        Qlib格式代码（如 SZ000001）
    """
    symbol, exchange = ts_code.split('.')
    return f"{exchange}{symbol}"
```

### 3.3 字段映射关系

| Tushare字段 | Qlib字段 | 说明 |
|------------|---------|------|
| ts_code | instrument | 股票代码（需转换格式） |
| trade_date | date | 交易日期 |
| open | open | 开盘价 |
| high | high | 最高价 |
| low | low | 最低价 |
| close | close | 收盘价 |
| vol | volume | 成交量（手） |
| amount | amount | 成交额（千元） |
| adj_factor | factor | 复权因子 |

---

## 4. 数据过滤规则

### 4.1 退市股票过滤
```sql
-- 只保留上市状态的股票
WHERE list_status = 'L'
```

**统计数据**:
- 上市股票（L）: 5,449只
- 退市股票（D）: 315只
- 暂停上市（P）: 0只

### 4.2 数据时间范围
- **起始日期**: 2008-01-01（用户指定）
- **结束日期**: 最新交易日（动态获取）
- **说明**: 虽然数据库包含1990年以来的历史数据，但为保持与Qlib训练配置一致，只转换2008年以后的数据

### 4.3 数据完整性要求
- ✅ 不过滤交易量为0的记录（可能是停牌）
- ✅ 保留完整历史数据（2008-01-01起）
- ✅ 不进行预复权处理（保留原始价格）

---

## 5. 增量更新机制

### 5.1 元数据文件格式
**文件路径**: `D:\Data\my_stock\.metadata.yaml`

```yaml
version: "1.0"
last_update_date: "2025-11-14"
last_update_time: "2025-11-14 15:30:00"
conversion_mode: "incremental"  # full | incremental
total_stocks: 5449
total_records: 17082406
trading_days: 8517
earliest_date: "1990-12-19"
latest_date: "2025-11-14"
conversion_history:
  - date: "2025-11-14"
    mode: "full"
    duration: "35min 42s"
    records: 17082406
```

### 5.2 增量判断逻辑

```python
def determine_conversion_mode(qlib_dir, force_rebuild=False):
    """
    判断转换模式（全量 vs 增量）

    Args:
        qlib_dir: Qlib数据目录
        force_rebuild: 是否强制重建

    Returns:
        'full' | 'incremental'
    """
    metadata_file = Path(qlib_dir) / ".metadata.yaml"

    if force_rebuild:
        return 'full'

    if not metadata_file.exists():
        return 'full'

    # 读取上次更新日期
    with open(metadata_file, 'r') as f:
        metadata = yaml.safe_load(f)

    last_date = metadata.get('last_update_date')

    # 查询PostgreSQL是否有新数据
    new_data_exists = check_new_data_since(last_date)

    return 'incremental' if new_data_exists else 'skip'
```

### 5.3 增量SQL查询

```sql
-- 查询新增的交易日历
SELECT DISTINCT cal_date
FROM tushare.trade_cal
WHERE is_open = 1
  AND cal_date > :last_update_date
ORDER BY cal_date;

-- 查询新增的日线数据
SELECT d.*
FROM tushare.stock_daily d
INNER JOIN tushare.stock_basic b ON d.ts_code = b.ts_code
WHERE b.list_status = 'L'
  AND d.trade_date >= '2008-01-01'  -- 起始日期限制
  AND d.trade_date > :last_update_date
ORDER BY d.ts_code, d.trade_date;

-- 查询新增的复权因子
SELECT f.*
FROM tushare.stock_adjfactor f
INNER JOIN tushare.stock_basic b ON f.ts_code = b.ts_code
WHERE b.list_status = 'L'
  AND f.trade_date >= '2008-01-01'  -- 起始日期限制
  AND f.trade_date > :last_update_date
ORDER BY f.ts_code, f.trade_date;
```

---

## 6. 技术实现方案

### 6.1 核心技术栈
- **数据库连接**: psycopg2
- **数据处理**: pandas
- **Qlib转换**: 官方DumpDataUpdate类
- **进度显示**: tqdm
- **日志记录**: logging
- **配置管理**: yaml

### 6.2 实现流程

```
1. 读取元数据（判断转换模式）
   ↓
2. 连接PostgreSQL数据库
   ↓
3. 查询上市股票列表（list_status='L'）
   ↓
4. 根据模式查询数据
   ├─ 全量模式：查询所有数据
   └─ 增量模式：查询 trade_date > last_update_date
   ↓
5. 数据转换
   ├─ 股票代码格式转换（Tushare → Qlib）
   ├─ 字段映射（vol → volume）
   └─ 导出为Parquet临时文件
   ↓
6. 调用Qlib DumpDataUpdate
   ├─ 全量模式：DumpDataAll
   └─ 增量模式：DumpDataUpdate
   ↓
7. 更新元数据文件
   ↓
8. 清理临时文件
```

### 6.3 关键代码片段

#### 数据导出为Parquet
```python
def export_to_parquet(pg_conn, last_date=None, temp_dir="./temp"):
    """
    从PostgreSQL导出数据为Parquet格式
    """
    # 构建查询条件
    date_filter = f"AND d.trade_date > '{last_date}'" if last_date else ""

    # 查询日线数据（从2008-01-01开始）
    query = f"""
    SELECT
        d.ts_code,
        d.trade_date as date,
        d.open,
        d.high,
        d.low,
        d.close,
        d.vol as volume,
        d.amount
    FROM tushare.stock_daily d
    INNER JOIN tushare.stock_basic b ON d.ts_code = b.ts_code
    WHERE b.list_status = 'L'
      AND d.trade_date >= '2008-01-01'  -- 起始日期限制
      {date_filter}
    ORDER BY d.ts_code, d.trade_date
    """

    df = pd.read_sql(query, pg_conn)

    # 转换股票代码格式
    df['symbol'] = df['ts_code'].apply(convert_ts_code_to_qlib)

    # 按股票分组导出
    for symbol, group in df.groupby('symbol'):
        output_file = Path(temp_dir) / f"{symbol}.parquet"
        group.to_parquet(output_file, index=False)
```

#### 调用Qlib转换
```python
from qlib.scripts.dump_bin import DumpDataAll, DumpDataUpdate

def convert_to_qlib_format(temp_dir, qlib_dir, mode='full'):
    """
    转换为Qlib二进制格式
    """
    if mode == 'full':
        converter = DumpDataAll(
            data_path=temp_dir,
            qlib_dir=qlib_dir,
            freq='day',
            max_workers=8,
            date_field_name='date',
            symbol_field_name='symbol',
            file_suffix='.parquet'
        )
    else:
        converter = DumpDataUpdate(
            data_path=temp_dir,
            qlib_dir=qlib_dir,
            freq='day',
            max_workers=8,
            date_field_name='date',
            symbol_field_name='symbol',
            file_suffix='.parquet'
        )

    converter.dump()
```

---

## 7. 命令行接口

### 7.1 使用方式

```bash
# 激活环境
conda activate mystock

# 自动模式（智能判断全量/增量）
python scripts/00_tushare_to_qlib.py --mode auto

# 强制全量转换
python scripts/00_tushare_to_qlib.py --mode full

# 增量更新
python scripts/00_tushare_to_qlib.py --mode incremental

# 指定输出路径
python scripts/00_tushare_to_qlib.py --output D:\Data\my_stock

# 显示详细日志
python scripts/00_tushare_to_qlib.py --verbose
```

### 7.2 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| --mode | str | auto | 转换模式：auto/full/incremental |
| --output | str | D:\Data\my_stock | 输出目录 |
| --host | str | 127.0.0.1 | PostgreSQL地址 |
| --port | int | 5432 | PostgreSQL端口 |
| --database | str | my_stock | 数据库名 |
| --user | str | root | 用户名 |
| --password | str | 123456 | 密码 |
| --workers | int | 8 | 并行工作进程数 |
| --verbose | flag | False | 显示详细日志 |

---

## 8. 性能预估

### 8.1 全量转换
- **原始数据量**: 17,082,406条记录（1990-2025）
- **转换数据量**: 约12,000,000条记录（2008-2025，估算）
- **股票数**: 5,449只（上市股票）
- **预计时间**: 25-45分钟
- **输出大小**: ~900MB（二进制压缩）

### 8.2 增量转换
- **日均新增**: ~5,449条（每只股票1条）
- **预计时间**: 1-5分钟
- **输出增量**: ~10MB/天

---

## 9. 测试计划

### 9.1 单元测试
- ✅ 股票代码转换函数
- ✅ 元数据读写
- ✅ 增量判断逻辑
- ✅ 数据过滤规则

### 9.2 集成测试
- ✅ 全量转换流程
- ✅ 增量转换流程
- ✅ 强制重建流程
- ✅ 异常处理

### 9.3 验证方法
```python
import qlib
from qlib.data import D
from qlib.constant import REG_CN

# 初始化Qlib
qlib.init(provider_uri='D:/Data/my_stock', region=REG_CN)

# 验证交易日历
calendar = D.calendar(start_time='2020-01-01', end_time='2020-12-31')
print(f"2020年交易日数量: {len(calendar)}")

# 验证股票列表
instruments = D.instruments('all')
stock_list = D.list_instruments(instruments=instruments, as_list=True)
print(f"上市股票数量: {len(stock_list)}")

# 验证数据完整性
df = D.features(['SH600000'], ['$open', '$close', '$volume'],
                start_time='2020-01-01', end_time='2020-01-10')
print(df.head())
```

---

## 10. 异常处理

### 10.1 常见错误
- **数据库连接失败**: 检查PostgreSQL服务状态
- **权限不足**: 确保有写入D:\Data\目录的权限
- **内存不足**: 减少workers数量或分批处理
- **数据格式错误**: 检查数据库表结构是否完整

### 10.2 日志级别
```python
logging.INFO:  正常流程日志
logging.WARNING: 警告信息（如缺失数据）
logging.ERROR: 错误信息（但继续执行）
logging.CRITICAL: 致命错误（终止执行）
```

---

## 11. 后续扩展

### 11.1 Phase 2功能
- [ ] 支持stock_dailybasic表（基本面指标）
- [ ] 支持分钟级数据
- [ ] 支持港股数据
- [ ] Web界面管理

### 11.2 性能优化
- [ ] 并行处理优化
- [ ] 内存使用优化
- [ ] 断点续传功能

---

**文档版本**: v1.0
**最后更新**: 2025-11-14
