# Minishare 用户接口手册

这是一份面向普通接入方的 Minishare API 手册，适合提供给脚本调用方、服务端集成方、数据分析同学和下游内部工具使用者。本文档只覆盖正常用户会直接调用的接口，不覆盖管理员接口、同步运维接口和工作台内部页面数据接口。

## 1. 这份手册是给谁看的

如果你属于下面任一类用户，这份手册就是给你准备的：

- 需要从脚本或服务端调用 Minishare 的普通接入方
- 已经有账号，希望先登录、再创建 API Key 的用户
- 需要查询 Tushare / AKShare 包装接口的调用方
- 需要用 AI 问答、聊天或分析接口的普通业务方

如果你要做的是后台用户管理、角色授权、限流治理、同步任务运维，那些接口不在本文范围内。

## 2. 服务定位与使用边界

Minishare 可以理解成一个把上游数据能力和应用层鉴权、缓存、权限、调用治理收在一起的内部服务。对普通用户来说，最重要的是三件事：

1. 先有一个账号，并能登录成功。
2. 登录后创建自己的 API Key。
3. 用 `X-API-Key` 调普通接口；需要细粒度 AKShare 下游授权时，再额外签发临时 Bearer Token。

对于普通接入方，最常用的接口大体分成四组：

- Session / API Key：登录、查看当前会话、创建和禁用自己的 API Key
- 通用行情与查询：`/api/v1/me`、`/api/v1/query`、`/api/v1/stock-basic`、`/api/v1/daily`
- AKShare：能力目录、能力详情、直接请求、访问校验、临时 Token、物化内容查询
- AI：问答、聊天、分析、状态检查

## 3. Base URL 与环境前提

本文所有示例默认以本地开发地址为例：

```text
https://minishare.wmlgg.com
```

如果你的服务部署在别的域名或端口，请把示例中的 Base URL 换成你的实际地址。

在真正开始调用前，默认你已经具备下面这些前提：

- 你已经有一个可登录的账号
- 服务端已经正常启动
- 你的账号至少具备普通用户权限
- 如果你要调用 AKShare 或 AI，服务端对应上游能力已经配置好

下面这几个页面和接口可以帮助你判断服务是否已经起来：

- 公开登录页：`GET /login`
- API 根入口：`GET /api`
- 文档页：`GET /docs`

其中 `GET /api` 是公开接口，返回值类似：

```json
{
  "message": "Minishare governance API is running.",
  "docs": "/docs",
  "workspace": "/",
  "public_home": "/login"
}
```

它适合做最基础的连通性检查，但不代表你的账号或权限一定已经可用。

## 4. 认证方式总览

Minishare 对普通用户主要有三种认证方式。

| 方式 | 典型场景 | 是否长期使用 | 说明 |
| --- | --- | --- | --- |
| 浏览器 Session Cookie | 用户先登录，再在同源环境里管理账号、改密码、创建 API Key | 否 | 适合浏览器或同源后端流程，示例里常用 `minishare_jwt=<jwt-session-cookie>` 表示 |
| `X-API-Key` | 脚本、后端服务、定时任务、绝大多数接口调用 | 是 | 普通接入方最常用的方式 |
| `Authorization: Bearer` | AKShare 能力的临时受限授权 | 否 | 只用于 AKShare 访问控制，不是通用登录态替代品 |

你可以把三者理解成下面的关系：

- Session Cookie：先登录，证明“你是谁”
- API Key：登录后创建，适合长期稳定调用
- AKShare Bearer Token：从 API Key 派生出来的短期受限凭证，适合下游临时放权

### 4.1 什么时候用 Session

下面这些接口使用 Session 最自然：

- `POST /api/v1/session/logout`
- `GET /api/v1/session/me`
- `POST /api/v1/session/api-keys`
- `POST /api/v1/session/api-keys/<api_key_id>/disable`
- `POST /api/v1/session/password`
- `GET /api/v1/akshare/<capability_code>/debug`

### 4.2 什么时候用 `X-API-Key`

对普通接入方来说，绝大多数接口都推荐走 `X-API-Key`。例如：

- `GET /api/v1/me`
- `POST /api/v1/query`
- `GET /api/v1/stock-basic`
- `GET /api/v1/daily`
- 几乎所有 AKShare 用户查询接口
- `GET /api/v1/ai/status`
- 绝大多数 AI 调用

请求头示例：

```http
X-API-Key: <your-api-key>
```

### 4.3 什么时候用 Bearer Token

Bearer Token 只在 AKShare 相关场景下有意义，主要用在：

- 你不想把完整 API Key 交给下游
- 你只想把某几个 AK 能力临时放给下游
- 你希望下游只能在 token 生命周期内访问指定能力

请求头示例：

```http
Authorization: Bearer <akshare-access-token>
```

## 5. 五分钟快速接入

如果你第一次接入，推荐按下面的顺序跑通。

### 5.1 第一步：登录，拿到 Session

```bash
curl "https://minishare.wmlgg.com/api/v1/session/login" -X POST \
  -H "Content-Type: application/json" \
  -d '{"account":"<your-account>","password":"<your-password>"}'
```

这一步的目标不是直接拿数据，而是确认：

- 账号密码正确
- 服务端能创建你的登录会话
- 后续你可以用同一个 Session 去创建 API Key

成功返回示例：

