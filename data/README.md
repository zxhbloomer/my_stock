# Data Module 设计文档

## 📋 整体架构设计

本模块整合了现有的简单采集器模式和alphaHome的任务系统架构，提供统一的数据获取和处理能力。

## 🏗️ 推荐目录结构

```
data/
├── __init__.py                          # 模块入口，统一导出
│
├── common/                              # 通用组件（从alphaHome学习）
│   ├── __init__.py
│   ├── task_system.py                   # 统一任务系统：BaseTask, TaskFactory, @task_register
│   ├── logging_utils.py                 # 日志工具
│   └── db_manager.py                    # 数据库管理器（异步AsyncIO）
│
├── collectors/                          # 数据采集器模块（外部API → 本地存储）
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── fetcher_task.py             # 抽象采集任务基类（3种更新模式：MANUAL/SMART/FULL）
│   │   └── collector.py                # 兼容旧版base_collector.py的简化版
│   │
│   ├── sources/                         # 数据源实现
│   │   ├── __init__.py
│   │   ├── tushare/                    # Tushare数据源
│   │   │   ├── __init__.py
│   │   │   ├── tushare_task.py         # Tushare任务基类（集成API客户端和转换器）
│   │   │   ├── tushare_api.py          # Tushare API客户端（含速率限制、分页、并发控制）
│   │   │   ├── tushare_collector.py    # 兼容旧版的Run类（保持向后兼容）
│   │   │   └── data_transformer.py     # 数据转换器（列映射、日期转换、自定义变换）
│   │   │
│   │   └── qlib/                       # Qlib官方数据源（未来扩展）
│   │       ├── __init__.py
│   │       └── qlib_collector.py
│   │
│   └── tasks/                          # 具体采集任务（按资产类别组织）
│       ├── __init__.py
│       ├── stock/                      # 股票数据采集
│       │   ├── __init__.py
│       │   ├── daily_bar.py           # 日线行情采集任务
│       │   ├── adj_factor.py          # 复权因子采集任务
│       │   ├── index_weight.py        # 指数成分和权重
│       │   └── basic_info.py          # 股票基本信息
│       │
│       ├── fund/                       # 基金数据采集
│       ├── index/                      # 指数数据采集
│       └── macro/                      # 宏观数据采集
│
├── processors/                         # 数据处理器模块（数据库 → 特征工程 → 数据库）
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── processor_task.py          # 处理任务基类（单表/多表查询，依赖检查）
│   │   ├── block_processor.py         # 分块处理Mixin（大数据集分块处理）
│   │   └── normalizer.py              # 兼容旧版的DataNormalizer类
│   │
│   ├── operations/                     # 数据处理操作（可组合的操作单元）
│   │   ├── __init__.py
│   │   ├── base_operation.py          # 操作基类和操作流水线
│   │   ├── missing_data.py            # 缺失值处理（FillNAOperation, DropNAOperation）
│   │   ├── technical_indicators.py    # 技术指标计算（MA, RSI, MACD等）
│   │   └── data_cleaning.py           # 数据清洗操作
│   │
│   ├── utils/                          # 处理工具
│   │   ├── __init__.py
│   │   ├── query_builder.py           # SQL查询构建器（参数化、防注入）
│   │   ├── data_validator.py          # 数据验证器（类型、范围、异常值检测）
│   │   └── validator.py               # 兼容旧版的简化验证器
│   │
│   └── tasks/                          # 具体处理任务
│       ├── __init__.py
│       ├── stock/
│       │   ├── __init__.py
│       │   ├── adjusted_price.py      # 后复权价格计算
│       │   ├── adjdaily_processor.py  # 日线复权+交易日补全
│       │   ├── technical_features.py  # 技术特征计算
│       │   └── fundamental_features.py # 基本面特征计算
│       │
│       └── portfolio/                  # 组合数据处理
│
└── loaders/                            # 数据加载器（未来预留，用于Qlib Handler集成）
    ├── __init__.py
    └── qlib_loader.py
```

---

## 🔄 设计原则

