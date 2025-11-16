# configs/ 目录说明

## 📁 目录作用

`configs/` 目录存放 **Qlib 工作流配置文件**，这些文件定义了：
- 使用什么数据（股票池、时间范围）
- 使用什么模型（LightGBM参数）
- 使用什么因子（Alpha158、自定义因子）
- 如何回测（策略、交易成本）

**核心思想**：**配置与代码分离**，通过修改 YAML 配置文件就能改变策略，无需修改代码。

---

## 📋 当前配置文件清单

### **1. workflow_config_lightgbm_Alpha158.yaml**（基础配置）
```yaml
市场: CSI300（沪深300）
基准: SH000300
因子: Alpha158（158个技术指标）
模型参数: Qlib官方默认参数
用途: 基线策略，参考配置
```

### **2. workflow_config_lightgbm_Alpha158_csi500.yaml**（中证500）
```yaml
市场: CSI500（中证500）
基准: SH000905
因子: Alpha158
模型参数: Qlib官方默认参数
用途: 中小盘股票策略
```

### **3. workflow_config_top50.yaml**（Top50因子）⭐
```yaml
市场: CSI300
基准: SH000905（注意：这里可能有问题，应该是SH000300）
因子: Top50因子（从255个Alpha158因子中筛选出的强因子）
模型参数: Qlib官方参数
用途: 使用IC分析后筛选的强因子
创建: 由 scripts/22_训练Top因子模型.py 自动生成
```

### **4. workflow_config_custom.yaml**（自定义配置）
```yaml
用途: 用户自定义配置，可以随意修改
```

### **5. workflow_config_optimized_csi300.yaml**（参数优化后）🆕
```yaml
市场: CSI300
基准: SH000300
因子: Alpha158
模型参数: 由 scripts/参数优化_改进版.py 优化后的最佳参数
用途: 使用贝叶斯优化后的参数
创建: 自动生成
```

---

## 🔄 配置文件如何被使用？

### **方法1：scripts/一键运行.py**（推荐）

```python
# scripts/一键运行.py 的核心逻辑：

def run_workflow(config_path):
    # 1. 读取YAML配置文件
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    # 2. 使用配置初始化Qlib
    qlib.init(**config['qlib_init'])

    # 3. 使用配置创建模型
    model = init_instance_by_config(config['task']['model'])

    # 4. 使用配置加载数据
    dataset = init_instance_by_config(config['task']['dataset'])

    # 5. 训练模型
    model.fit(dataset)

    # 6. 回测
    # ... 使用 config['port_analysis_config']
```

**使用示例**：
```bash
# 使用默认配置
python scripts/一键运行.py

# 使用Top50因子配置
python scripts/一键运行.py configs/workflow_config_top50.yaml

# 使用优化后的参数配置
python scripts/一键运行.py configs/workflow_config_optimized_csi300.yaml
```

### **方法2：Qlib官方命令 qrun**

```bash
# 直接使用qrun命令
qrun configs/workflow_config_lightgbm_Alpha158.yaml
```

---

## 📊 配置文件结构详解

### **完整的YAML结构**

