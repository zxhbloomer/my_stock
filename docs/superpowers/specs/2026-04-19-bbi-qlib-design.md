# BBI因子 + Qlib完整流水线 设计文档

**日期**: 2026-04-19  
**项目**: my_stock  
**目标**: 将BBI（Bull Bear Index）作为自定义因子加入Qlib Alpha158因子库，使用LightGBM在A股全市场选股，完成预测→选股→回测完整链路。

---

## 1. 系统目标

### 1.1 解决什么问题

现有 `scripts/50_个股回测/50_BBI个股回测.py` 是单股规则回测，存在三个局限：
1. 只能测单只股票，无法全市场选股
2. 手写回测引擎，未考虑涨跌停、T+1等A股约束
3. BBI是硬规则（金叉买/死叉卖），无法结合其他因子

本设计解决上述问题：用Qlib完整流水线，BBI作为因子之一，LightGBM综合预测，全市场选股。

### 1.2 跑出来是什么

```
输出1：IC分析报告
  - 每日预测分数与实际收益的相关性（IC均值、ICIR）
  - 判断BBI因子对模型的贡献度
  - IC > 0.02 表示模型有预测力

输出2：组合回测报告
  - 年化收益率（对比CSI500 benchmark）
  - 最大回撤
  - 信息比率（IR > 1.0 为优秀）
  - 超额收益曲线图

输出3：每日持仓列表
  - 从CSI500中每天选top-50只股票
  - 每期替换5只（TopkDropoutStrategy）
```

### 1.3 不做什么

- 不做单只股票预测（qlib是全市场选股逻辑）
- 不做实盘交易接入
- 不做分钟级高频策略

---

## 2. 架构设计

### 2.1 完整流水线

```
PostgreSQL (tushare_v2)
    │
    ├── 063_stk_factor_pro  → 价格(复权OHLCV) + BBI因子
    ├── 027_daily_basic     → 估值因子(PE/PB/换手率)
    ├── 061_cyq_perf        → 筹码因子(平均成本/胜率)
    ├── 080_moneyflow       → 资金流因子(大单净流入)
    ├── 029_stk_limit       → 涨跌停(回测约束)
    ├── 030_suspend_d       → 停复牌(回测约束)
    ├── 001_stock_basic     → 股票列表
    ├── 003_trade_cal       → 交易日历
    └── 122_index_daily     → 指数行情(benchmark)
         │
         ▼
scripts/bbi/01_data_to_qlib.py   ← 数据转换层
    将PostgreSQL数据转为Qlib二进制格式
    输出到 D:\Data\my_stock\
         │
         ▼
scripts/bbi/02_train_predict.py  ← 模型训练层
    BBIAlpha Handler（Alpha158 + BBI因子）
    LightGBM训练
    生成每日预测score
         │
         ▼
scripts/bbi/03_backtest.py       ← 回测层
    TopkDropoutStrategy（top50，每期换5只）
    Exchange（涨跌停9.5%，T+1，手续费）
    输出IC分析 + 组合回测报告
```

### 2.2 目录结构

```
scripts/bbi/
├── 01_data_to_qlib.py      # 数据转换：PostgreSQL → Qlib二进制
├── 02_train_predict.py     # 模型训练与预测
├── 03_backtest.py          # 回测与结果分析
├── handler.py              # BBIAlpha自定义Handler
└── config.yaml             # 统一配置文件
```

---

## 3. 数据层设计

### 3.0 股票池过滤规则

全A股（6006只）作为基础池，每日动态过滤：

**必须过滤（硬规则）**

| 条件 | 标准 | 数据来源 |
|------|------|---------|
| 去除ST/\*ST | `name`不含"ST" | `001_stock_basic` |
| 去除停牌 | 当日无停牌记录 | `030_suspend_d` |
| 去除涨跌停 | 不在涨跌停价格 | `029_stk_limit` |
| 去除次新股 | 上市满1年 | `001_stock_basic.list_date` |

**强烈建议过滤**

| 条件 | 标准 | 原因 |
|------|------|------|
| 最小流通市值 | > 20亿 | 小盘股冲击成本高 |
| 最小日均成交额 | > 5000万 | 保证流动性 |
| 去除退市风险 | 非退市整理板 | 避免踩雷 |

