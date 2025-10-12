# 文件复制与迁移清单

## 📋 概述

本文档列出从alphaHome项目复制到my_stock项目的所有文件及其目标位置。

**源路径基准**: `D:\2025_project\99_quantify\99_github\tushare项目\alphaHome\alphahome\`
**目标路径基准**: `D:\2025_project\99_quantify\python\my_stock\data\`

---

## 🔹 阶段一：通用组件（common/）

### 1.1 任务系统核心

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `common/task_system/base_task.py` | `data/common/task_system.py` | ✅ 需要整合到一个文件中 |
| `common/task_system/task_factory.py` | `data/common/task_system.py` | ✅ 合并到同一文件 |
| `common/task_system/task_register.py` | `data/common/task_system.py` | ✅ 合并装饰器 |
| `common/task_system/__init__.py` | `data/common/__init__.py` | ✅ 导出接口 |

### 1.2 日志系统

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `common/logging_utils.py` | `data/common/logging_utils.py` | ⚠️ 需要适配项目日志配置 |

### 1.3 数据库管理

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `common/db_manager.py` | `data/common/db_manager.py` | ⚠️ 需要根据项目数据库配置修改 |

---

## 🔹 阶段二：数据采集器（collectors/）

### 2.1 采集器基类

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `fetchers/base/fetcher_task.py` | `data/collectors/base/fetcher_task.py` | ✅ 直接复制，少量路径调整 |

### 2.2 Tushare数据源

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `fetchers/sources/tushare/tushare_task.py` | `data/collectors/sources/tushare/tushare_task.py` | ✅ 直接复制 |
| `fetchers/sources/tushare/tushare_api.py` | `data/collectors/sources/tushare/tushare_api.py` | ⚠️ 需要添加token配置 |
| `fetchers/sources/tushare/data_transformer.py` | `data/collectors/sources/tushare/data_transformer.py` | ✅ 直接复制 |

**注意**：现有的 `data/collectors/tushare_collector.py` 保留不动，作为简化接口。

### 2.3 采集任务示例（参考）

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `fetchers/tasks/stock/daily_bar.py`（如存在） | `data/collectors/tasks/stock/daily_bar.py` | 🔧 需要参照创建 |
| `fetchers/tasks/stock/adj_factor.py`（如存在） | `data/collectors/tasks/stock/adj_factor.py` | 🔧 需要参照创建 |

**说明**：alphaHome的具体任务实现可能不完整，需要根据其模式自行创建。

---

## 🔹 阶段三：数据处理器（processors/）

### 3.1 处理器基类

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `processors/processor_task.py` | `data/processors/base/processor_task.py` | ✅ 直接复制，调整导入路径 |
| `processors/base/block_processor.py` | `data/processors/base/block_processor.py` | ✅ 直接复制 |

### 3.2 处理操作（operations/）

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `processors/operations/base_operation.py` | `data/processors/operations/base_operation.py` | ✅ 直接复制 |
| `processors/operations/missing_data.py` | `data/processors/operations/missing_data.py` | ✅ 直接复制 |
| `processors/operations/technical_indicators.py` | `data/processors/operations/technical_indicators.py` | ✅ 直接复制 |

**注意**：现有的 `data/processors/normalizer.py` 和 `data/processors/validator.py` 保留不动。

### 3.3 处理工具（utils/）

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `processors/utils/query_builder.py` | `data/processors/utils/query_builder.py` | ⚠️ 需要适配项目数据库类型 |
| `processors/utils/data_validator.py` | `data/processors/utils/data_validator.py` | ✅ 直接复制 |

### 3.4 处理任务示例

| 源文件 | 目标位置 | 修改要求 |
|--------|---------|---------|
| `processors/tasks/stock_adjdaily_processor.py` | `data/processors/tasks/stock/adjdaily_processor.py` | ⚠️ 需要修改表名和字段 |
| `processors/tasks/stock_adjusted_price.py` | `data/processors/tasks/stock/adjusted_price.py` | ⚠️ 需要修改表名和字段 |

---

## 🔹 阶段四：配置和初始化文件

### 4.1 __init__.py 文件创建清单

| 目标位置 | 内容要求 |
|---------|---------|
| `data/common/__init__.py` | 导出：`BaseTask`, `UnifiedTaskFactory`, `task_register`, `get_logger`, `DBManager` |
| `data/collectors/__init__.py` | 导出：`FetcherTask`, `TushareTask` |
| `data/collectors/base/__init__.py` | 导出：`FetcherTask` |
| `data/collectors/sources/__init__.py` | 空文件或导出各数据源 |
| `data/collectors/sources/tushare/__init__.py` | 导出：`TushareTask`, `TushareAPI`, `TushareDataTransformer` |
| `data/collectors/tasks/__init__.py` | 空文件 |
| `data/collectors/tasks/stock/__init__.py` | 导出各股票采集任务 |
| `data/processors/__init__.py` | 导出：`ProcessorTask`, `BlockProcessorMixin` |
| `data/processors/base/__init__.py` | 导出：`ProcessorTask`, `BlockProcessorMixin` |
| `data/processors/operations/__init__.py` | 导出所有操作类 |
| `data/processors/utils/__init__.py` | 导出：`QueryBuilder`, `DataValidator` |
| `data/processors/tasks/__init__.py` | 空文件 |
| `data/processors/tasks/stock/__init__.py` | 导出各股票处理任务 |

---

## 📝 详细复制命令脚本

### Windows PowerShell 脚本

```powershell
# 文件复制脚本
# 运行前请确认所有路径正确

