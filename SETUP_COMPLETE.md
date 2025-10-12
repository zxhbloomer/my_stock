# ✅ 环境配置完成

## 配置摘要

### 🔐 已配置的环境变量

**文件位置**: `.env`

```bash
TUSHARE_TOKEN=2fee9f337f8944f40988... (已配置 ✅)
DATABASE_URL=postgresql://root:123456@localhost:5432/test (已配置 ✅)
LOG_LEVEL=INFO
```

### 🗄️ 数据库连接信息

- **类型**: PostgreSQL 17.6
- **容器**: postgresql17 (Docker)
- **地址**: localhost:5432
- **数据库**: test
- **用户名**: root
- **密码**: 123456
- **状态**: ✅ 连接测试通过

### ✅ 测试结果

运行 `test_db_connection.py` 结果：

```
✅ Tushare Token: 配置正确
✅ Database URL: 配置正确
✅ 数据库连接成功
✅ PostgreSQL版本: 17.6
```

## 下一步操作

### 1. 测试数据采集

```python
# test_data_collection.py
import asyncio
from data.collectors.tasks.stock import TushareStockBasicTask
from data.common.db_manager import create_async_manager
from data.common.config_manager import get_database_url

async def test_fetch():
    # 连接数据库
    db = create_async_manager(get_database_url())
    await db.connect()

    # 创建任务：获取股票基本信息
    task = TushareStockBasicTask(
        db_connection=db,
        list_status='L',  # 只获取上市状态的股票
        exchange=''       # 所有交易所
    )

    # 运行任务（会自动创建表）
    print("开始采集股票基本信息...")
    result = await task.run()

    print(f"✅ 采集完成！获取 {len(result)} 只股票")

    await db.close()

# 运行测试
asyncio.run(test_fetch())
```

### 2. 查看已创建的表

```bash
# 连接到数据库
docker exec -it postgresql17 psql -U root -d test

# 查看所有schema
\dn

# 查看tushare schema下的所有表
\dt tushare.*

# 查看表结构
\d tushare.stock_basic

# 查询数据
SELECT COUNT(*) FROM tushare.stock_basic;
SELECT * FROM tushare.stock_basic LIMIT 10;
```

### 3. 常用数据采集任务

#### 股票基本信息
```python
from data.collectors.tasks.stock import TushareStockBasicTask

task = TushareStockBasicTask(
    db_connection=db,
    list_status='L',  # L=上市, D=退市, P=暂停上市
    exchange=''       # SSE=上交所, SZSE=深交所, ''=全部
)
await task.run()
```

#### 日线行情
```python
from data.collectors.tasks.stock import TushareStockDailyTask

task = TushareStockDailyTask(
    db_connection=db,
    start_date="20240101",
    end_date="20241231"
)
await task.run()
```

#### 复权因子
```python
from data.collectors.tasks.stock import TushareStockAdjFactorTask

task = TushareStockAdjFactorTask(
    db_connection=db,
    start_date="20240101",
    end_date="20241231"
)
await task.run()
```

### 4. 批量采集脚本示例

