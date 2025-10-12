# My Stock - 基于 Qlib 的A股量化投资项目

基于 Microsoft Qlib 框架的中国A股量化投资研究项目，集成了完整的数据采集、处理和回测功能。

## 项目特点

- ✅ **完整的数据流水线**: 从数据采集到处理的完整工具链
- ✅ **Tushare数据源集成**: 支持A股市场数据采集
- ✅ **灵活的任务系统**: 基于装饰器的任务注册和工厂模式
- ✅ **异步数据库操作**: PostgreSQL异步/同步双模式支持
- ✅ **批处理规划**: 智能批次切分和并发处理
- ✅ **因子处理框架**: 内置多种技术指标和数据处理操作

## 项目结构

```
my_stock/
├── data/                        # 数据采集和处理模块（从alphaHome迁移）
│   ├── collectors/              # 数据采集器
│   │   ├── base/               # 采集器基础类
│   │   │   └── fetcher_task.py # 通用数据获取任务基类
│   │   ├── sources/            # 数据源实现
│   │   │   └── tushare/        # Tushare数据源
│   │   │       ├── tushare_api.py          # Tushare API封装
│   │   │       ├── tushare_task.py         # Tushare任务基类
│   │   │       ├── batch_utils.py          # 批处理工具
│   │   │       └── tushare_data_transformer.py  # 数据转换器
│   │   └── tasks/              # 具体采集任务
│   │       └── stock/          # 股票数据任务
│   │           ├── tushare_stock_basic.py      # 股票基本信息
│   │           ├── tushare_stock_daily.py      # 日线行情
│   │           ├── tushare_stock_adjfactor.py  # 复权因子
│   │           └── ...                         # 其他股票数据任务
│   ├── processors/              # 数据处理器
│   │   ├── base/               # 处理器基础类
│   │   │   ├── processor_task.py    # 处理器任务基类
│   │   │   └── block_processor.py   # 块处理器Mixin
│   │   ├── operations/         # 数据操作
│   │   │   ├── base_operation.py         # 操作基类
│   │   │   ├── missing_data.py           # 缺失值处理
│   │   │   └── technical_indicators.py   # 技术指标计算
│   │   ├── tasks/              # 具体处理任务
│   │   │   └── stock/          # 股票数据处理
│   │   │       ├── stock_adjusted_price.py  # 复权价格计算
│   │   │       └── stock_adjdaily.py        # 复权日线处理
│   │   └── utils/              # 处理工具
│   │       ├── query_builder.py    # SQL查询构建器
│   │       └── data_validator.py   # 数据验证器
│   ├── common/                  # 共通模块
│   │   ├── db_components/      # 数据库组件
│   │   │   ├── db_manager_core.py           # 核心连接管理
│   │   │   ├── database_operations_mixin.py # 数据库操作Mixin
│   │   │   ├── schema_management_mixin.py   # 表结构管理Mixin
│   │   │   ├── table_name_resolver.py       # 表名解析器
│   │   │   └── utility_mixin.py             # 工具函数Mixin
│   │   ├── task_system/        # 任务系统
│   │   │   ├── base_task.py         # 任务基类
│   │   │   ├── task_decorator.py    # 任务装饰器
│   │   │   └── task_factory.py      # 任务工厂
│   │   ├── planning/           # 批处理规划
│   │   │   └── batch_planner.py     # 批次规划器
│   │   ├── config_manager.py   # 配置管理器
│   │   ├── constants.py        # 常量定义
│   │   ├── db_manager.py       # 数据库管理器（统一接口）
│   │   └── logging_utils.py    # 日志工具
│   └── loaders/                # 数据加载器（Qlib DataHandler）
├── configs/                     # YAML 配置文件
│   ├── workflow_config_lightgbm_Alpha158.yaml     # CSI300策略
│   └── workflow_config_lightgbm_Alpha158_csi500.yaml  # CSI500策略
├── handlers/                    # 自定义Qlib DataHandler
├── factors/                     # 自定义因子库
├── utils/                       # 工具模块
│   └── chinese_charts.py       # 中文图表工具
├── scripts/                     # 辅助脚本
│   ├── setup_env.bat           # 环境设置
│   └── download_data.bat       # 数据下载
├── examples/                    # 示例代码
│   ├── data_collection_example.py   # 数据采集示例
│   └── custom_handler_example.py    # 自定义Handler示例
├── notebooks/                   # Jupyter Notebook 分析
│   └── 01_workflow_by_code.ipynb
├── docs/                        # 文档
│   ├── Qlib中国A股完整工作流程指南.md
│   ├── TUSHARE_API_LIST.md     # Tushare API列表
│   └── TUSHARE_TABLES_LIST.md  # Tushare数据表列表
├── tests/                       # 测试文件
├── mlruns/                      # MLflow 实验记录（自动生成）
├── run_workflow.py              # 主工作流执行脚本
├── view_results.py              # 结果分析脚本
├── view_charts.py               # 中文图表展示
├── test_imports.py              # 导入测试脚本
├── environment.yml              # Conda环境配置
├── requirements.txt             # Python依赖
└── CLAUDE.md                    # Claude Code项目说明

```