$SOURCE_BASE = "D:\2025_project\99_quantify\99_github\tushare项目\alphaHome\alphahome"
$TARGET_BASE = "D:\2025_project\99_quantify\python\my_stock\data"

# 创建目录结构
$directories = @(
    "common",
    "collectors\base",
    "collectors\sources\tushare",
    "collectors\tasks\stock",
    "collectors\tasks\fund",
    "collectors\tasks\index",
    "collectors\tasks\macro",
    "processors\base",
    "processors\operations",
    "processors\utils",
    "processors\tasks\stock",
    "processors\tasks\portfolio",
    "loaders"
)

foreach ($dir in $directories) {
    $fullPath = Join-Path $TARGET_BASE $dir
    if (-not (Test-Path $fullPath)) {
        New-Item -ItemType Directory -Path $fullPath -Force
        Write-Host "✓ 创建目录: $fullPath"
    }
}

# 阶段一：通用组件
Write-Host "`n=== 阶段一：复制通用组件 ===" -ForegroundColor Cyan

# 注意：task_system需要手动整合多个文件
# Copy-Item "$SOURCE_BASE\common\task_system\*.py" "$TARGET_BASE\common\" -Force
Write-Host "⚠️  task_system需要手动整合：base_task.py + task_factory.py + task_register.py → task_system.py"

Copy-Item "$SOURCE_BASE\common\logging_utils.py" "$TARGET_BASE\common\" -Force
Write-Host "✓ 复制: logging_utils.py"

if (Test-Path "$SOURCE_BASE\common\db_manager.py") {
    Copy-Item "$SOURCE_BASE\common\db_manager.py" "$TARGET_BASE\common\" -Force
    Write-Host "✓ 复制: db_manager.py"
}

# 阶段二：采集器
Write-Host "`n=== 阶段二：复制采集器 ===" -ForegroundColor Cyan

Copy-Item "$SOURCE_BASE\fetchers\base\fetcher_task.py" "$TARGET_BASE\collectors\base\" -Force
Write-Host "✓ 复制: fetcher_task.py"

Copy-Item "$SOURCE_BASE\fetchers\sources\tushare\tushare_task.py" "$TARGET_BASE\collectors\sources\tushare\" -Force
Write-Host "✓ 复制: tushare_task.py"

