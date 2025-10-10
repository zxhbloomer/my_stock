# My Stock - 基于 Qlib 的A股量化投资项目

基于 Microsoft Qlib 框架的中国A股量化投资研究项目。

## 项目结构

```
my_stock/
├── examples/                    # Qlib 官方示例参考
│   ├── benchmarks/             # 基准模型（参考 qlib/examples/benchmarks）
│   └── tutorial/               # 教程示例
├── mlruns/                      # MLflow 实验记录（自动生成）
├── notebooks/                   # Jupyter Notebook 分析
├── scripts/                     # 数据脚本
└── configs/                     # YAML 配置文件
```

## 快速开始

### 第一步：创建 Conda 环境

```bash
# 使用脚本（推荐）
scripts\setup_env.bat

# 或手动创建
conda env create -f environment.yml
```

### 第二步：激活环境

```bash
conda activate mystock
```

### 第三步：下载数据

```bash
# 使用脚本（推荐）
scripts\download_data.bat

# 或手动下载
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn
```

### 第四步：运行示例

```bash
# 方式1: 使用配置文件
qrun configs\workflow_config_lightgbm_Alpha158.yaml

# 方式2: 使用一键脚本
scripts\activate_and_run.bat

# 方式3: 使用 Jupyter Notebook
jupyter notebook notebooks\01_workflow_by_code.ipynb
```

### 第五步：查看结果

```bash
mlflow ui
# 访问 http://localhost:5000
```

**详细说明请查看**: [启动指南.md](./启动指南.md)

## 配置说明

所有策略配置文件位于 `configs/` 目录，参考 Qlib 官方格式：

- `workflow_config_lightgbm_Alpha158.yaml` - LightGBM + Alpha158 因子
- `workflow_config_lightgbm_Alpha360.yaml` - LightGBM + Alpha360 因子

## 参考资料

- [Qlib 官方文档](https://qlib.readthedocs.io/)
- [Qlib GitHub](https://github.com/microsoft/qlib)
- [Examples 目录](https://github.com/microsoft/qlib/tree/main/examples)