```json
{
  "message": "登录成功。",
  "user": {
    "username": "demo",
    "display_name": "Demo User",
    "roles": ["user"],
    "auth_method": "session",
    "requests_per_minute": 60,
    "max_active_request_ips": 1,
    "redis_cache_ttl_seconds": 1800,
    "mysql_cache_ttl_seconds": 86400
  }
}
```

同时响应会写入一个 HttpOnly Session Cookie。本文示例里统一写成：

```text
minishare_jwt=<jwt-session-cookie>
```

实际部署时，Cookie 名称可能由服务配置决定。

### 5.2 第二步：创建 API Key

```bash
curl "https://minishare.wmlgg.com/api/v1/session/api-keys" -X POST \
  -H "Content-Type: application/json" \
  -H "Origin: https://minishare.wmlgg.com" \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>" \
  -d '{"name":"my-service"}'
```

这一步的目标是把一次性浏览器登录，转换成一个适合长期脚本调用的 API Key。

你需要特别注意一件事：**明文 API Key 一般只会在创建时返回一次**。拿到后请立刻存入你自己的安全存储位置。

### 5.3 第三步：用 API Key 验证身份

```bash
curl "https://minishare.wmlgg.com/api/v1/me" \
  -H "X-API-Key: <your-api-key>"
```

只要这一步能通，通常说明：

- API Key 可用
- 账号权限基础链路可用
- 后续普通接口可以继续接入

### 5.4 第四步：试一条最常见的数据接口

```bash
curl "https://minishare.wmlgg.com/api/v1/stock-basic?exchange=SSE&list_status=L&fields=ts_code,symbol,name,area,industry,list_date" \
  -H "X-API-Key: <your-api-key>"
```

或者：

```bash
curl "https://minishare.wmlgg.com/api/v1/daily?ts_code=000001.SZ&trade_date=20260410&fields=ts_code,trade_date,open,high,low,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

### 5.5 第五步：查看 AKShare 能力目录

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/capabilities" \
  -H "X-API-Key: <your-api-key>"
```

如果你已经能走到这一步，说明你的普通接入链路已经基本跑通。后面只需要根据业务需要，继续接通具体的数据能力即可。

## 6. Session 与 API Key 接口

这一章覆盖普通用户最常用的账号与认证接口。

### 6.1 `POST /api/v1/session/login`

- 用途：用账号密码登录，建立浏览器 Session
- 认证方式：无需预先认证
- 请求体：

```json
{
  "account": "<your-account>",
  "password": "<your-password>"
}
```

- 字段说明：
  - `account`：账号名，不能为空
  - `password`：密码，不能为空
- 成功返回：
  - `message`：固定为登录成功提示
  - `user`：当前登录用户摘要
- 常见错误：
  - `401`：账号或密码不正确
  - `422`：缺少字段或字段为空

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/session/login" -X POST \
  -H "Content-Type: application/json" \
  -d '{"account":"demo","password":"DemoPass123"}'
```

### 6.2 `POST /api/v1/session/logout`

- 用途：退出当前 Session
- 认证方式：Session Cookie
- 请求体：无
- 成功返回：

```json
{
  "message": "已退出登录。"
}
```

- 常见错误：
  - `401`：当前没有有效 Session

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/session/logout" -X POST \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>"
```

### 6.3 `GET /api/v1/session/me`

- 用途：查看当前 Session 对应的用户信息
- 认证方式：Session Cookie
- 请求参数：无
- 成功返回：返回当前用户信息，字段结构与登录返回里的 `user` 类似
- 常见错误：
  - `401`：没有有效 Session

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/session/me" \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>"
```

### 6.4 `POST /api/v1/session/api-keys`

- 用途：为当前登录用户创建一个新的 API Key
- 认证方式：Session Cookie
- 请求体：

```json
{
  "name": "my-service"
}
```

- 字段说明：
  - `name`：可选，给 API Key 起一个容易辨认的名字
- 成功返回重点：
  - `message`
  - `api_key`：API Key 摘要信息
  - `plaintext_api_key`：本次创建返回的明文 Key
- 常见错误：
  - `400`：名字不合法或服务端校验失败
  - `401`：没有有效 Session

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/session/api-keys" -X POST \
  -H "Content-Type: application/json" \
  -H "Origin: https://minishare.wmlgg.com" \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>" \
  -d '{"name":"analytics-bot"}'
```

### 6.5 `POST /api/v1/session/api-keys/<api_key_id>/disable`

- 用途：禁用当前登录用户自己名下的某个 API Key
- 认证方式：Session Cookie
- 请求体：无
- 路径参数：
  - `api_key_id`：要禁用的 API Key ID
- 成功返回：返回更新后的 API Key 状态摘要
- 常见错误：
  - `401`：没有有效 Session
  - `404`：Key 不存在，或者不属于当前用户

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/session/api-keys/12/disable" -X POST \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>"
```

### 6.6 `POST /api/v1/session/password`

- 用途：修改当前登录用户自己的密码
- 认证方式：Session Cookie
- 请求体：

```json
{
  "password": "NewPass456"
}
```

- 字段说明：
  - `password`：新密码，长度至少 8 位
- 成功返回：返回更新后的用户摘要
- 常见错误：
  - `400`：密码不符合规则
  - `401`：没有有效 Session

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/session/password" -X POST \
  -H "Content-Type: application/json" \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>" \
  -d '{"password":"NewPass456"}'
```

