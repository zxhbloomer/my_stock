# Tushare Moneyflow 任务开发方案

**方案编号**: 2025-11-15-194429
**创建时间**: 2025-11-15 19:44:29
**功能名称**: 股票资金流向数据采集任务
**负责人**: Claude AI

---

## 1. 需求概述

### 1.1 业务需求
实现Tushare `moneyflow` API的数据采集任务，获取A股个股资金流向数据，包括超大单、大单、中单、小单的买入卖出金额及净额。

### 1.2 核心参数
- **表名**: `moneyflow`
- **主键**: `["ts_code", "trade_date"]` (复合主键)
- **起始日期**: `20100101`
- **智能增量回看**: 3天
- **任务名**: `tushare_moneyflow`
- **API名称**: `moneyflow`

### 1.3 数据字段
```python
fields = [
    "ts_code",          # TS股票代码
    "trade_date",       # 交易日期
    "buy_elg_amount",   # 超大单买入金额(万元)
    "sell_elg_amount",  # 超大单卖出金额(万元)
    "buy_lg_amount",    # 大单买入金额(万元)
    "sell_lg_amount",   # 大单卖出金额(万元)
    "buy_md_amount",    # 中单买入金额(万元)
    "sell_md_amount",   # 中单卖出金额(万元)
    "buy_sm_amount",    # 小单买入金额(万元)
    "sell_sm_amount",   # 小单卖出金额(万元)
    "net_mf_amount"     # 净流入金额(万元)
]
```

---

## 2. 调用链路分析

### 2.1 完整调用链
```
GUI界面
  → TaskManager.run_task("tushare_moneyflow", update_type="smart")
    → TushareMoneyFlowTask.__init__() [初始化数据库连接、API客户端]
      → FetcherTask._fetch_data() [主入口，基类实现]
        → FetcherTask._determine_date_range() [确定日期范围]
          ↓ update_type="smart"
          → get_latest_date_for_task() [查询数据库最新日期]
          → 计算: latest_date + 1 - smart_lookback_days
          ← 返回: {"start_date": "20241110", "end_date": "20251115"}

        → TushareMoneyFlowTask.get_batch_list(**kwargs) [子类实现]
          → generate_trade_day_batches() [工具函数]
            → TushareAPI.query("trade_cal") [获取交易日历]
            ← 返回: 批次列表 [{"start_date": "20241110", "end_date": "20241114"}, ...]

        → FetcherTask._execute_batches(batches) [并发执行]
          → TushareMoneyFlowTask.prepare_params(batch) [准备参数]
            ← 返回: {"start_date": "20241110", "end_date": "20241114"}

          → TushareMoneyFlowTask.fetch_batch(params) [子类重写]
            → TushareTask.fetch_batch(params) [基类实现]
              → TushareAPI.query("moneyflow", fields, **params)
                → _fetch_with_pagination() [分页处理]
                → _wait_for_rate_limit_slot() [速率控制]
                ← 返回: DataFrame (原始数据)

              → TushareDataTransformer.process_data(df) [数据转换]
                → 应用 transformations (类型转换)
                → 应用 column_mapping (列名映射)
                → 应用自定义转换
                ← 返回: DataFrame (已转换)

        ← 返回: pd.concat([batch1_df, batch2_df, ...])

      → BaseTask._save_data(combined_df) [保存数据]
        → 创建表 (如不存在)
        → 批量写入/更新 (基于主键)
        ← 完成
```

### 2.2 关键节点说明
1. **智能增量逻辑**: 由 `FetcherTask` 基类统一实现，回看3天确保数据完整性
2. **批次生成**: 使用 `generate_trade_day_batches` 工具函数，按交易日历分批
3. **API调用**: 由 `TushareTask` 基类统一封装，处理分页、速率控制、重试
4. **数据转换**: 由 `TushareDataTransformer` 统一处理，避免重复代码
5. **并发控制**: 由 `FetcherTask` 基类的 `asyncio.Semaphore` 控制并发数

---

## 3. 数据支撑分析

### 3.1 参考实现验证
**参考文件**: `D:\2025_project\99_quantify\python\my_stock\data\collectors\tasks\stock\tushare_stock_daily.py`

**已验证的关键点**:
- ✅ 继承 `TushareTask` 基类
- ✅ 使用 `@task_register()` 装饰器自动注册
- ✅ 复合主键 `["ts_code", "trade_date"]` 模式成熟
- ✅ 智能增量回看逻辑已在基类实现
- ✅ 批次生成工具 `generate_trade_day_batches` 已验证
- ✅ 数据转换流程由 `TushareDataTransformer` 统一处理