Copy-Item "$SOURCE_BASE\fetchers\sources\tushare\tushare_api.py" "$TARGET_BASE\collectors\sources\tushare\" -Force
Write-Host "✓ 复制: tushare_api.py"

if (Test-Path "$SOURCE_BASE\fetchers\sources\tushare\data_transformer.py") {
    Copy-Item "$SOURCE_BASE\fetchers\sources\tushare\data_transformer.py" "$TARGET_BASE\collectors\sources\tushare\" -Force
    Write-Host "✓ 复制: data_transformer.py"
}

# 阶段三：处理器
Write-Host "`n=== 阶段三：复制处理器 ===" -ForegroundColor Cyan

Copy-Item "$SOURCE_BASE\processors\processor_task.py" "$TARGET_BASE\processors\base\" -Force
Write-Host "✓ 复制: processor_task.py"

Copy-Item "$SOURCE_BASE\processors\base\block_processor.py" "$TARGET_BASE\processors\base\" -Force
Write-Host "✓ 复制: block_processor.py"

Copy-Item "$SOURCE_BASE\processors\operations\base_operation.py" "$TARGET_BASE\processors\operations\" -Force
Write-Host "✓ 复制: base_operation.py"

Copy-Item "$SOURCE_BASE\processors\operations\missing_data.py" "$TARGET_BASE\processors\operations\" -Force
Write-Host "✓ 复制: missing_data.py"

Copy-Item "$SOURCE_BASE\processors\operations\technical_indicators.py" "$TARGET_BASE\processors\operations\" -Force
Write-Host "✓ 复制: technical_indicators.py"

Copy-Item "$SOURCE_BASE\processors\utils\query_builder.py" "$TARGET_BASE\processors\utils\" -Force
Write-Host "✓ 复制: query_builder.py"

Copy-Item "$SOURCE_BASE\processors\utils\data_validator.py" "$TARGET_BASE\processors\utils\" -Force
Write-Host "✓ 复制: data_validator.py"

Copy-Item "$SOURCE_BASE\processors\tasks\stock_adjdaily_processor.py" "$TARGET_BASE\processors\tasks\stock\adjdaily_processor.py" -Force
Write-Host "✓ 复制: adjdaily_processor.py"

Copy-Item "$SOURCE_BASE\processors\tasks\stock_adjusted_price.py" "$TARGET_BASE\processors\tasks\stock\adjusted_price.py" -Force
Write-Host "✓ 复制: adjusted_price.py"

Write-Host "`n=== 复制完成 ===" -ForegroundColor Green
Write-Host "接下来需要手动完成："
Write-Host "1. 整合task_system相关文件"
Write-Host "2. 创建所有__init__.py文件"
Write-Host "3. 调整导入路径"
Write-Host "4. 修改数据库配置相关代码"
Write-Host "5. 运行测试验证"
```

---

## 🔧 修改要求详细说明

### 必须修改的文件

#### 1. `data/common/task_system.py`（需要整合）
**操作**: 将以下文件整合到一个文件中：
- `common/task_system/base_task.py`
- `common/task_system/task_factory.py`
- `common/task_system/task_register.py`

**修改内容**:
```python
# 整合后的结构
from abc import ABC, abstractmethod
from typing import Dict, Type, List

# BaseTask类（来自base_task.py）
class BaseTask(ABC):
    # ...

# UnifiedTaskFactory类（来自task_factory.py）
class UnifiedTaskFactory:
    # ...

# task_register装饰器（来自task_register.py）
def task_register():
    # ...

# get_task辅助函数
def get_task(name: str):
    return UnifiedTaskFactory.get_task(name)