### 6.7 `GET /api/v1/me`

- 用途：用 API Key 查看当前调用者是谁
- 认证方式：`X-API-Key`
- 请求参数：无
- 典型用途：
  - 校验 API Key 是否可用
  - 查看自己的角色和速率限制
  - 在程序启动时做一次自检
- 成功返回字段：
  - `username`
  - `display_name`
  - `roles`
  - `auth_method`
  - `requests_per_minute`
  - `max_active_request_ips`
  - `redis_cache_ttl_seconds`
  - `mysql_cache_ttl_seconds`
- 常见错误：
  - `401`：API Key 不存在、已失效、已禁用

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/me" \
  -H "X-API-Key: <your-api-key>"
```

## 7. 通用行情与数据查询接口

这部分是普通接入方最常用的数据接口。

### 7.1 什么时候用 `/api/v1/query`，什么时候用快捷路由

优先按下面的思路选：

- 如果你查的是最常用的股票基础信息，用 `GET /api/v1/stock-basic`
- 如果你查的是最常用的日线行情，用 `GET /api/v1/daily`
- 如果你需要更通用的 Tushare 查询入口，用 `POST /api/v1/query`

可以简单理解成：

- 快捷路由：更直观，参数写法更简单
- 通用查询：可扩展性更强，适合统一接各种 `api_name`

当前代码里能明确看到的代表性 `api_name` 包括：

- `stock_basic`
- `daily`
- `income`
- `balancesheet`
- `cashflow`
- `fina_indicator`
- `trade_cal`
- `weekly`
- `monthly`
- `daily_basic`
- `adj_factor`
- `index_daily`
- `fund_daily`
- `index_basic`
- `fund_basic`
- `namechange`
- `concept`
- `concept_detail`
- `rt_tick`
- `realtime_quote`

### 7.2 `POST /api/v1/query`

- 用途：统一查询入口
- 认证方式：`X-API-Key`
- 请求体结构：

```json
{
  "api_name": "trade_cal",
  "params": {
    "exchange": "SSE",
    "start_date": "20260401",
    "end_date": "20260430"
  },
  "fields": ["exchange", "cal_date", "is_open"],
  "use_cache": true,
  "ttl_seconds": 300
}
```

- 字段说明：
  - `api_name`：要调用的查询接口名
  - `params`：传给上游查询的参数对象
  - `fields`：希望返回的字段列表，留空则由上游或服务端决定
  - `use_cache`：是否允许读取缓存，默认 `true`
  - `ttl_seconds`：客户端希望使用的 TTL，是否生效取决于权限和接口策略

- 成功返回常见字段：
  - `api_name`
  - `columns`
  - `rows`
  - `row_count`
  - `cached`
  - `cache_layer`
  - `requested_by`

- 常见错误：
  - `401`：API Key 不可用
  - `403`：当前角色没有对应权限
  - `422`：请求体格式错误或字段不合法

示例：查交易日历

```bash
curl "https://minishare.wmlgg.com/api/v1/query" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "api_name": "trade_cal",
    "params": {
      "exchange": "SSE",
      "start_date": "20260401",
      "end_date": "20260430"
    },
    "fields": ["exchange", "cal_date", "is_open"]
  }'
```

### 7.3 `GET /api/v1/stock-basic`

- 用途：查询股票基础信息
- 认证方式：`X-API-Key`
- 常见查询参数：
  - `exchange`：交易所，例如 `SSE`
  - `list_status`：上市状态，默认 `L`
  - `is_hs`：是否沪深港通
  - `fields`：逗号分隔的字段列表
  - `use_cache`
  - `ttl_seconds`

- 成功返回结构与 `QueryResponse` 类似，重点字段：
  - `columns`
  - `rows`
  - `row_count`
  - `cached`
  - `cache_layer`

- 常见错误：
  - `401`：API Key 不可用
  - `403`：没有 `quote:read_stock_basic` 权限

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/stock-basic?exchange=SSE&list_status=L&fields=ts_code,symbol,name,area,industry,list_date" \
  -H "X-API-Key: <your-api-key>"
```

### 7.4 `GET /api/v1/daily`

- 用途：查询日线行情
- 认证方式：`X-API-Key`
- 常见查询参数：
  - `ts_code`
  - `trade_date`
  - `start_date`
  - `end_date`
  - `fields`
  - `use_cache`
  - `ttl_seconds`

- 参数建议：
  - 单日查询优先用 `trade_date`
  - 区间查询用 `start_date` / `end_date`
  - 日期一般使用 `YYYYMMDD`

- 额外注意：
  - 历史数据可能受当前服务的本地历史下限限制
  - 某些历史数据命中本地事实表或物化层时，`cache_layer` 会体现实际来源

- 常见错误：
  - `401`：API Key 不可用
  - `403`：没有 `quote:read_daily` 权限

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/daily?ts_code=000001.SZ&start_date=20260401&end_date=20260410&fields=ts_code,trade_date,open,high,low,close,vol" \
  -H "X-API-Key: <your-api-key>"