### 1. **渐进式迁移（Progressive Migration）**
- 保留现有的简单接口（`base_collector.py`, `tushare_collector.py`, `normalizer.py`, `validator.py`）
- 新增高级任务系统（`fetcher_task.py`, `processor_task.py`）
- 两套系统共存，逐步迁移旧代码到新架构

### 2. **职责分离（Separation of Concerns）**
```
collectors/   → 外部数据源 → 原始数据存储（CSV/数据库）
processors/   → 数据库 → 特征工程 → 模型训练数据
loaders/      → 数据 → Qlib Handler → 模型
```

### 3. **统一任务系统（Unified Task System）**
```python
# 所有任务使用统一的装饰器注册
@task_register()
class MyTask(FetcherTask):  # 或 ProcessorTask
    name = "my_task"
    # ...
```

### 4. **AsyncIO优先（Async-First）**
- 所有新任务使用 `async/await`
- 并发控制：`asyncio.Semaphore`
- 速率限制：滑动窗口算法

### 5. **可组合操作（Composable Operations）**
```python
# 操作流水线示例
pipeline = OperationPipeline("日线处理")
pipeline.add_operation(FillNAOperation(method='mean'))
pipeline.add_operation(MovingAverageOperation(window=5))
pipeline.add_operation(RSIOperation(window=14))
result = await pipeline.apply(data)
```

---

## 📦 核心组件说明

### A. 统一任务系统（common/task_system.py）

#### BaseTask（抽象基类）
```python
class BaseTask(ABC):
    """所有任务的基类"""
    task_type: str              # "fetch" 或 "processor"
    name: str                   # 任务名称（唯一标识）
    description: str            # 任务描述
    dependencies: List[str]     # 依赖的其他任务

    @abstractmethod
    async def execute(self, **kwargs):
        """执行任务的核心逻辑"""
        pass
```

#### UnifiedTaskFactory（任务工厂）
```python
class UnifiedTaskFactory:
    """统一任务工厂，管理所有注册的任务"""
    _tasks: Dict[str, Type[BaseTask]] = {}

    @classmethod
    def register(cls, task_class):
        """注册任务类"""
        cls._tasks[task_class.name] = task_class

    @classmethod
    def get_task(cls, name: str) -> BaseTask:
        """根据名称获取任务实例"""
        return cls._tasks[name]()
```

#### @task_register装饰器
```python
def task_register():
    """任务注册装饰器"""
    def wrapper(task_class):
        UnifiedTaskFactory.register(task_class)
        return task_class
    return wrapper
```

---

### B. 数据采集器（collectors/）

#### FetcherTask（抽象基类）
```python
class FetcherTask(BaseTask, ABC):
    """数据采集任务基类"""

    # 三种更新模式
    UPDATE_TYPE = Enum("UpdateType", ["MANUAL", "SMART", "FULL"])

    # 核心配置
    default_concurrent_limit = 5       # 并发限制
    default_max_retries = 3            # 重试次数
    default_retry_delay = 2            # 重试延迟（秒）
    smart_lookback_days = 10           # SMART模式回溯天数

    @abstractmethod
    def get_batch_list(self, **kwargs) -> List[Dict]:
        """生成批次列表（子类实现）"""
        pass

    @abstractmethod
    async def fetch_batch(self, batch_params: Dict, stop_event=None):
        """获取单个批次数据（子类实现）"""
        pass

    async def _execute_batches(self, batches: List[Any], stop_event=None):
        """并发执行所有批次（带重试逻辑）"""
        semaphore = asyncio.Semaphore(self.concurrent_limit)
        # ... 并发执行 + 进度条 + 重试
```

#### TushareTask（Tushare专用基类）
```python
class TushareTask(FetcherTask):
    """Tushare数据源任务"""
    data_source = "tushare"
    default_page_size = 5000           # 分页大小
    default_rate_limit_delay = 65      # 速率限制间隔

    def __init__(self, token: str, **kwargs):
        self.api = TushareAPI(token)
        self.data_transformer = TushareDataTransformer()

    async def fetch_batch(self, params: Dict, stop_event=None):
        """调用Tushare API并转换数据"""
        data = await self.api.query(
            api_name=self.api_name,
            fields=self.fields,
            stop_event=stop_event,
            **params
        )
        return self.data_transformer.process_data(data)
```

