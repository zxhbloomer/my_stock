# 配置管理说明

## 概述

My Stock项目使用**环境变量**和**配置文件**的组合方式管理敏感信息，提供灵活且安全的配置管理。

## 配置优先级

配置加载遵循以下优先级（从高到低）：

```
1. 环境变量（操作系统级别）
2. .env 文件（项目根目录）
3. config.json 文件（用户配置目录）
4. 默认值
```

## 推荐配置方式

### ⭐ 方案A: .env文件（推荐）

**优点**:
- ✅ 简单直观
- ✅ 不会提交到Git
- ✅ 支持本地开发
- ✅ 符合12-Factor App原则

**快速开始**:

```bash
# 1. 运行配置向导
python setup_env.py

# 2. 或手动创建
cp .env.example .env
# 编辑.env文件，填入实际配置

# 3. 验证配置
python -c "from data.common.config_manager import get_tushare_token; print(get_tushare_token())"
```

**.env 文件示例**:
```bash
TUSHARE_TOKEN=your_actual_token_here
DATABASE_URL=postgresql://user:pass@localhost:5432/tusharedb
LOG_LEVEL=INFO
```

### 方案B: 环境变量

**适用场景**:
- 生产环境部署
- Docker容器
- CI/CD流程

**设置方式**:

```bash
# Windows CMD
set TUSHARE_TOKEN=your_token
set DATABASE_URL=postgresql://user:pass@localhost:5432/db

# Windows PowerShell
$env:TUSHARE_TOKEN="your_token"
$env:DATABASE_URL="postgresql://user:pass@localhost:5432/db"

# Linux/Mac
export TUSHARE_TOKEN="your_token"
export DATABASE_URL="postgresql://user:pass@localhost:5432/db"

# Docker
docker run -e TUSHARE_TOKEN="your_token" -e DATABASE_URL="..." myapp

# docker-compose.yml
environment:
  - TUSHARE_TOKEN=${TUSHARE_TOKEN}
  - DATABASE_URL=${DATABASE_URL}
```

### 方案C: config.json文件

**适用场景**:
- 需要复杂配置结构
- 多任务配置管理

**配置文件位置**:
- Windows: `C:/Users/<用户名>/AppData/Local/trademaster/alphahome/config.json`
- Linux: `~/.config/alphahome/config.json`
- macOS: `~/Library/Application Support/alphahome/config.json`

**config.json 格式**:
```json
{
    "api": {
        "tushare_token": "your_token_here"
    },
    "database": {
        "url": "postgresql://user:pass@localhost:5432/db"
    },
    "tasks": {
        "tushare_stock_daily": {
            "batch_size": 100,
            "retry_count": 3
        }
    }
}
```

## 配置项详解

### 核心配置

| 配置项 | 环境变量 | config.json路径 | 必需 | 说明 |
|--------|---------|-----------------|------|------|
| Tushare Token | `TUSHARE_TOKEN` | `api.tushare_token` | ✅ | Tushare Pro API访问令牌 |
| 数据库URL | `DATABASE_URL` | `database.url` | ✅ | PostgreSQL连接字符串 |
| 日志级别 | `LOG_LEVEL` | - | ❌ | 日志输出级别 (DEBUG/INFO/WARNING/ERROR) |

### 数据库URL格式

```
postgresql://用户名:密码@主机:端口/数据库名

# 示例
postgresql://myuser:mypass@localhost:5432/tusharedb
postgresql://admin:admin123@192.168.1.100:5432/stock_data
```

## 在代码中使用配置

### 基础用法

```python
from data.common.config_manager import (
    load_config,
    get_tushare_token,
    get_database_url
)

# 方法1: 获取单个配置
token = get_tushare_token()
db_url = get_database_url()

# 方法2: 获取完整配置
config = load_config()
token = config["api"]["tushare_token"]
db_url = config["database"]["url"]
```

### 在数据采集任务中使用

```python
from data.collectors.tasks.stock import TushareStockDailyTask
from data.common.db_manager import create_async_manager
from data.common.config_manager import get_database_url

# 数据库连接自动从配置加载
db = create_async_manager(get_database_url())

# Token自动从配置注入（通过TaskFactory）
task = TushareStockDailyTask(
    db_connection=db,
    start_date="20200101",
    end_date="20231231"
)

await task.run()
```