```

## 8. AKShare 用户接口

这一章会把 AKShare 用户侧接口写得更完整一些，包括调用模式、能力目录、完整能力清单、物化数据接口和调试接口。

### 8.1 AKShare 接入有哪两种方式

普通用户调用 AKShare，通常有两种方式。

第一种，直接用 `X-API-Key` 调能力接口：

- 最简单
- 最适合自己的脚本或服务端
- 不需要额外签 token

第二种，先签发临时 Bearer Token，再交给下游：

- 更安全
- 权限范围更窄
- 生命周期更短
- 适合把部分 AK 能力临时给其他系统或组件

### 8.2 AKShare 用户侧接口全景

| 路径 | 方法 | 认证方式 | 用途 |
| --- | --- | --- | --- |
| `/api/v1/akshare/entitlements` | `GET` | `X-API-Key` | 查看当前用户视角下的 AK 可用授权结果 |
| `/api/v1/akshare/capabilities` | `GET` | `X-API-Key` | 查看完整 AK 能力目录 |
| `/api/v1/akshare/capabilities/<capability_code>` | `GET` | `X-API-Key` | 查看某个能力的详细定义 |
| `/api/v1/akshare/materialized/summary` | `GET` | `X-API-Key` | 查看 AK 物化数据汇总状态 |
| `/api/v1/akshare/materialized/content-documents` | `GET` | `X-API-Key` | 查询已物化的内容型文档数据 |
| `/api/v1/akshare/materialized/financial-reports` | `GET` | `X-API-Key` | 查询已物化的财报数据 |
| `/api/v1/akshare/materialized/sync-states` | `GET` | `X-API-Key` | 查询物化同步状态 |
| `/api/v1/akshare/tokens/issue` | `POST` | `X-API-Key` | 批量签发 AK 临时 Bearer Token |
| `/api/v1/akshare/capabilities/<capability_code>/token` | `POST` | `X-API-Key` | 为单个能力签发临时 Bearer Token |
| `/api/v1/akshare/<capability_code>` | `GET` | `X-API-Key` 或 Bearer | 直接请求某个 AK 能力 |
| `/api/v1/akshare/<capability_code>/debug` | `GET` | Session Cookie | 用登录会话调试某个 AK 能力 |
| `/api/v1/akshare/access` | `GET` | `X-API-Key` 或 Bearer | 按能力编码检查当前是否可访问 |
| `/api/v1/akshare/capabilities/<capability_code>/access` | `GET` | `X-API-Key` 或 Bearer | 用能力别名路径做同样的访问校验 |

### 8.3 先理解三个概念

在 AKShare 场景里，经常会混淆这三件事：

- 能力目录：平台知道有哪些 AK 能力
- 当前用户可见授权：你当前账号具备哪些能力、当前时窗是否可用
- 真正发请求：你实际去请求某个能力的数据或包装结果

简单说：

- `capabilities` 更偏“目录”
- `entitlements` / `access` 更偏“当前你能不能用”
- `GET /api/v1/akshare/<capability_code>` 才是真正的能力请求入口

### 8.4 `GET /api/v1/akshare/entitlements`

- 用途：查看当前用户视角下的 AK 授权结果
- 认证方式：`X-API-Key`
- 请求参数：无
- 典型返回内容：
  - `code`
  - `display_name`
  - `permission_code`
  - `available_now`
  - `grant_source`
  - `grant_qps_limit`
  - `grant_daily_limit`
  - `reason`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/entitlements" \
  -H "X-API-Key: <your-api-key>"
```

### 8.5 `GET /api/v1/akshare/capabilities`

- 用途：查看 AK 能力目录总表
- 认证方式：`X-API-Key`
- 请求参数：无
- 典型返回内容：
  - `registered_entitlement_count`
  - `warnings`
  - `modules`
  - `capabilities`
  - `grant_management`
  - `materialized_summary`

它非常适合做三件事：

- 找能力编码
- 看推荐请求字段
- 判断某个能力现在是“已登记可用”还是“仅目录模板”

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/capabilities" \
  -H "X-API-Key: <your-api-key>"
```

### 8.6 `GET /api/v1/akshare/capabilities/<capability_code>`

- 用途：查看单个 AK 能力的完整定义
- 认证方式：`X-API-Key`
- 路径参数：
  - `capability_code`：能力编码，例如 `cn_equity_minute_history`
- 典型返回字段：
  - `code`
  - `display_name`
  - `module_code`
  - `module_name`
  - `permission_code`
  - `access_window`
  - `token_required`
  - `supports_temporary_token`
  - `request_fields`
  - `usage_steps`
  - `wrapper_endpoints`
  - `materialized_stats`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/capabilities/cn_equity_minute_history" \
  -H "X-API-Key: <your-api-key>"
```

### 8.7 `GET /api/v1/akshare/materialized/summary`

- 用途：查看 AK 物化数据整体状态
- 认证方式：`X-API-Key`
- 请求参数：无
- 适合场景：
  - 你想知道当前有哪些 AK 内容已经做了物化落库
  - 你想结合物化数据接口直接检索内容和财报

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/materialized/summary" \
  -H "X-API-Key: <your-api-key>"
```

### 8.8 `GET /api/v1/akshare/materialized/content-documents`

- 用途：查询已物化的内容型文档
- 认证方式：`X-API-Key`
- 常见查询参数：
  - `capability_code`
  - `scope_key`
  - `limit`，默认 `20`，最大 `200`
  - `offset`，默认 `0`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/materialized/content-documents?capability_code=broker_reports&limit=20&offset=0" \
  -H "X-API-Key: <your-api-key>"
```