## 快速开始

### 环境要求

- Python 3.8
- PostgreSQL (可选，用于数据采集)
- Conda/Miniconda

### 第一步：创建 Conda 环境

```bash
# 创建环境
conda env create -f environment.yml

# 激活环境
conda activate mystock
```

### 第二步：安装依赖

```bash
# 安装所有依赖
pip install -r requirements.txt
```

### 第三步：下载 Qlib 数据

```bash
# 下载中国A股数据
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

### 第四步：运行工作流

```bash
# 使用Python脚本运行
python run_workflow.py

# 或使用配置文件运行
python run_workflow.py configs/workflow_config_lightgbm_Alpha158_csi500.yaml
```

### 第五步：查看结果

```bash
# 查看回测结果
python view_results.py

# 查看中文标注图表
python view_charts.py

# 或启动MLflow UI
mlflow ui
# 访问 http://localhost:5000
```

## 核心功能

### 1. 数据采集系统

基于Tushare Pro的异步数据采集框架：

```python
from data.collectors.tasks.stock import TushareStockDailyTask
from data.common.db_manager import create_async_manager

# 创建数据库管理器
db = create_async_manager("postgresql://user:pass@localhost/dbname")

# 创建任务并执行
task = TushareStockDailyTask(
    db_connection=db,
    start_date="20200101",
    end_date="20231231"
)
await task.run()
```

### 2. 数据处理系统

灵活的数据处理管道：

```python
from data.processors.operations import OperationPipeline, FillNAOperation, MovingAverageOperation

# 构建处理管道
pipeline = OperationPipeline([
    FillNAOperation(method="ffill"),
    MovingAverageOperation(window=5, columns=["close"])
])

# 应用到数据
processed_df = pipeline.apply(df)
```

### 3. Qlib工作流

完整的量化投资工作流：

```python
import qlib
from qlib.constant import REG_CN

# 初始化Qlib
qlib.init(provider_uri='~/.qlib/qlib_data/cn_data', region=REG_CN)

# 使用配置文件运行完整工作流
# 详见 run_workflow.py
```

## 配置说明

### 策略配置文件

位于 `configs/` 目录：

- **workflow_config_lightgbm_Alpha158.yaml**: CSI300股票池，LightGBM模型
- **workflow_config_lightgbm_Alpha158_csi500.yaml**: CSI500股票池，LightGBM模型

配置包含：
- 数据处理器配置（时间周期、股票池）
- 模型配置（LightGBM参数）
- 回测配置（初始资金、交易费用）
- 记录器配置（SignalRecord、PortAnaRecord）

### 数据库配置

数据采集系统支持PostgreSQL：

```python
# 异步模式（用于数据采集）
from data.common.db_manager import create_async_manager
db = create_async_manager("postgresql://user:pass@localhost:5432/dbname")

# 同步模式（用于Backtrader等）
from data.common.db_manager import create_sync_manager
db = create_sync_manager("postgresql://user:pass@localhost:5432/dbname")
```

## 测试

```bash
# 运行导入测试
python test_imports.py

# 测试结果应显示所有8个模块通过
✅ 所有导入测试通过！
```

## 技术栈

- **量化框架**: Microsoft Qlib
- **机器学习**: LightGBM, scikit-learn
- **数据源**: Tushare Pro API
- **数据库**: PostgreSQL (asyncpg + psycopg2-binary)
- **异步框架**: asyncio, aiohttp
- **实验追踪**: MLflow
- **数据处理**: pandas, numpy

## 依赖说明

核心依赖：
- `pyqlib` - Qlib量化框架
- `asyncpg` - PostgreSQL异步驱动
- `psycopg2-binary` - PostgreSQL同步驱动
- `aiohttp` - 异步HTTP客户端
- `tushare` - Tushare数据源
- `appdirs` - 配置管理
- `aiolimiter` - 异步速率限制

详见 `requirements.txt`

## 参考资料

- [Qlib 官方文档](https://qlib.readthedocs.io/)
- [Qlib GitHub](https://github.com/microsoft/qlib)
- [Tushare Pro](https://tushare.pro/)
- [完整工作流程指南](./docs/Qlib中国A股完整工作流程指南.md)

## 项目文档

- **CLAUDE.md** - Claude Code工作说明
- **MODULE_GUIDE.md** - 模块使用指南
- **MIGRATION_CHECKLIST.md** - 迁移检查清单
- **FIX_COMPLETION_REPORT.md** - 修复完成报告
- **QA_REVIEW_REPORT.md** - QA审查报告

## License

本项目基于 Qlib 框架开发，遵循相应开源协议。
