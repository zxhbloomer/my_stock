# Tushare Pro - moneyflow 接口文档

## 接口说明

**接口名称**: `moneyflow` (个股资金流向)

**功能描述**: 获取沪深A股票资金流向数据，显示单子大小分类的买卖金额

**数据来源**: Tushare Pro

**数据开始时间**: 2010年至今

**数据更新频率**: 每日收盘后更新

---

## 接口参数

### 必填参数（二选一）

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `ts_code` | str | 股票代码（单只股票查询） | `'000001.SZ'` |
| `trade_date` | str | 交易日期（某天所有股票查询） | `'20190315'` |

**注意**: `ts_code` 和 `trade_date` 必须至少提供一个参数

### 可选参数

| 参数名 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `start_date` | str | 开始日期 | `'20190101'` |
| `end_date` | str | 结束日期 | `'20191231'` |

---

## 返回字段

| 字段名 | 类型 | 说明 | 单位 |
|--------|------|------|------|
| `ts_code` | str | 股票代码 | - |
| `trade_date` | str | 交易日期 | YYYYMMDD |
| `buy_elg_amount` | float | 特大单买入金额 | 万元 |
| `sell_elg_amount` | float | 特大单卖出金额 | 万元 |
| `buy_lg_amount` | float | 大单买入金额 | 万元 |
| `sell_lg_amount` | float | 大单卖出金额 | 万元 |
| `buy_md_amount` | float | 中单买入金额 | 万元 |
| `sell_md_amount` | float | 中单卖出金额 | 万元 |
| `buy_sm_amount` | float | 小单买入金额 | 万元 |
| `sell_sm_amount` | float | 小单卖出金额 | 万元 |
| `net_mf_amount` | float | 净流入金额 | 万元 |

---

## 单子大小定义

Tushare按成交金额将订单分为4个级别：

| 单子类型 | 成交金额范围 |
|---------|-------------|
| **小单** | < 5万元 |
| **中单** | 5万元 ≤ 金额 < 20万元 |
| **大单** | 20万元 ≤ 金额 < 100万元 |
| **特大单** | ≥ 100万元 |

---

## 使用示例

### 示例1: 查询某一天所有股票的资金流向

```python
import tushare as ts

pro = ts.pro_api('你的token')

# 查询2019年3月15日所有股票的资金流向
df = pro.moneyflow(trade_date='20190315')
print(df.head())
```

### 示例2: 查询某只股票一段时间的资金流向

```python
import tushare as ts

pro = ts.pro_api('你的token')

# 查询股票002149从2019年1月15日到3月15日的资金流向
df = pro.moneyflow(
    ts_code='002149.SZ',
    start_date='20190115',
    end_date='20190315'
)
print(df.head())
```

### 示例3: 返回数据示例

```python
{
    "ts_code": "000779.SZ",           # 股票代码
    "trade_date": "20190315",         # 交易日期
    "buy_elg_amount": 500.75,         # 特大单买入(万元)
    "sell_elg_amount": 400.50,        # 特大单卖出(万元)
    "buy_lg_amount": 1500.50,         # 大单买入(万元)
    "sell_lg_amount": 1300.25,        # 大单卖出(万元)
    "buy_md_amount": 1316.72,         # 中单买入(万元)
    "sell_md_amount": 1498.90,        # 中单卖出(万元)
    "buy_sm_amount": 1150.17,         # 小单买入(万元)
    "sell_sm_amount": 1122.97,        # 小单卖出(万元)
    "net_mf_amount": 50.25            # 净流入(万元)
}
```

---

## 批处理策略

### 单股票查询模式（推荐）

```python
# 按股票代码分批，每批240个交易日（约1年）
for ts_code in stock_list:
    df = pro.moneyflow(
        ts_code=ts_code,
        start_date='20190101',
        end_date='20191231'
    )
```

**优点**:
- 数据量可控，不易超时
- 便于并发处理
- 适合按股票增量更新

### 全市场查询模式

```python
# 按交易日期查询
df = pro.moneyflow(trade_date='20190315')
```

**说明**:
- 单次返回该日所有股票的数据

---

## 本项目实现方案

### 数据库表设计

**表名**: `moneyflow`

**主键**: `["ts_code", "trade_date"]`

**字段定义**: 参见上方"返回字段"章节

### 批处理配置

参考 `tushare_stock_daily.py` 实现：

- **单股票查询**: 每批240个交易日（约1年）
- **智能增量**: 回看3天
- **全量更新**: 从2010年1月1日开始

### 更新模式

1. **智能增量** (smart_update):
   - 查询数据库最新日期
   - 从最新日期减3天开始更新

2. **手动增量** (manual_update):
   - 用户指定 `start_date` 和 `end_date`

3. **全量更新** (full_update):
   - 从 `default_start_date = "20100101"` 开始更新

---

## 注意事项

1. **API速率限制**:
   - 遵循Tushare Pro的速率限制规则
   - 本项目采用单股票查询模式，每批240个交易日

2. **数据完整性**:
   - 停牌日期可能没有数据
   - 新股上市前几天可能数据不全

3. **金额单位**:
   - 所有金额字段单位为**万元**
   - 存入数据库前无需单位转换

4. **数据说明**:
   - `net_mf_amount` 为Tushare API直接返回的净流入金额字段
   - 正值表示净流入，负值表示净流出

---

## 相关文档

- [Tushare Pro官方文档](https://tushare.pro/document/2?doc_id=170)
- [本项目数据库表结构清单](./数据库表结构清单_带注释.md)
- [TushareTask基类说明](../data/collectors/sources/tushare/tushare_task.py)