**交易所过滤**

| 条件 | 标准 |
|------|------|
| 去除北交所 | `ts_code`不以`8`开头 |

所有过滤条件均来自现有数据库表，无需额外数据。

### 3.1 数据源选择

**使用 `tushare_v2.063_stk_factor_pro` 作为主数据源**（已验证）：
- 数据范围：2010-01-04 至 2026-04-16
- 股票数量：6006只（覆盖全A股历史）
- 包含字段：`open_qfq`, `high_qfq`, `low_qfq`, `close_qfq`, `vol`（后复权）
- 包含BBI：`bbi_qfq`（直接可用，无需重算）

**辅助数据源**：
| 表名 | 用途 | 关键字段 |
|------|------|---------|
| 027_daily_basic | 估值因子 | pe_ttm, pb, ps_ttm, turnover_rate, volume_ratio |
| 061_cyq_perf | 筹码因子 | cost_5pct, cost_15pct, cost_85pct, cost_95pct, weight_avg, winner_rate |
| 080_moneyflow | 资金流因子 | buy_lg_amount, sell_lg_amount, net_mf_amount |
| 029_stk_limit | 回测约束 | up_limit, down_limit |
| 030_suspend_d | 回测约束 | suspend_type |

### 3.2 Qlib数据格式

Qlib需要以下目录结构（输出到 `D:\Data\my_stock\`）：
```
D:\Data\my_stock\
├── calendars/day.txt          # 交易日历
├── instruments/
│   ├── all.txt                # 全部股票列表
│   └── csi500.txt             # CSI500成分股
└── features/
    └── {symbol}/              # 每只股票一个目录
        ├── open.day.bin
        ├── high.day.bin
        ├── low.day.bin
        ├── close.day.bin
        ├── volume.day.bin
        ├── factor.day.bin     # 复权因子（固定为1.0，因为已用后复权价格）
        ├── vwap.day.bin       # 用close_qfq代替（063表无vwap）
        ├── bbi.day.bin        # BBI值（来自bbi_qfq）
        ├── pe_ttm.day.bin     # 来自027_daily_basic
        ├── pb.day.bin
        ├── turnover.day.bin
        ├── winner_rate.day.bin # 来自061_cyq_perf
        ├── cost_avg.day.bin
        ├── net_mf.day.bin     # 来自080_moneyflow
        └── ...
```

---

## 4. 因子设计（BBIAlpha Handler）

### 4.1 继承Alpha158，新增BBI因子组

```python
class BBIAlpha(Alpha158):
    """Alpha158 + BBI因子扩展"""
    
    def get_feature_config(self):
        # 继承Alpha158的158个因子
        fields, names = super().get_feature_config()
        
        # 新增BBI因子组（6个）
        bbi_fields = [
            "$bbi/$close",                    # BBI相对价格（归一化）
            "$close/$bbi - 1",                # 价格偏离BBI程度
            "($bbi - Ref($bbi,1))/$bbi",      # BBI斜率（趋势方向）
            "If($close > $bbi, 1, -1)",       # 金叉/死叉状态
            "Mean($close > $bbi, 5)",         # 近5日金叉占比
            "Mean($close > $bbi, 20)",        # 近20日金叉占比
        ]
        bbi_names = [
            "BBI_RATIO", "BBI_DEV", "BBI_SLOPE",
            "BBI_CROSS", "BBI_CROSS5", "BBI_CROSS20"
        ]
        
        # 新增估值因子组（来自027_daily_basic）
        val_fields = [
            "$pe_ttm", "$pb", "$turnover",
            "Rank($pe_ttm, 20)", "Rank($turnover, 20)"
        ]
        val_names = ["PE_TTM", "PB", "TURNOVER", "PE_RANK20", "TURN_RANK20"]
        
        # 新增筹码因子组（来自061_cyq_perf）
        chip_fields = [
            "$winner_rate",
            "$cost_avg/$close - 1",           # 平均成本偏离
        ]
        chip_names = ["WINNER_RATE", "COST_DEV"]
        
        # 新增资金流因子（来自080_moneyflow）
        flow_fields = [
            "$net_mf / ($volume * $close + 1e-12)",  # 净流入占比
            "Mean($net_mf, 5) / ($volume * $close + 1e-12)",
        ]
        flow_names = ["MF_RATIO", "MF_RATIO5"]
        
        fields += bbi_fields + val_fields + chip_fields + flow_fields
        names += bbi_names + val_names + chip_names + flow_names
        
        return fields, names