```yaml
# ========== 1. Qlib初始化配置 ==========
qlib_init:
    provider_uri: "D:\\Data\\my_stock"  # 数据路径
    region: cn                           # 地区（中国）

# ========== 2. 市场和基准 ==========
market: &market csi300                   # 股票池（YAML锚点，后面可引用）
benchmark: &benchmark SH000300           # 基准指数

# ========== 3. 数据处理配置 ==========
data_handler_config: &data_handler_config
    start_time: 2008-01-01               # 数据开始时间
    end_time: 2020-08-01                 # 数据结束时间
    fit_start_time: 2008-01-01           # 特征工程训练开始
    fit_end_time: 2014-12-31             # 特征工程训练结束
    instruments: *market                 # 引用市场（csi300）

# ========== 4. 回测策略配置 ==========
port_analysis_config: &port_analysis_config
    strategy:
        class: TopkDropoutStrategy       # 策略类
        module_path: qlib.contrib.strategy.strategy
        kwargs:
            topk: 50                     # 持有前50只股票
            n_drop: 5                    # 每次调仓卖出5只
            signal: <PRED>               # 使用模型预测作为信号
    backtest:
        start_time: 2017-01-01           # 回测开始时间
        end_time: 2020-08-01             # 回测结束时间
        account: 100000000               # 初始资金1亿
        benchmark: *benchmark            # 引用基准（SH000300）
        exchange_kwargs:
            limit_threshold: 0.095       # 涨跌停限制9.5%
            deal_price: close            # 成交价为收盘价
            open_cost: 0.0005            # 买入手续费0.05%
            close_cost: 0.0015           # 卖出手续费0.15%
            min_cost: 5                  # 最低手续费5元

# ========== 5. 核心任务配置 ==========
task:
    # 5.1 模型配置
    model:
        class: LGBModel                  # LightGBM模型
        module_path: qlib.contrib.model.gbdt
        kwargs:
            loss: mse                    # 损失函数
            colsample_bytree: 0.8879     # 特征采样率
            learning_rate: 0.0421        # 学习率（可优化）
            subsample: 0.8789            # 样本采样率
            lambda_l1: 205.6999          # L1正则
            lambda_l2: 580.9768          # L2正则
            max_depth: 8                 # 树深度（可优化）
            num_leaves: 210              # 叶子节点数（可优化）
            num_threads: 20              # 线程数

    # 5.2 数据集配置
    dataset:
        class: DatasetH                  # Qlib标准数据集类
        module_path: qlib.data.dataset
        kwargs:
            handler:
                class: Alpha158          # Alpha158因子（158个技术指标）
                module_path: qlib.contrib.data.handler
                kwargs: *data_handler_config  # 引用数据处理配置
            segments:
                train: [2008-01-01, 2014-12-31]  # 训练集
                valid: [2015-01-01, 2016-12-31]  # 验证集
                test: [2017-01-01, 2020-08-01]   # 测试集

    # 5.3 记录器配置（保存结果）
    record:
        - class: SignalRecord            # 保存预测信号
          module_path: qlib.workflow.record_temp
          kwargs: {}
        - class: SigAnaRecord            # 保存信号分析
          module_path: qlib.workflow.record_temp
          kwargs:
              ana_long_short: False
              ann_scaler: 252
        - class: PortAnaRecord           # 保存组合分析
          module_path: qlib.workflow.record_temp
          kwargs:
              config: *port_analysis_config
```

---

## 🔧 配置文件参数说明

### **关键参数对照表**

| 配置项 | 参数 | 说明 | 示例值 |
|-------|------|------|--------|
| **市场** | `market` | 股票池 | `csi300`, `csi500` |
| **基准** | `benchmark` | 对比基准 | `SH000300`（沪深300指数）, `SH000905`（中证500指数） |
| **数据时间** | `start_time`, `end_time` | 全部数据范围 | `2008-01-01` ~ `2020-08-01` |
| **训练时间** | `segments.train` | 模型训练时间 | `2008-01-01` ~ `2014-12-31` |
| **验证时间** | `segments.valid` | 参数调优时间 | `2015-01-01` ~ `2016-12-31` |
| **测试时间** | `segments.test` | 回测时间 | `2017-01-01` ~ `2020-08-01` |
| **因子库** | `handler.class` | 特征工程方法 | `Alpha158`, `DataHandlerLP` |
| **模型** | `model.class` | 预测模型 | `LGBModel`, `XGBModel` |
| **策略** | `strategy.class` | 交易策略 | `TopkDropoutStrategy` |

### **LightGBM可优化参数**

| 参数 | 默认值 | 优化范围 | 影响 |
|------|--------|---------|------|
| `learning_rate` | 0.0421 | 0.01-0.3 | 学习速度，影响训练时间和精度 |
| `num_leaves` | 210 | 20-210 | 模型复杂度，过大易过拟合 |
| `max_depth` | 8 | 3-10 | 树深度，控制复杂度 |
| `feature_fraction` | 0.8879 | 0.6-1.0 | 特征采样率，防过拟合 |
| `bagging_fraction` | 0.8789 | 0.6-1.0 | 样本采样率，防过拟合 |
| `min_data_in_leaf` | 未设 | 10-100 | 叶子最小样本数 |

