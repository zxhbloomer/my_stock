# Scripts 目录说明

本目录包含项目的所有工具脚本，按功能分类。

## 📂 目录结构

```
scripts/
├── result/                    # 📊 结果查看和分析工具
│   ├── README.md              # 使用说明
│   ├── 查看结果.py            # 终端查看回测结果
│   ├── 生成图表.py            # 生成PNG静态图表
│   ├── 生成HTML报告.py        # 生成交互式HTML报告
│   └── 检查数据范围.py        # 检查Qlib数据时间范围
│
├── run/                       # 🖥️ GUI运行工具
│   └── run_gui.py             # 图形界面启动器
│
├── 00_Tushare转Qlib.py       # 📥 Tushare数据转Qlib格式
├── 10_检查环境.py             # ✅ 环境检查工具
├── 20_IC分析.py               # 📈 因子IC分析（从255个因子筛选强因子）
├── 21_使用IC结果.py           # 📊 查看和使用IC分析结果
├── 22_训练Top因子模型.py      # 🚀 用Top因子生成配置并训练
├── 一键运行.py                # ⚡ 完整工作流执行器（训练+回测+报告）
└── model_optimization.py      # 🔧 模型参数优化工具
```

## 🔢 文件编号规则

- **00-09**：数据准备和环境检查
- **10-19**：环境和工具检查
- **20-29**：因子分析和筛选
- **30+**：（预留）其他功能

## 📋 核心工作流程

### **标准流程**（推荐）

```bash
# 步骤1: 检查环境
python scripts/10_检查环境.py

# 步骤2: IC分析（筛选强因子）
python scripts/20_IC分析.py

# 步骤3: 生成Top因子配置
python scripts/22_训练Top因子模型.py --top 50

# 步骤4: 执行完整工作流（训练+回测+报告）
python scripts/一键运行.py configs/workflow_config_top50.yaml
```

### **快速查看结果**

```bash
# 终端查看
python scripts/result/查看结果.py

# 生成PNG图表
python scripts/result/生成图表.py

# 生成HTML报告（推荐）
python scripts/result/生成HTML报告.py
```

## 📖 详细说明

### **数据准备脚本**

#### `00_Tushare转Qlib.py`
**功能**：将Tushare Pro数据转换为Qlib格式
```bash
python scripts/00_Tushare转Qlib.py
```
**输出**：`D:/Data/my_stock/` 目录下的Qlib数据

---

### **环境检查脚本**

#### `10_检查环境.py`
**功能**：检查Qlib、数据、环境是否正常
```bash
python scripts/10_检查环境.py
```
**检查项**：
- Qlib是否安装
- 数据路径是否存在
- 数据时间范围
- Python环境和依赖

---

### **因子分析脚本**

#### `20_IC分析.py`
**功能**：计算255个因子的IC值，筛选强因子
```bash
python scripts/20_IC分析.py
```
**参数**：
- `--pool`：股票池（csi300/csi500，默认csi300）
- `--start`：开始时间（默认2017-01-01）
- `--end`：结束时间（默认2020-12-31）
- `--threshold`：IC阈值（默认0.01）

**输出**：
- MLflow实验记录：`mlruns/ic_analysis`
- IC排序结果：保存在实验中

**示例**：
```bash
# 在CSI500上分析
python scripts/20_IC分析.py --pool csi500

# 自定义IC阈值
python scripts/20_IC分析.py --threshold 0.02
```

---

#### `21_使用IC结果.py`
**功能**：查看和导出IC分析结果
```bash
python scripts/21_使用IC结果.py
```
**输出**：
- 显示Top因子列表
- 导出CSV文件（可选）

---

#### `22_训练Top因子模型.py`
**功能**：根据IC分析结果生成配置文件
```bash
python scripts/22_训练Top因子模型.py --top 50
```
**参数**：
- `--top`：选择Top N个因子（默认50）
- `--output`：输出配置文件路径

**输出**：
- `configs/workflow_config_top50.yaml`（或自定义）

---

### **核心执行脚本**

#### `一键运行.py`
**功能**：执行完整工作流（训练+回测+自动生成报告）
```bash
# 使用默认配置
python scripts/一键运行.py

# 使用指定配置
python scripts/一键运行.py configs/workflow_config_top50.yaml
```

**执行流程**：
1. 读取配置文件
2. 初始化Qlib
3. 训练模型（2008-2014）
4. 验证模型（2015-2016）
5. 回测分析（2017-2020）
6. 自动生成HTML报告并打开浏览器

**输出**：
- MLflow实验记录：`mlruns/train_model` 和 `mlruns/backtest_analysis`
- HTML报告：`backtest_report.html`

---

### **优化工具**

#### `model_optimization.py`
**功能**：LightGBM参数优化
```bash
python scripts/model_optimization.py
```
**功能**：
- 网格搜索最佳参数
- 交叉验证
- 生成优化报告

---

## 💡 使用建议

### **首次使用**
1. 运行 `10_检查环境.py` 确保环境正常
2. 运行 `20_IC分析.py` 分析因子质量
3. 运行 `22_训练Top因子模型.py` 生成配置
4. 运行 `一键运行.py` 执行完整流程

### **日常使用**
- 直接运行 `一键运行.py` 进行回测
- 使用 `result/` 目录下的工具查看结果

### **参数调优**
1. 修改 `configs/*.yaml` 配置文件
2. 运行 `一键运行.py` 测试效果
3. 使用 `model_optimization.py` 优化参数

## 🔧 注意事项

1. **中文文件名**：所有脚本使用中文命名，便于识别，但不能被其他模块import
2. **独立运行**：每个脚本都可以独立运行
3. **数据依赖**：确保 `D:/Data/my_stock/` 有数据
4. **环境依赖**：需要激活 `mystock` conda环境

## 📊 输出文件位置

- **MLflow实验**：`mlruns/`
- **配置文件**：`configs/`
- **HTML报告**：项目根目录 `backtest_report.html`
- **PNG图表**：项目根目录 `backtest_analysis.png`