创建 `collect_all_data.py`:

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量采集数据"""
import asyncio
from data.collectors.tasks.stock import (
    TushareStockBasicTask,
    TushareStockDailyTask,
    TushareStockAdjFactorTask
)
from data.common.db_manager import create_async_manager
from data.common.config_manager import get_database_url

async def collect_all():
    """采集所有基础数据"""
    db = create_async_manager(get_database_url())
    await db.connect()

    print("=" * 60)
    print("开始批量数据采集")
    print("=" * 60)

    # 1. 股票基本信息
    print("\n[1/3] 采集股票基本信息...")
    task1 = TushareStockBasicTask(db_connection=db)
    result1 = await task1.run()
    print(f"✅ 完成！获取 {len(result1)} 只股票")

    # 2. 日线行情（最近1年）
    print("\n[2/3] 采集日线行情...")
    task2 = TushareStockDailyTask(
        db_connection=db,
        start_date="20240101",
        end_date="20241231"
    )
    result2 = await task2.run()
    print(f"✅ 完成！获取 {len(result2)} 条数据")

    # 3. 复权因子
    print("\n[3/3] 采集复权因子...")
    task3 = TushareStockAdjFactorTask(
        db_connection=db,
        start_date="20240101",
        end_date="20241231"
    )
    result3 = await task3.run()
    print(f"✅ 完成！获取 {len(result3)} 条数据")

    print("\n" + "=" * 60)
    print("✅ 所有数据采集完成！")
    print("=" * 60)

    await db.close()

if __name__ == "__main__":
    asyncio.run(collect_all())
```

## 配置文件说明

### .env 文件（已创建）
包含敏感信息，不会提交到Git

### .env.example 文件
配置模板，可以提交到Git

### docker-compose.yml
PostgreSQL配置文件：
- 位置: `D:\2025_project\00_docker\postgresql\docker-compose.yml`
- 容器名: postgresql17
- 端口: 5432

## 常用命令

### Docker管理

```bash
# 启动PostgreSQL
cd D:\2025_project\00_docker\postgresql
docker-compose up -d

# 停止PostgreSQL
docker-compose down

# 查看日志
docker-compose logs -f

# 重启PostgreSQL
docker-compose restart
```

### 数据库管理

```bash
# 进入PostgreSQL命令行
docker exec -it postgresql17 psql -U root -d test

# 创建新数据库
docker exec -it postgresql17 psql -U root -c "CREATE DATABASE tusharedb;"

# 备份数据库
docker exec postgresql17 pg_dump -U root test > backup.sql

# 恢复数据库
docker exec -i postgresql17 psql -U root test < backup.sql
```

### 项目测试

```bash
# 测试导入
python test_imports.py

# 测试数据库连接
python test_db_connection.py

# 测试配置加载
python -c "from data.common.config_manager import load_config; print(load_config())"
```

## 故障排查

### 问题1: 数据库连接失败

**检查项**:
```bash
# 1. 检查Docker容器是否运行
docker ps | grep postgresql17

# 2. 检查端口是否开放
netstat -an | findstr 5432

# 3. 测试直接连接
docker exec -it postgresql17 psql -U root -d test
```

### 问题2: Tushare API报错

**检查项**:
- Token是否正确（长度应该是50位）
- 账号积分是否足够（访问 https://tushare.pro/user/token）
- 是否超过API调用频率限制

### 问题3: 表未自动创建

**解决方案**:
```python
# 手动创建表
from data.collectors.tasks.stock import TushareStockBasicTask

task = TushareStockBasicTask(db_connection=db)

# 检查表是否存在
exists = await db.table_exists(task)
print(f"表存在: {exists}")

# 手动创建表
if not exists:
    await db.create_table_from_schema(task)
```

## 项目结构

```
my_stock/
├── .env                        # 环境变量配置（已创建 ✅）
├── .env.example                # 配置模板
├── test_db_connection.py       # 连接测试脚本
├── setup_env.py                # 配置向导
├── data/
│   ├── collectors/             # 数据采集器
│   ├── processors/             # 数据处理器
│   └── common/
│       ├── config_manager.py   # 配置管理（支持.env ✅）
│       └── db_manager.py       # 数据库管理
└── docs/
    ├── CONFIGURATION.md        # 配置文档
    └── ENV_SETUP_GUIDE.md      # 环境设置指南
```

## 支持资源

- **Tushare文档**: https://tushare.pro/document/2
- **PostgreSQL文档**: https://www.postgresql.org/docs/
- **项目配置文档**: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- **环境设置指南**: [docs/ENV_SETUP_GUIDE.md](docs/ENV_SETUP_GUIDE.md)

## 更新日志

- 2025-10-12: 完成环境配置，所有测试通过 ✅