---

## 🎯 当前运行使用哪个配置？

### **查看方法**

```bash
# 方法1: 查看scripts/一键运行.py的默认配置
grep "default_config" scripts/一键运行.py

# 方法2: 查看最近运行记录
ls -lt mlruns/
```

### **当前情况分析**

根据你的项目，当前主要使用：

1. **workflow_config_top50.yaml** ⭐
   - 这是 `scripts/22_训练Top因子模型.py` 生成的
   - 使用从255个因子中筛选出的Top50强因子
   - 模型参数使用Qlib官方默认值

2. **workflow_config_optimized_csi300.yaml** 🆕
   - 刚由 `scripts/参数优化_改进版.py` 生成
   - 使用优化后的LightGBM参数
   - **推荐试试这个，可能性能更好！**

---

## 💡 如何选择和修改配置？

### **选择策略**

| 场景 | 推荐配置 | 原因 |
|------|---------|------|
| **快速测试** | `workflow_config_lightgbm_Alpha158.yaml` | 标准配置，稳定 |
| **使用强因子** | `workflow_config_top50.yaml` | IC分析筛选的强因子 |
| **追求最佳性能** | `workflow_config_optimized_csi300.yaml` | 参数优化后 |
| **中小盘股票** | `workflow_config_lightgbm_Alpha158_csi500.yaml` | CSI500 |
| **自定义实验** | 复制后修改 | 灵活调整 |

### **修改配置示例**

```bash
# 1. 复制一个配置
cp configs/workflow_config_top50.yaml configs/my_experiment.yaml

# 2. 编辑配置文件
vim configs/my_experiment.yaml

# 3. 修改你想调整的参数：
#    - 市场（csi300 → csi500）
#    - 时间范围（2008-2020 → 2015-2023）
#    - 模型参数（learning_rate, num_leaves等）

# 4. 运行新配置
python scripts/一键运行.py configs/my_experiment.yaml
```

---

## 📊 配置文件对比总结

| 配置文件 | 股票池 | 因子 | 参数来源 | 适合场景 |
|---------|--------|------|---------|---------|
| `lightgbm_Alpha158.yaml` | CSI300 | Alpha158全部（158个） | Qlib官方 | 基线测试 |
| `lightgbm_Alpha158_csi500.yaml` | CSI500 | Alpha158全部 | Qlib官方 | 中小盘 |
| `workflow_config_top50.yaml` | CSI300 | Top50强因子 | IC筛选 | **强因子策略** ⭐ |
| `workflow_config_optimized_csi300.yaml` | CSI300 | Alpha158全部 | 贝叶斯优化 | **最优参数** 🚀 |

---

## 🚀 推荐的完整工作流

```bash
# Step 1: IC分析，筛选强因子
python scripts/20_IC分析.py

# Step 2: 生成Top50因子配置
python scripts/22_训练Top因子模型.py --top 50

# Step 3: 参数优化
python scripts/参数优化_改进版.py --n-iter 30

# Step 4: 对比三种配置的性能

# 4a. 原始配置（Alpha158全部因子 + 默认参数）
python scripts/一键运行.py configs/workflow_config_lightgbm_Alpha158.yaml

# 4b. Top50因子配置（强因子 + 默认参数）
python scripts/一键运行.py configs/workflow_config_top50.yaml

# 4c. 优化参数配置（Alpha158全部因子 + 优化参数）
python scripts/一键运行.py configs/workflow_config_optimized_csi300.yaml

# Step 5: 查看HTML报告对比性能
# 打开 backtest_report.html
```

---

## 🎓 总结

**configs/ 目录的核心作用**：
1. ✅ **配置与代码分离**：修改策略不需要改代码
2. ✅ **可复现性**：完整记录实验配置
3. ✅ **版本管理**：可以保存多个配置对比
4. ✅ **自动化生成**：脚本可以自动生成配置文件

**当前最推荐的配置**：
- **workflow_config_top50.yaml**（使用IC筛选的强因子）
- **workflow_config_optimized_csi300.yaml**（使用优化后的参数）

**建议**：对比这两个配置的回测结果，选择性能更好的作为最终策略！