### 8.9 `GET /api/v1/akshare/materialized/financial-reports`

- 用途：查询已物化的财报数据
- 认证方式：`X-API-Key`
- 常见查询参数：
  - `capability_code`
  - `scope_key`
  - `symbol`
  - `statement_type`
  - `limit`
  - `offset`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/materialized/financial-reports?capability_code=us_financial_reports&symbol=AAPL&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

### 8.10 `GET /api/v1/akshare/materialized/sync-states`

- 用途：查看物化同步状态
- 认证方式：`X-API-Key`
- 常见查询参数：
  - `capability_code`
  - `scope_key`
  - `limit`
  - `offset`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/materialized/sync-states?capability_code=broker_reports&limit=20" \
  -H "X-API-Key: <your-api-key>"
```

### 8.11 `POST /api/v1/akshare/tokens/issue`

- 用途：批量签发 AK 临时 Bearer Token
- 认证方式：`X-API-Key`
- 请求体：

```json
{
  "entitlement_codes": ["cn_equity_minute_history", "broker_reports"],
  "expires_in_seconds": 3600
}
```

- 字段说明：
  - `entitlement_codes`：可选。不传时表示为当前用户所有可签发能力签 token
  - `expires_in_seconds`：可选，最小 60 秒；如果超过系统允许上限，会返回 `422`

- 成功返回字段：
  - `token_type`
  - `access_token`
  - `expires_at`
  - `username`
  - `expires_in_seconds`
  - `granted_entitlement_codes`
  - `granted_permission_codes`

- 常见错误：
  - `403`：请求了当前用户没有授权的能力
  - `422`：过期时间超出系统上限

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/tokens/issue" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "entitlement_codes": ["cn_equity_minute_history", "broker_reports"],
    "expires_in_seconds": 3600
  }'
```

### 8.12 `POST /api/v1/akshare/capabilities/<capability_code>/token`

- 用途：给单个能力签发临时 Token
- 认证方式：`X-API-Key`
- 路径参数：
  - `capability_code`
- 请求体：

```json
{
  "expires_in_seconds": 3600
}
```

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/capabilities/cn_equity_minute_history/token" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{"expires_in_seconds": 3600}'
```

### 8.13 `GET /api/v1/akshare/<capability_code>`

- 用途：直接请求某个 AK 能力
- 认证方式：`X-API-Key` 或 Bearer Token
- 路径参数：
  - `capability_code`
- 查询参数：
  - 按不同能力而不同
  - 可以先去 `GET /api/v1/akshare/capabilities/<capability_code>` 看 `request_fields`

- 返回结构重点：
  - `message`
  - `capability_code`
  - `display_name`
  - `permission_code`
  - `available_now`
  - `request_params`
  - `upstream_api_names`
  - `columns`
  - `rows`
  - `row_count`
  - `cached`
  - `cache_layer`
  - `notes`
  - `upstream_result`

示例：直接用 API Key 调分钟历史

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_equity_minute_history?symbol=600519.SH&start_time=2026-04-10T09:30:00&end_time=2026-04-10T15:00:00&period=1" \
  -H "X-API-Key: <your-api-key>"
```

示例：直接用 Bearer 调访问

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_equity_minute_history?symbol=600519.SH&start_time=2026-04-10T09:30:00&end_time=2026-04-10T15:00:00&period=1" \
  -H "Authorization: Bearer <token>"
```

### 8.14 `GET /api/v1/akshare/<capability_code>/debug`

- 用途：用当前登录 Session 调试某个能力
- 认证方式：Session Cookie
- 适用场景：
  - 你已经在浏览器登录
  - 你想快速看某个能力在当前会话下的请求结果
  - 你不想额外创建或粘贴 API Key

- 额外返回：
  - `debug_mode: "session"`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/cn_equity_minute_history/debug?symbol=600519.SH&start_time=2026-04-10T09:30:00&end_time=2026-04-10T15:00:00&period=1" \
  -H "Cookie: minishare_jwt=<jwt-session-cookie>"
```

### 8.15 `GET /api/v1/akshare/access`

- 用途：按能力编码做访问校验
- 认证方式：`X-API-Key` 或 Bearer Token
- 必填查询参数：
  - `entitlement_code`

- 常见错误：
  - `422`：没有传 `entitlement_code`
  - `403`：当前用户或当前 token 没有这个能力
  - `404`：能力编码不存在

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/access?entitlement_code=cn_equity_minute_history" \
  -H "Authorization: Bearer <token>"
```

### 8.16 `GET /api/v1/akshare/capabilities/<capability_code>/access`

- 用途：用能力别名路径做访问校验
- 认证方式：`X-API-Key` 或 Bearer Token
- 路径参数：
  - `capability_code`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/akshare/capabilities/cn_equity_minute_history/access" \
  -H "Authorization: Bearer <token>"
```

### 8.17 AKShare 全量能力清单

下面这张表把当前项目里定义的 AK 能力都列出来了，适合给最终用户直接查。