### 覆盖默认配置

```python
# 即使配置了.env，仍可手动指定
task = TushareStockDailyTask(
    db_connection=db,
    api_token="override_token",  # 手动指定token
    start_date="20200101",
    end_date="20231231"
)
```

## 配置验证

### 验证脚本

```python
# validate_config.py
from data.common.config_manager import load_config
import sys

def validate():
    config = load_config()

    # 检查必需配置
    required = {
        "Tushare Token": config.get("api", {}).get("tushare_token"),
        "Database URL": config.get("database", {}).get("url"),
    }

    missing = [k for k, v in required.items() if not v]

    if missing:
        print(f"❌ 缺少必需配置: {', '.join(missing)}")
        return False

    print("✅ 配置验证通过")
    return True

if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
```

## 安全最佳实践

### ✅ 应该做的

1. **使用.gitignore**
   ```gitignore
   .env
   .env.local
   .env.*.local
   config.json
   secrets.json
   ```

2. **限制文件权限**
   ```bash
   # Linux/Mac
   chmod 600 .env
   ```

3. **使用不同环境配置**
   ```
   .env.development  # 开发环境
   .env.production   # 生产环境
   .env.test         # 测试环境
   ```

4. **定期更换密钥**
   ```bash
   # 定期更新Token
   # 使用密钥轮换策略
   ```

### ❌ 不应该做的

1. ❌ **硬编码敏感信息**
   ```python
   # 错误示例
   token = "abc123token"  # 不要这样做！
   ```

2. ❌ **提交.env到Git**
   ```bash
   # 确保.env在.gitignore中
   git status  # 检查.env是否被追踪
   ```

3. ❌ **在日志中打印敏感信息**
   ```python
   # 错误示例
   logger.info(f"Using token: {token}")  # 不要这样做！

   # 正确示例
   logger.info(f"Using token: {token[:4]}***")  # 只显示部分
   ```

## 故障排查

### 问题1: 配置未生效

**症状**: 代码仍使用默认值或空值

**检查清单**:
- [ ] .env文件是否在项目根目录
- [ ] 文件名是否正确（`.env`，注意前面的点）
- [ ] 是否安装了`python-dotenv`
- [ ] ConfigManager是否正确初始化

**解决方案**:
```bash
# 检查.env位置
ls -la .env

# 检查依赖
pip list | grep python-dotenv

# 验证加载
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('TUSHARE_TOKEN'))"
```

### 问题2: 数据库连接失败

**症状**: `connection refused` 或 `authentication failed`

**检查清单**:
- [ ] PostgreSQL服务是否运行
- [ ] 数据库URL格式是否正确
- [ ] 用户名密码是否正确
- [ ] 数据库是否存在

**解决方案**:
```bash
# 检查PostgreSQL服务
# Windows
services.msc

# Linux
sudo systemctl status postgresql

# 测试连接
psql -h localhost -U myuser -d tusharedb
```

### 问题3: Tushare API报错

**症状**: `token不存在` 或 `权限不足`

**检查清单**:
- [ ] Token是否正确
- [ ] 账号积分是否足够
- [ ] API权限是否满足

**解决方案**:
```python
# 测试Token
import tushare as ts
from data.common.config_manager import get_tushare_token

token = get_tushare_token()
print(f"Token: {token[:10]}...")  # 显示前10位

pro = ts.pro_api(token)
df = pro.stock_basic(fields='ts_code,name')
print(f"✅ 成功获取 {len(df)} 只股票")
```

## 示例项目结构

```
my_stock/
├── .env                    # 本地配置（不提交）
├── .env.example            # 配置示例（提交）
├── .gitignore              # 包含.env
├── setup_env.py            # 配置向导
├── requirements.txt        # 包含python-dotenv
└── data/
    └── common/
        └── config_manager.py  # 配置管理器
```

## 相关文档

- [环境变量设置指南](ENV_SETUP_GUIDE.md)
- [数据库配置指南](DATABASE_SETUP.md)
- [Tushare API文档](TUSHARE_API_LIST.md)

## 更新日志

- 2025-10-12: 添加.env文件支持和python-dotenv集成
- 2025-10-12: 更新ConfigManager支持多级配置回退
