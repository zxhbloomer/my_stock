# 环境变量配置指南

## 快速开始

### 方法1: 使用配置向导（推荐）

```bash
# 运行配置向导
python setup_env.py

# 按提示输入配置信息
```

### 方法2: 手动创建.env文件

```bash
# 1. 复制示例文件
cp .env.example .env

# 2. 编辑.env文件，填入实际配置
notepad .env  # Windows
# 或
nano .env     # Linux/Mac
```

## 配置项说明

### 必需配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
| `TUSHARE_TOKEN` | Tushare Pro API Token | `your_token_here` |
| `DATABASE_URL` | PostgreSQL连接字符串 | `postgresql://user:pass@localhost:5432/db` |

### 可选配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `CACHE_DIR` | 数据缓存目录 | `~/.my_stock/cache` |

## 获取Tushare Token

1. 访问 [Tushare Pro官网](https://tushare.pro/register)
2. 注册账号
3. 在个人中心获取Token
4. 完成积分任务提升权限（可选）

## 数据库配置

### PostgreSQL安装（使用Docker，推荐）

```bash
# 1. 创建docker-compose.yml
cat > docker-compose.yml << EOF
version: '3.8'
services:
  postgres:
    image: postgres:14
    container_name: my_stock_db
    environment:
      POSTGRES_USER: mystock
      POSTGRES_PASSWORD: mystock123
      POSTGRES_DB: tusharedb
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
EOF

# 2. 启动数据库
docker-compose up -d

# 3. 验证连接
docker exec -it my_stock_db psql -U mystock -d tusharedb
```

### 手动安装PostgreSQL

**Windows**:
1. 下载 [PostgreSQL安装包](https://www.postgresql.org/download/windows/)
2. 运行安装程序
3. 记录安装时设置的密码

**Linux (Ubuntu/Debian)**:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

**macOS**:
```bash
brew install postgresql
brew services start postgresql
```

## 验证配置

### 方法1: 使用验证脚本

```bash
# 验证配置是否正确
python -c "from data.common.config_manager import load_config; print(load_config())"
```

### 方法2: 测试数据库连接

```python
from data.common.db_manager import create_async_manager
import asyncio

async def test_connection():
    db = create_async_manager("DATABASE_URL from .env")
    await db.connect()
    print("✅ 数据库连接成功")
    await db.close()

asyncio.run(test_connection())
```

### 方法3: 测试Tushare API

```python
import tushare as ts
from data.common.config_manager import get_tushare_token

token = get_tushare_token()
pro = ts.pro_api(token)

# 测试接口
df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
print(f"✅ Tushare API连接成功，获取到 {len(df)} 只股票")
```

## 使用示例

### 在代码中使用配置

```python
from data.common.config_manager import (
    get_tushare_token,
    get_database_url,
    load_config
)

# 获取Tushare Token
token = get_tushare_token()

# 获取数据库URL
db_url = get_database_url()

# 获取完整配置
config = load_config()
```

### 在数据采集任务中使用

```python
from data.collectors.tasks.stock import TushareStockDailyTask
from data.common.db_manager import create_async_manager
from data.common.config_manager import get_database_url

# 自动从.env加载配置
db = create_async_manager(get_database_url())

# 创建任务（token会自动从配置加载）
task = TushareStockDailyTask(
    db_connection=db,
    start_date="20200101",
    end_date="20231231"
)

# 运行任务
await task.run()
```

## 安全注意事项

### ✅ 应该做的

- ✅ 将`.env`文件添加到`.gitignore`
- ✅ 使用环境变量管理敏感信息
- ✅ 定期更换Token和密码
- ✅ 为不同环境使用不同的配置（开发/生产）
- ✅ 限制`.env`文件的读取权限

### ❌ 不应该做的

- ❌ 将`.env`文件提交到Git
- ❌ 在代码中硬编码Token和密码
- ❌ 在日志中打印敏感信息
- ❌ 与他人共享`.env`文件

## 多环境配置

### 开发环境

```bash
# .env.development
TUSHARE_TOKEN=dev_token
DATABASE_URL=postgresql://localhost:5432/tusharedb_dev
LOG_LEVEL=DEBUG
```

### 生产环境

```bash
# .env.production
TUSHARE_TOKEN=prod_token
DATABASE_URL=postgresql://prod-server:5432/tusharedb
LOG_LEVEL=INFO
```

### 加载特定环境配置

```python
from dotenv import load_dotenv
import os

# 根据环境变量选择配置文件
env = os.getenv('ENVIRONMENT', 'development')
load_dotenv(f'.env.{env}')
```

## 常见问题

### Q1: .env文件不生效？

**检查项**:
1. 文件名是否为`.env`（注意前面的点）
2. 文件是否在项目根目录
3. 是否已安装`python-dotenv`
4. 代码中是否调用了`load_dotenv()`

### Q2: 数据库连接失败？

**检查项**:
1. PostgreSQL服务是否启动
2. 数据库URL格式是否正确
3. 用户名密码是否正确
4. 数据库是否存在
5. 防火墙是否阻止连接

### Q3: Tushare API报错？

**检查项**:
1. Token是否正确
2. 账号是否有足够的积分/权限
3. API接口是否需要更高权限
4. 是否超过调用频率限制

## 技术支持

- Tushare官方文档: https://tushare.pro/document/2
- PostgreSQL官方文档: https://www.postgresql.org/docs/
- python-dotenv文档: https://github.com/theskumar/python-dotenv

## 更新日志

- 2025-10-12: 初始版本，添加.env配置支持