| 中文能力名 | 能力编码 | 模块 | 权限码 | 常见请求参数 |
| --- | --- | --- | --- | --- |
| 盘前股本 | `pre_market_capital` | `reference` | `akshare:read_reference` | `symbol`, `trade_date`, `limit` |
| 集合竞价成交 | `call_auction_trades` | `reference` | `akshare:read_reference` | `symbol`, `trade_date`, `limit` |
| 沪深董秘问答 | `cn_irm_qa` | `company_content` | `akshare:read_content` | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page` |
| 公告数据 | `announcements` | `company_content` | `akshare:read_disclosure` | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page` |
| 新闻资讯 | `news` | `company_content` | `akshare:read_content` | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page` |
| 政策法规库 | `policy_library` | `company_content` | `akshare:read_content` | `symbol`, `keyword`, `start_date`, `end_date`, `limit`, `page` |
| 券商研报 | `broker_reports` | `company_content` | `akshare:read_content` | `symbol`, `keyword`, `limit`, `page` |
| A股历史分钟 | `cn_equity_minute_history` | `market_data` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| A股分钟RT | `cn_equity_minute_realtime` | `market_data` | `akshare:read_realtime` | `symbol`, `period`, `limit` |
| A股日线RT | `cn_equity_daily_realtime` | `market_data` | `akshare:read_realtime` | `symbol`, `trade_date`, `fields` |
| 指数历史分钟 | `index_minute_history` | `market_data` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| 指数分钟RT | `index_minute_realtime` | `market_data` | `akshare:read_realtime` | `symbol`, `period`, `limit` |
| 指数日线RT | `index_daily_realtime` | `market_data` | `akshare:read_realtime` | `symbol`, `trade_date`, `fields` |
| 申万指数分钟 | `sw_index_minute_history` | `market_data` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| 申万实时行情 | `sw_realtime_quotes` | `market_data` | `akshare:read_reference` | `symbol`, `period`, `limit` |
| ETF历史分钟 | `etf_minute_history` | `derivatives` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| ETF分钟RT | `etf_minute_realtime` | `derivatives` | `akshare:read_realtime` | `symbol`, `period`, `limit` |
| ETF日线RT | `etf_daily_realtime` | `derivatives` | `akshare:read_realtime` | `symbol`, `trade_date`, `fields` |
| 期权历史分钟 | `option_minute_history` | `derivatives` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| 可转债价格变动 | `convertible_bond_price_change` | `derivatives` | `akshare:read_reference` | `symbol`, `trade_date`, `limit` |
| 期货历史分钟 | `futures_minute_history` | `futures` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| 期货实时分钟 | `futures_minute_realtime` | `futures` | `akshare:read_realtime` | `symbol`, `period`, `limit` |
| 港股历史日线 | `hk_daily_history` | `cross_border` | `akshare:read_history` | `symbol`, `start_date`, `end_date`, `adjust`, `fields` |
| 港股历史分钟 | `hk_minute_history` | `cross_border` | `akshare:read_history` | `symbol`, `start_time`, `end_time`, `period`, `adjust` |
| 港股实时日线 | `hk_daily_realtime` | `cross_border` | `akshare:read_realtime` | `symbol`, `trade_date`, `fields` |
| 港股财报 | `hk_financial_reports` | `cross_border` | `akshare:read_disclosure` | `symbol`, `report_period`, `statement_type`, `limit` |
| 美股历史日线 | `us_daily_history` | `cross_border` | `akshare:read_history` | `symbol`, `start_date`, `end_date`, `adjust`, `fields` |
| 美股财报 | `us_financial_reports` | `cross_border` | `akshare:read_disclosure` | `symbol`, `report_period`, `statement_type`, `limit` |

### 8.18 AKShare 模块视角总览

为了方便业务同学理解，也可以从模块角度看这 28 个能力：

- `reference`
  - `pre_market_capital`
  - `call_auction_trades`
- `company_content`
  - `cn_irm_qa`
  - `announcements`
  - `news`
  - `policy_library`
  - `broker_reports`
- `market_data`
  - `cn_equity_minute_history`
  - `cn_equity_minute_realtime`
  - `cn_equity_daily_realtime`
  - `index_minute_history`
  - `index_minute_realtime`
  - `index_daily_realtime`
  - `sw_index_minute_history`
  - `sw_realtime_quotes`
- `derivatives`
  - `etf_minute_history`
  - `etf_minute_realtime`
  - `etf_daily_realtime`
  - `option_minute_history`
  - `convertible_bond_price_change`
- `futures`
  - `futures_minute_history`
  - `futures_minute_realtime`
- `cross_border`
  - `hk_daily_history`
  - `hk_minute_history`
  - `hk_daily_realtime`
  - `hk_financial_reports`
  - `us_daily_history`
  - `us_financial_reports`

### 8.19 AKShare 常见调用路径模板

对任一能力编码 `<code>`，你通常会用到下面这些路径：

```text
GET  /api/v1/akshare/capabilities/<code>
POST /api/v1/akshare/capabilities/<code>/token
GET  /api/v1/akshare/capabilities/<code>/access
GET  /api/v1/akshare/<code>
GET  /api/v1/akshare/<code>/debug
```

例如 `broker_reports`：

```text
GET  /api/v1/akshare/capabilities/broker_reports
POST /api/v1/akshare/capabilities/broker_reports/token
GET  /api/v1/akshare/capabilities/broker_reports/access
GET  /api/v1/akshare/broker_reports
GET  /api/v1/akshare/broker_reports/debug
```

### 8.20 和现有 AK 参考文档的关系

如果你还需要：

- 更细的能力背景说明
- 更偏治理视角的介绍
- 已购能力与包装接口的展开说明

可以继续看仓库里的 [akshare-interface-reference.md](/Users/hzzp/Minishare/docs/akshare-interface-reference.md)。本文已经把用户接入需要的 AK 能力清单补进来了，但那份文档仍然适合做治理侧补充参考。

## 9. AI 接口

当前项目里有四个用户侧 AI 接口。

### 9.1 AI 能力与权限差异

按照当前代码里的角色权限映射：

- 普通用户 `user` 默认有 `ai:question`
- `vip` 和 `admin` 同时有 `ai:question`、`ai:chat`、`ai:analyze`

因此你不能默认每个账号都能调用聊天和分析接口。

### 9.2 `POST /api/v1/ai/chat`

- 用途：通用聊天接口
- 认证方式：`X-API-Key`
- 权限要求：`ai:chat`
- 请求体：

```json
{
  "messages": [
    {"role": "system", "content": "你是一个金融分析助手"},
    {"role": "user", "content": "请总结今天市场的主要风险点"}
  ],
  "temperature": 0.5,
  "max_tokens": 800
}
```

- 必填字段：
  - `messages`
- 返回字段：
  - `response`
  - `usage`

- 常见错误：
  - `400`：缺少 `messages`
  - `403`：当前用户没有 `ai:chat`
  - `503`：GLM 服务未配置
  - `500`：AI 上游调用异常

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/ai/chat" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "messages": [
      {"role": "user", "content": "帮我总结一下近期市场关注点"}
    ]
  }'
```