### 3.2 Tushare API配置
**已确认配置** (来自 `TushareAPI`):
- `moneyflow` API默认速率限制: 100次/分钟 (未在特定配置中，使用默认值)
- 默认并发限制: 20个请求
- 分页大小: 5000条/页

### 3.3 数据库设计
**表结构定义**:
```sql
CREATE TABLE moneyflow (
    ts_code VARCHAR(15) NOT NULL,
    trade_date DATE NOT NULL,
    buy_elg_amount FLOAT,
    sell_elg_amount FLOAT,
    buy_lg_amount FLOAT,
    sell_lg_amount FLOAT,
    buy_md_amount FLOAT,
    sell_md_amount FLOAT,
    buy_sm_amount FLOAT,
    sell_sm_amount FLOAT,
    net_mf_amount FLOAT,
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ts_code, trade_date)
);
```

**索引设计**:
```python
indexes = [
    {"name": "idx_moneyflow_1", "columns": "ts_code"},
    {"name": "idx_moneyflow_2", "columns": "trade_date"},
    {"name": "idx_moneyflow_3", "columns": "update_time"},
]
```

---

## 4. 方案设计

### 4.1 文件设计
**创建文件**: `D:\2025_project\99_quantify\python\my_stock\data\collectors\tasks\stock\tushare_moneyflow.py`

**设计理由**:
1. 完全复用 `TushareTask` 基类的成熟逻辑
2. 遵循现有命名规范: `tushare_<api_name>.py`
3. 放置在 `tasks/stock/` 目录，与同类任务归类

### 4.2 核心实现

#### 4.2.1 类定义
```python
@task_register()
class TushareMoneyFlowTask(TushareTask):
    """股票资金流向数据任务"""

    # 1.核心属性
    name = "tushare_moneyflow"
    description = "获取A股个股资金流向数据"
    table_name = "moneyflow"
    primary_keys = ["ts_code", "trade_date"]
    date_column = "trade_date"
    default_start_date = "20100101"
    smart_lookback_days = 3

    # 2.自定义索引
    indexes = [
        {"name": "idx_moneyflow_1", "columns": "ts_code"},
        {"name": "idx_moneyflow_2", "columns": "trade_date"},
        {"name": "idx_moneyflow_3", "columns": "update_time"},
    ]

    # 3.Tushare特有属性
    api_name = "moneyflow"
    fields = [...]  # 11个字段

    # 4.数据类型转换
    transformations = {
        "buy_elg_amount": float,
        "sell_elg_amount": float,
        "buy_lg_amount": float,
        "sell_lg_amount": float,
        "buy_md_amount": float,
        "sell_md_amount": float,
        "buy_sm_amount": float,
        "sell_sm_amount": float,
        "net_mf_amount": float,
    }

    # 5.表结构定义
    schema_def = {...}  # 对应数据库表结构

    # 6.数据验证规则
    validations = [...]  # 业务规则验证

    # 7.批次配置
    batch_trade_days_single_code = 240  # 单股票查询：1年
    batch_trade_days_all_codes = 5      # 全市场查询：1周
```

#### 4.2.2 批次生成方法
```python
async def get_batch_list(self, **kwargs) -> List[Dict]:
    """复用 generate_trade_day_batches 工具函数"""
    # 完全参照 tushare_stock_daily 实现
    # 支持单股票和全市场两种模式
    # 根据是否有 ts_code 选择不同批次大小
```

### 4.3 关键设计决策

#### 决策1：不使用列名映射
- **理由**: API返回字段名与目标表字段名一致
- **对比**: `tushare_stock_daily` 需要 `vol` → `volume` 映射

#### 决策2：数据验证规则
```python
validations = [
    # 资金额不能为负数(NULL除外)
    (lambda df: df["buy_elg_amount"].isna() | (df["buy_elg_amount"] >= 0), "超大单买入金额不能为负数"),
    (lambda df: df["sell_elg_amount"].isna() | (df["sell_elg_amount"] >= 0), "超大单卖出金额不能为负数"),
    # ... 其他字段类似
]
```

#### 决策3：批次大小策略
- **单股票查询**: 240个交易日/批 (约1年)
  - 理由: 资金流向数据量适中，1年数据可以一次性处理
- **全市场查询**: 5个交易日/批 (1周)
  - 理由: 全市场数据量大(约5000只股票)，小批次避免API超时

---

## 5. KISS原则7问题回答

### Q1: 这是个真问题还是臆想出来的？
**A**: ✅ **真问题**
- 用户明确提出需要获取 `moneyflow` 数据
- 资金流向是量化分析的重要指标
- 数据库中确实缺少此表

### Q2: 有更简单的方法吗？
**A**: ✅ **当前方法已是最简**
- 完全复用现有成熟的 `TushareTask` 基类
- 只需定义配置属性，无需编写复杂逻辑
- 参考实现 `tushare_stock_daily.py` 已验证可行