#### TushareAPI（API客户端）
```python
class TushareAPI:
    """Tushare HTTP API客户端"""

    # 每分钟最大请求数（按API分类）
    _api_max_requests_per_minute: Dict[str, int] = {
        "daily": 800,
        "index_weight": 500,
        # ...
    }

    # 并发限制（按API分类）
    _api_concurrency_limits: Dict[str, int] = {
        "daily": 80,
        "index_weight": 50,
        # ...
    }

    async def query(self, api_name: str, fields: List[str], **params):
        """执行API查询（含速率限制和分页）"""
        await self._wait_for_rate_limit_slot(api_name)
        # ... 分页处理 + HTTP请求
```

---

### C. 数据处理器（processors/）

#### ProcessorTask（抽象基类）
```python
class ProcessorTask(BaseTask, BlockProcessorMixin):
    """数据处理任务基类"""

    source_tables: List[str] = []      # 源数据表
    dependencies: List[str] = []       # 依赖的其他任务
    batch_size = 1000                  # 批处理大小

    async def fetch_data(self, stop_event=None, **kwargs):
        """从数据库获取数据（单表或多表）"""
        if len(self.source_tables) == 1:
            return await self._fetch_single_table(**kwargs)
        else:
            return await self._fetch_multiple_tables(**kwargs)

    @abstractmethod
    def _calculate_from_single_source(self, data: pd.DataFrame, **kwargs):
        """单表数据计算逻辑（子类实现）"""
        pass
```

#### BlockProcessorMixin（分块处理）
```python
class BlockProcessorMixin(ABC):
    """大数据集分块处理Mixin"""
    is_block_processor: bool = False

    @abstractmethod
    def get_data_blocks(self, **kwargs) -> Iterator[Dict[str, Any]]:
        """将任务分解成可独立处理的数据块"""
        pass

    @abstractmethod
    def process_block(self, block_params: Dict[str, Any]) -> Optional[pd.DataFrame]:
        """处理单个数据块"""
        pass

    def run_all_blocks(self, **kwargs) -> None:
        """驱动所有数据块处理"""
        for block_params in self.get_data_blocks(**kwargs):
            self.process_block(block_params)
```

#### OperationPipeline（操作流水线）
```python
class OperationPipeline:
    """可组合的数据处理操作流水线"""

    def __init__(self, name: str = "Pipeline"):
        self.operations = []

    def add_operation(self, operation: Operation, condition=None):
        """添加操作到流水线（支持条件执行）"""
        self.operations.append((operation, condition))
        return self

    async def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        """按顺序应用所有操作"""
        result = data.copy()
        for operation, condition in self.operations:
            if condition is None or condition(result):
                result = await operation.apply(result)
        return result
```

---

## 🔌 使用示例

### 1. 数据采集任务（简单模式 - 向后兼容）
```python
from data.collectors.sources.tushare import Run

# 使用旧版简化接口
runner = Run(token="your_token")

# 下载数据
runner.download(
    source_dir="~/.qlib/stock_data/source/tushare",
    start_date="20200101",
    end_date="20231231"
)

# 标准化数据
runner.normalize(
    source_dir="~/.qlib/stock_data/source/tushare",
    normalize_dir="~/.qlib/stock_data/normalized/tushare"
)
```

### 2. 数据采集任务（高级模式 - 新任务系统）
```python
from data.collectors.tasks.stock import StockDailyBarTask
from data.common.task_system import UnifiedTaskFactory

# 方式1：直接实例化
task = StockDailyBarTask(token="your_token")
await task.execute(
    start_date="20230101",
    end_date="20231231",
    symbols=["000001.SZ", "000002.SZ"],
    update_type="SMART"  # 智能增量更新
)

# 方式2：通过工厂获取
task = UnifiedTaskFactory.get_task("stock_daily_bar")
await task.execute(...)
```