```

#### 2. `data/collectors/sources/tushare/tushare_api.py`
**修改项**:
- 添加从环境变量或配置文件读取token
- 调整速率限制参数以适应项目需求
- 修改日志输出格式

#### 3. `data/processors/utils/query_builder.py`
**修改项**:
- 根据项目数据库类型（MySQL/PostgreSQL/ClickHouse）调整SQL语法
- 修改参数占位符格式（`$param` vs `%s` vs `?`）

#### 4. `data/processors/tasks/stock/*.py`
**修改项**:
- 修改表名以匹配项目数据库schema
- 调整字段名
- 修改日期格式（`YYYYMMDD` vs `YYYY-MM-DD`）

### 导入路径调整规则

**原路径** → **新路径**:
- `from ..common.task_system` → `from data.common.task_system`
- `from ...common.logging_utils` → `from data.common.logging_utils`
- `from ..fetchers.base` → `from data.collectors.base`
- `from ..processors.base` → `from data.processors.base`

---

## ✅ 验证清单

复制完成后，依次验证以下内容：

### 1. 目录结构验证
```bash
# 运行此命令检查目录结构
tree data/ /F
```

**预期输出**: 所有目录和文件都已创建

### 2. 导入测试
```python
# 测试基础导入
from data.common.task_system import BaseTask, UnifiedTaskFactory, task_register
from data.common.logging_utils import get_logger
from data.collectors.base.fetcher_task import FetcherTask
from data.collectors.sources.tushare import TushareTask, TushareAPI
from data.processors.base.processor_task import ProcessorTask
from data.processors.operations import FillNAOperation, MovingAverageOperation

print("✓ 所有导入成功")
```

### 3. 任务注册测试
```python
from data.common.task_system import UnifiedTaskFactory

# 检查已注册的任务
registered_tasks = UnifiedTaskFactory._tasks
print(f"已注册任务数量: {len(registered_tasks)}")
print(f"任务列表: {list(registered_tasks.keys())}")
```

### 4. 功能测试
```python
# 测试采集器
from data.collectors.sources.tushare import TushareAPI

api = TushareAPI(token="your_token")
# ... 测试API调用

# 测试处理器
from data.processors.operations import FillNAOperation
import pandas as pd

data = pd.DataFrame({'a': [1, None, 3], 'b': [4, 5, None]})
op = FillNAOperation(method='mean')
result = await op.apply(data)
print(result)
```

---

## 📊 进度跟踪表

| 阶段 | 任务 | 状态 | 备注 |
|------|------|------|------|
| 阶段一 | 创建目录结构 | ⬜ 待开始 | 使用PowerShell脚本 |
| 阶段一 | 复制通用组件 | ⬜ 待开始 | 需要整合task_system |
| 阶段二 | 复制采集器基类 | ⬜ 待开始 | |
| 阶段二 | 复制Tushare数据源 | ⬜ 待开始 | 需要配置token |
| 阶段三 | 复制处理器基类 | ⬜ 待开始 | |
| 阶段三 | 复制处理操作 | ⬜ 待开始 | |
| 阶段三 | 复制处理工具 | ⬜ 待开始 | 需要调整SQL |
| 阶段三 | 复制处理任务 | ⬜ 待开始 | 需要修改表名 |
| 阶段四 | 创建__init__.py | ⬜ 待开始 | 所有子模块 |
| 阶段四 | 调整导入路径 | ⬜ 待开始 | 所有复制的文件 |
| 验证 | 导入测试 | ⬜ 待开始 | |
| 验证 | 功能测试 | ⬜ 待开始 | |
| 验证 | 集成测试 | ⬜ 待开始 | |

---

## 🎯 下一步操作建议

1. **立即执行**: 运行PowerShell复制脚本
2. **手动整合**: 整合`task_system`相关文件
3. **创建初始化**: 编写所有`__init__.py`文件
4. **路径调整**: 批量修改导入路径
5. **配置适配**: 修改数据库和API配置
6. **测试验证**: 运行验证清单中的所有测试

---

## 📚 参考文档

- **设计文档**: `data/README.md`
- **alphaHome源码**: `D:\2025_project\99_quantify\99_github\tushare项目\alphaHome\`
- **Qlib文档**: https://qlib.readthedocs.io/