### Q3: 会破坏什么吗？
**A**: ✅ **无破坏**
- 新增文件，不修改现有代码
- 使用 `@task_register()` 自动注册，不影响其他任务
- 数据库新增表，不影响现有表

### Q4: 当前项目真的需要这个功能吗？
**A**: ✅ **真正需要**
- 资金流向是股票分析的重要维度
- 用户明确提出需求
- 数据完整性要求必须补充此数据源

### Q5: 这个问题过度设计了吗？有缺少必要信息吗？能否继续评估？
**A**: ✅ **设计合理，信息完整**
- 设计完全基于成熟模式，无过度设计
- 所有必要信息已收集齐全（表名、主键、字段、起始日期）
- 可以自信地继续实施

### Q6: 话题是否模糊，是否会导致幻觉的产生？
**A**: ✅ **话题清晰，无幻觉风险**
- 需求明确：实现 `moneyflow` API数据采集
- 有完整的参考实现可对照
- 所有技术细节已验证

### Q7: 是否已经学习了关于代码实施的注意事项的内容？
**A**: ✅ **已深刻学习并应用**
- **复用现有逻辑**: 完全继承 `TushareTask` 基类
- **遵循命名规范**: 文件名、类名、任务名都遵循现有模式
- **索引命名规则**: `idx_表名_1,2,3`
- **避免重复实现**: 使用 `generate_trade_day_batches` 工具函数
- **数据转换统一**: 由 `TushareDataTransformer` 处理
- **验证规则**: 使用lambda表达式的成熟模式

---

## 6. 风险分析与缓解措施

### 6.1 技术风险

#### 风险1: API速率限制
- **风险等级**: 🟡 中等
- **描述**: Tushare `moneyflow` API可能有更严格的速率限制
- **缓解**:
  - 使用 `TushareAPI` 的速率控制机制
  - 配置合理的并发限制（默认20）
  - 支持自动重试和速率限制等待

#### 风险2: 数据完整性
- **风险等级**: 🟢 低
- **描述**: 智能增量回看3天可能遗漏数据
- **缓解**:
  - 回看3天已经过 `tushare_stock_daily` 验证
  - 支持手动指定日期范围的全量更新
  - 数据库唯一约束防止重复

### 6.2 业务风险

#### 风险1: 历史数据起始日期
- **风险等级**: 🟢 低
- **描述**: Tushare `moneyflow` API的实际数据可能早于/晚于2010年
- **缓解**:
  - 首次运行使用全量更新模式验证
  - API返回空数据时自动跳过
  - 日志记录实际获取的日期范围

### 6.3 性能风险

#### 风险1: 全市场数据量大
- **风险等级**: 🟡 中等
- **描述**: 约5000只股票×每天数据，首次全量更新耗时长
- **缓解**:
  - 使用小批次（5个交易日）分批处理
  - 并发控制避免API超时
  - 进度条显示处理进度
  - 支持中断后续传

---

## 7. 实施计划

### 7.1 实施步骤
1. ✅ **阶段1-3**: 需求确认、问题分解、数据收集 (已完成)
2. 🔄 **阶段4**: 方案设计文档编写 (当前)
3. ⏳ **阶段5**: 方案审批等待 (需用户确认)
4. ⏳ **阶段6**: 代码实施
   - 创建 `tushare_moneyflow.py` 文件
   - 定义任务类及所有配置属性
   - 实现 `get_batch_list` 方法
5. ⏳ **阶段7**: QA代码评审 (自动触发)
6. ⏳ **阶段8**: 完成验收

### 7.2 验收标准
- ✅ 代码符合KISS原则，无过度设计
- ✅ 遵循现有代码规范和命名约定
- ✅ 数据库表成功创建，索引正确
- ✅ 智能增量更新正常工作
- ✅ 数据验证规则生效
- ✅ 无重复代码，完全复用基类逻辑

---

## 8. 总结

### 8.1 设计亮点
1. **零创新，100%复用**: 完全基于成熟模式，无需重复造轮子
2. **配置驱动**: 所有逻辑通过配置属性控制，代码极简
3. **健壮性**: 继承基类的异常处理、重试、速率控制机制
4. **可维护性**: 遵循现有规范，后续维护无障碍

### 8.2 核心价值
- **开发效率**: 预计30分钟完成全部代码（仅需配置属性）
- **质量保证**: 基于验证过的基类，风险极低
- **扩展性**: 未来添加更多Tushare任务可完全复制此模式

---

**方案状态**: ✅ 设计完成，等待审批
**下一步**: 提交用户审批，批准后进入代码实施阶段