### 3. 数据处理任务（操作流水线）
```python
from data.processors.operations import (
    FillNAOperation,
    MovingAverageOperation,
    RSIOperation
)
from data.processors.operations.base_operation import OperationPipeline

# 创建操作流水线
pipeline = OperationPipeline("股票日线处理")

# 添加操作
pipeline.add_operation(
    FillNAOperation(method='mean', columns=['close', 'volume'])
).add_operation(
    MovingAverageOperation(window=5, column='close', group_by=['ts_code'])
).add_operation(
    RSIOperation(window=14, column='close', group_by=['ts_code'])
)

# 应用流水线
import pandas as pd
data = pd.read_csv("stock_data.csv")
processed_data = await pipeline.apply(data)
```

### 4. 数据处理任务（完整任务）
```python
from data.processors.tasks.stock import StockAdjustedPriceTask

# 实例化任务
task = StockAdjustedPriceTask(db_connection=db)

# 执行任务（自动处理多表联合查询、计算、验证、保存）
result = await task.execute(
    start_date="20230101",
    end_date="20231231",
    ts_code="000001.SZ"
)
```

### 5. 分块处理任务（大数据集）
```python
from data.processors.tasks.stock import StockAdjdailyProcessorTask

# 初始化分块处理任务
task = StockAdjdailyProcessorTask(
    db_connection=db,
    config={
        "block_size_codes": 20,  # 每次处理20只股票
        "calendar_exchange": "SSE"
    }
)

# 执行任务（自动分块、并行处理、进度跟踪）
await task.execute(
    codes=all_stock_codes,  # 数千只股票
    start_date="20200101",
    end_date="20231231"
)
```

---

## 🔀 迁移路径

### 阶段1：共存阶段（当前）
- ✅ 保留旧版接口：`base_collector.py`, `tushare_collector.py`, `normalizer.py`, `validator.py`
- ✅ 新增任务系统：`fetcher_task.py`, `processor_task.py`, `task_system.py`
- ✅ 两套系统独立运行，不相互依赖

### 阶段2：部分迁移
- 🔄 新功能使用新任务系统
- 🔄 旧代码逐步重构为任务
- 🔄 关键业务逻辑优先迁移

### 阶段3：完全迁移
- ⏳ 所有采集和处理逻辑使用任务系统
- ⏳ 旧版接口标记为 `@deprecated`
- ⏳ 提供自动化迁移工具

---

## ✨ 新架构的优势

### 1. **并发性能**
- AsyncIO并发：单进程处理大量I/O密集任务
- 智能速率限制：避免API限流
- 批量处理：减少网络往返

### 2. **可靠性**
- 自动重试机制：网络抖动自动恢复
- 断点续传：支持SMART增量更新
- 错误隔离：单个批次失败不影响整体

### 3. **可扩展性**
- 统一注册系统：新任务只需添加装饰器
- 任务依赖管理：自动检查前置任务
- 可组合操作：灵活构建数据处理流水线

### 4. **可维护性**
- 清晰的职责分离：采集器 vs 处理器
- 统一的代码风格：所有任务继承自基类
- 完整的日志系统：详细的执行追踪

### 5. **向后兼容**
- 旧代码继续运行：无需立即迁移
- 渐进式升级：按需迁移关键路径
- 统一接口：新旧系统可互操作

---

## 🎯 下一步行动

1. **创建目录结构**：按照上述设计创建所有文件夹
2. **实现通用组件**：`task_system.py`, `logging_utils.py`, `db_manager.py`
3. **迁移第一个任务**：将 `tushare_collector.py` 重构为 `TushareTask`
4. **编写使用文档**：详细的API文档和使用示例
5. **单元测试**：为所有核心组件编写测试

---

## 📚 参考资料

- **alphaHome项目**：`D:\2025_project\99_quantify\99_github\tushare项目\alphaHome\`
- **Qlib官方文档**：https://qlib.readthedocs.io/
- **Tushare文档**：`doc/Tushare数据获取完整教程.md`