### 9.3 `POST /api/v1/ai/analyze`

- 用途：面向金融数据描述的分析接口
- 认证方式：`X-API-Key`
- 权限要求：`ai:analyze`
- 请求体：

```json
{
  "data_description": "这是某只股票最近 20 个交易日的 OHLCV 数据",
  "data_context": "行业为白酒，市场近期波动较大",
  "question": "请判断近期走势是否存在放量回调"
}
```

- 必填字段：
  - `data_description`
- 返回字段：
  - `analysis`
  - `input`

- 常见错误：
  - `400`：缺少 `data_description`
  - `403`：当前用户没有 `ai:analyze`
  - `503`：GLM 服务未配置

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/ai/analyze" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "data_description": "这是某只股票最近 20 个交易日的价格与成交量数据",
    "data_context": "近期板块轮动加快",
    "question": "请给出趋势判断和风险提示"
  }'
```

### 9.4 `POST /api/v1/ai/question`

- 用途：面向普通问答的轻量 AI 接口
- 认证方式：`X-API-Key`
- 权限要求：`ai:question`
- 请求体：

```json
{
  "question": "什么是换手率？",
  "context": "请用股票市场的语境解释"
}
```

- 必填字段：
  - `question`
- 返回字段：
  - `answer`
  - `question`
  - `context`

- 常见错误：
  - `400`：缺少 `question`
  - `503`：GLM 服务未配置

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/ai/question" -X POST \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <your-api-key>" \
  -d '{
    "question": "什么是市盈率？",
    "context": "请用适合新手的方式解释"
  }'
```

### 9.5 `GET /api/v1/ai/status`

- 用途：查看当前服务端 AI 能力是否启用
- 认证方式：`X-API-Key`
- 返回字段：
  - `glm_enabled`
  - `glm_model`
  - `glm_max_tokens`
  - `glm_temperature`
  - `glm_configured`

示例：

```bash
curl "https://minishare.wmlgg.com/api/v1/ai/status" \
  -H "X-API-Key: <your-api-key>"
```

## 10. 常见响应字段与返回约定

不同接口的返回结构不完全一样，但你可以重点理解下面这些常见字段。

### 10.1 通用查询类字段

在 `/api/v1/query`、`/api/v1/stock-basic`、`/api/v1/daily` 这一类接口里，常见字段有：

- `columns`：列名列表
- `rows`：结果行数组
- `row_count`：结果行数
- `requested_by`：调用者用户名

### 10.2 缓存相关字段

- `cached`
  - `true`：本次响应来自缓存或缓存化结果
  - `false`：本次响应更可能来自实时请求或未命中缓存的路径

- `cache_layer`
  - 常见含义是当前命中了哪一层缓存或数据层
  - 例如可能来自 Redis、MySQL、物化层、本地表或上游源

### 10.3 AKShare 响应里的额外字段

AKShare 直接请求接口通常还会带这些字段：

- `capability_code`
- `display_name`
- `permission_code`
- `available_now`
- `request_params`
- `upstream_api_names`
- `notes`
- `upstream_result`

### 10.4 AI 响应里的额外字段

AI 接口常见字段包括：

- `response`
- `analysis`
- `answer`
- `usage`

其中 `usage` 不一定每个 AI 接口都返回，但如果有，一般表示本次模型调用的用量信息。

## 11. 常见错误与排错建议

### 11.1 `400 Bad Request`

常见原因：

- 请求体缺少必须字段
- 字段值格式不符合校验规则
- AI 接口没传必填字段

建议排查：

- 先核对 JSON 结构
- 再核对字段名是否和文档完全一致

### 11.2 `401 Unauthorized`

常见原因：

- 账号密码错误
- Session 已失效
- API Key 不存在、已禁用或已过期

建议排查：

- 登录接口确认账号密码
- 用 `GET /api/v1/session/me` 检查 Session
- 用 `GET /api/v1/me` 检查 API Key