```

**总因子数**：158（Alpha158）+ 6（BBI）+ 5（估值）+ 2（筹码）+ 2（资金流）= **173个因子**

### 4.2 Label定义

沿用Alpha158标准label：
```python
label = "Ref($close, -2) / Ref($close, -1) - 1"
# 含义：预测明天的收益率（T+2收盘/T+1收盘 - 1）
# 原因：T+1制度下，今天信号明天才能买，后天才能卖
```

---

## 5. 模型与回测配置

### 5.1 训练配置

```yaml
market: csi500
benchmark: SH000905

data_handler_config:
  start_time: 2010-01-01
  end_time: 2026-04-16
  instruments: csi500

segments:
  train: [2010-01-01, 2020-12-31]   # 10年训练
  valid: [2021-01-01, 2022-12-31]   # 2年验证
  test:  [2023-01-01, 2026-04-16]   # 3年测试

model: LightGBM（沿用现有参数）
```

### 5.2 回测配置

```yaml
strategy:
  class: TopkDropoutStrategy
  topk: 50          # 持仓50只
  n_drop: 5         # 每期替换5只
  hold_thresh: 1    # 最少持仓1天

exchange:
  limit_threshold: 0.095   # 涨跌停9.5%
  deal_price: close
  open_cost: 0.0005        # 开仓0.05%
  close_cost: 0.0015       # 平仓0.15%
  min_cost: 5              # 最低5元
```

---

## 6. 输出结果说明

### 6.1 IC分析（模型质量）

| 指标 | 含义 | 目标值 |
|------|------|--------|
| IC Mean | 预测与实际收益相关性均值 | > 0.02 |
| ICIR | IC均值/IC标准差 | > 0.5 |
| Rank IC | 排名相关性 | > 0.03 |

### 6.2 回测报告（策略收益）

| 指标 | 含义 | 目标值 |
|------|------|--------|
| 年化收益 | 策略年化超额收益 | > 10% |
| 最大回撤 | 最大亏损幅度 | < 20% |
| 信息比率IR | 风险调整后收益 | > 1.0 |
| 胜率 | 盈利交易占比 | > 55% |

### 6.3 可视化输出

- 超额收益曲线（策略 vs CSI500）
- IC时序图（每月IC变化）
- 持仓换手率分析

---

## 7. 实现步骤

1. **数据转换脚本** `01_data_to_qlib.py`
   - 从PostgreSQL读取063/027/061/080表
   - 写入Qlib二进制格式到 `D:\Data\my_stock\`
   - 生成交易日历、股票列表、CSI500成分

2. **自定义Handler** `handler.py`
   - 继承Alpha158，新增BBI+估值+筹码+资金流因子
   - 共173个因子

3. **训练脚本** `02_train_predict.py`
   - 使用BBIAlpha Handler
   - LightGBM训练，生成预测score
   - 保存到MLflow

4. **回测脚本** `03_backtest.py`
   - TopkDropoutStrategy选股
   - Exchange模拟交易
   - 输出IC分析 + 组合报告

---

## 8. 数据缺口说明

| 数据 | 状态 | 说明 |
|------|------|------|
| 复权OHLCV | ✅ 已有 | 063_stk_factor_pro.close_qfq等 |
| BBI值 | ✅ 已有 | 063_stk_factor_pro.bbi_qfq |
| 估值指标 | ✅ 已有 | 027_daily_basic |
| 筹码数据 | ✅ 已有（2018起） | 061_cyq_perf |
| 资金流 | ✅ 已有（2010起） | 080_moneyflow |
| 涨跌停 | ✅ 已有 | 029_stk_limit |
| 停复牌 | ✅ 已有 | 030_suspend_d |
| 交易日历 | ✅ 已有 | 003_trade_cal |
| 股票列表 | ✅ 已有 | 001_stock_basic |
| 指数行情 | ✅ 已有 | 122_index_daily |
| 014_daily | ❌ 无此表 | 用063替代，无影响 |

---

## 9. 阶段2：每日荐股（在阶段1验证有效后实施）

### 9.1 目标

模型训练好后，每天收盘后自动运行，输出**今日推荐股票列表**（预测分数最高的N只）。

### 9.2 技术方案

Qlib原生支持 `OnlineTool`（`qlib/contrib/online/`），流程：

```
每日收盘后（约18:00）
    ↓