### 11.3 `403 Forbidden`

常见原因：

- 角色没有对应权限
- AKShare 当前时窗不可访问
- Bearer Token 没有包含请求的能力或权限
- 请求了当前用户没有授权的 AK 能力

建议排查：

- 先看自己的角色
- 再看 AK 能力当前是否 `available_now`
- 如果是 Bearer Token，确认 `granted_entitlement_codes` 和 `granted_permission_codes`

### 11.4 `404 Not Found`

常见原因：

- AK 能力编码写错
- 要禁用的 API Key 不存在
- 请求了系统不认识的能力

建议排查：

- 先用 `GET /api/v1/akshare/capabilities` 查标准能力编码

### 11.5 `422 Unprocessable Entity`

常见原因：

- JSON 结构不符合 schema
- AK token 的 `expires_in_seconds` 超过系统允许上限
- 访问校验接口没传 `entitlement_code`

建议排查：

- 看响应里的 `detail`
- 检查字段类型、空值和时间格式

### 11.6 `503 Service Unavailable`

常见原因：

- GLM 服务未配置
- AI 接口当前不可用

建议排查：

- 先调用 `GET /api/v1/ai/status`
- 查看 `glm_enabled` 和 `glm_configured`

### 11.7 AKShare 最容易踩的坑

#### 1. 能看到能力目录，不代表一定能请求成功

目录只是目录。真正能不能请求成功，还要看：

- 当前用户有没有授权
- 当前时窗是否可访问
- 当前 token 是否包含这个能力

#### 2. 请求了 Bearer Token，但 token 没包含目标能力

这种情况下会收到 `403`。你需要重新签发包含对应能力的 token。

#### 3. 日期和时间参数格式混用

不同 AK 能力对日期时间的要求不完全一样，常见格式包括：

- `YYYYMMDD`
- `YYYY-MM-DD`
- `YYYY-MM-DDTHH:MM:SS`

最稳妥的做法是先看该能力的 `request_fields`，再参考本文的能力总表和示例请求。

## 12. 用户接口速查表

下面这张表把本文覆盖的普通用户接口整理成一张总表，适合快速查找。

| 路径 | 方法 | 认证方式 | 用途 |
| --- | --- | --- | --- |
| `/api` | `GET` | 无 | 最基础的服务连通性检查 |
| `/api/v1/session/login` | `POST` | 无 | 登录并建立 Session |
| `/api/v1/session/logout` | `POST` | Session Cookie | 退出登录 |
| `/api/v1/session/me` | `GET` | Session Cookie | 查看当前 Session 用户 |
| `/api/v1/session/api-keys` | `POST` | Session Cookie | 创建自己的 API Key |
| `/api/v1/session/api-keys/<api_key_id>/disable` | `POST` | Session Cookie | 禁用自己的 API Key |
| `/api/v1/session/password` | `POST` | Session Cookie | 修改自己的密码 |
| `/api/v1/me` | `GET` | `X-API-Key` | 用 API Key 查看当前调用者 |
| `/api/v1/query` | `POST` | `X-API-Key` | 通用查询入口 |
| `/api/v1/stock-basic` | `GET` | `X-API-Key` | 查询股票基础信息 |
| `/api/v1/daily` | `GET` | `X-API-Key` | 查询日线行情 |
| `/api/v1/akshare/entitlements` | `GET` | `X-API-Key` | 查看当前用户的 AK 授权视图 |
| `/api/v1/akshare/capabilities` | `GET` | `X-API-Key` | 查看 AK 能力目录 |
| `/api/v1/akshare/capabilities/<capability_code>` | `GET` | `X-API-Key` | 查看单个 AK 能力详情 |
| `/api/v1/akshare/materialized/summary` | `GET` | `X-API-Key` | 查看 AK 物化总览 |
| `/api/v1/akshare/materialized/content-documents` | `GET` | `X-API-Key` | 查询物化内容文档 |
| `/api/v1/akshare/materialized/financial-reports` | `GET` | `X-API-Key` | 查询物化财报 |
| `/api/v1/akshare/materialized/sync-states` | `GET` | `X-API-Key` | 查询物化同步状态 |
| `/api/v1/akshare/tokens/issue` | `POST` | `X-API-Key` | 批量签发 AK 临时 Token |
| `/api/v1/akshare/capabilities/<capability_code>/token` | `POST` | `X-API-Key` | 为单个能力签发 AK 临时 Token |
| `/api/v1/akshare/<capability_code>` | `GET` | `X-API-Key` 或 Bearer | 直接请求某个 AK 能力 |
| `/api/v1/akshare/<capability_code>/debug` | `GET` | Session Cookie | 用登录会话调试某个 AK 能力 |
| `/api/v1/akshare/access` | `GET` | `X-API-Key` 或 Bearer | 按编码做 AK 访问校验 |
| `/api/v1/akshare/capabilities/<capability_code>/access` | `GET` | `X-API-Key` 或 Bearer | 用能力别名做 AK 访问校验 |
| `/api/v1/ai/chat` | `POST` | `X-API-Key` | AI 聊天 |
| `/api/v1/ai/analyze` | `POST` | `X-API-Key` | AI 数据分析 |
| `/api/v1/ai/question` | `POST` | `X-API-Key` | AI 问答 |
| `/api/v1/ai/status` | `GET` | `X-API-Key` | 检查 AI 配置状态 |