数据库更新完成（063/027/061/080当日数据入库）
    ↓
scripts/bbi/04_daily_recommend.py
    ↓
update_online_pred() → 用最新数据跑模型推理
    ↓
输出：今日推荐股票列表（ts_code + 预测分数 + 排名）
    ↓
保存到 data/手动执行/推荐结果/YYYY-MM-DD.csv
```

### 9.3 新增脚本

```
scripts/bbi/
├── 04_daily_recommend.py   # 每日推荐，输出荐股列表
└── 05_view_recommend.py    # 查看历史推荐结果
```

### 9.4 输出格式

```csv
date,ts_code,name,score,rank,bbi_cross,pe_ttm,winner_rate
2026-04-19,600519.SH,贵州茅台,0.0312,1,1,28.5,0.72
2026-04-19,300750.SZ,宁德时代,0.0298,2,1,35.2,0.68
...
```

### 9.5 前提条件

- 阶段1回测验证：IC均值 > 0.02，年化超额 > 10%
- 数据库每日自动更新（现有 data/collectors 流程已支持）
- 模型已训练并保存到 MLflow

---

## 10. Tushare接口完整对应表

基于接口清单（239个接口）逐类分析，以下是本系统实际使用的接口：

### 必须接口（系统无法运行）

| 编号 | 接口名 | 中文名 | 用途 | 数据库表 |
|------|--------|--------|------|---------|
| 001 | stock_basic | 股票列表 | 股票池、上市/退市日期 | tushare_v2.001_stock_basic |
| 003 | trade_cal | 交易日历 | Qlib时间轴 | tushare_v2.003_trade_cal |
| 063 | stk_factor_pro | 技术因子(专业版) | 复权OHLCV + BBI值 | tushare_v2.063_stk_factor_pro |
| 122 | index_daily | 指数日线 | CSI500 benchmark对比 | tushare_v2.122_index_daily |
| 128 | index_weight | 指数成分权重 | CSI500股票池过滤 | ❌ 需确认是否已入库 |

### 强烈推荐接口（显著提升模型效果）

| 编号 | 接口名 | 中文名 | 用途 | 数据库表 |
|------|--------|--------|------|---------|
| 027 | daily_basic | 每日指标 | PE/PB/换手率/量比等估值因子 | tushare_v2.027_daily_basic |
| 061 | cyq_perf | 每日筹码及胜率 | 平均成本/胜率（2018起） | tushare_v2.061_cyq_perf |
| 080 | moneyflow | 个股资金流向 | 大单净流入（2010起） | tushare_v2.080_moneyflow |

### 回测约束接口（回测准确性必须）

| 编号 | 接口名 | 中文名 | 用途 | 数据库表 |
|------|--------|--------|------|---------|
| 029 | stk_limit | 每日涨跌停价格 | 过滤涨跌停不可交易 | tushare_v2.029_stk_limit |
| 030 | suspend_d | 每日停复牌 | 过滤停牌股 | tushare_v2.030_suspend_d |

### 不使用的接口（原因说明）

| 类别 | 接口编号 | 不使用原因 |
|------|---------|-----------|
| 财务报表 | 036/037/038/042 | 季度频率，与日线因子频率不匹配 |
| 分钟数据 | 016/017 | 日线模型不需要 |
| 筹码分布 | 062 cyq_chips | 颗粒度过细，cyq_perf已够用 |
| 资金流(THS/DC) | 081/082 | 081数据从2023起太短；082需5000积分且2023起 |
| 融资融券 | 073/074 | 可选，首期不加，避免复杂度 |
| 北向资金 | 066 hk_hold | 可选，首期不加 |
| 宏观数据 | 219-224 | 全市场统一，对个股区分度低 |
| 港股/美股/期货 | 184-203 | 与A股选股无关 |
| 014 daily | 014 | 无此表，063已含复权价格，无需 |
