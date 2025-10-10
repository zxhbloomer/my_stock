# 示例代码目录

本目录用于存放 Qlib 官方示例的参考代码。

## 推荐学习路径

### 1. 基础入门
- 查看 Qlib 官方教程: https://github.com/microsoft/qlib/tree/main/examples/tutorial
- 运行 `notebooks/01_workflow_by_code.ipynb`
- 运行 `notebooks/02_data_exploration.ipynb`

### 2. 基准模型
参考 Qlib 官方 benchmarks:
- **LightGBM**: https://github.com/microsoft/qlib/tree/main/examples/benchmarks/LightGBM
- **LSTM**: https://github.com/microsoft/qlib/tree/main/examples/benchmarks/LSTM
- **Transformer**: https://github.com/microsoft/qlib/tree/main/examples/benchmarks/Transformer

### 3. 高级策略
- **TRA (Temporal Routing Adaptor)**: 时序路由适配器
- **HIST**: 图神经网络
- **DDG-DA**: 动态概念漂移适应

## 如何使用官方示例

### 方式1: 直接使用配置文件
```bash
# 已经为您准备好了配置文件
qrun configs/workflow_config_lightgbm_Alpha158.yaml
```

### 方式2: 参考官方代码
```bash
# 克隆官方仓库
git clone https://github.com/microsoft/qlib.git

# 查看示例
cd qlib/examples
```

### 方式3: 在本项目中实现
```bash
# 创建自己的策略目录
mkdir -p examples/my_strategy

# 参考官方代码实现
# 配置文件放在 configs/ 目录
# Jupyter 分析放在 notebooks/ 目录
```

## 目录组织建议

```
examples/
├── README.md (本文件)
├── benchmarks/          # 基准模型参考
│   ├── LightGBM/
│   ├── LSTM/
│   └── ...
└── custom/              # 自定义策略
    ├── my_strategy_1/
    └── my_strategy_2/
```

## 相关资源

- [Qlib 文档](https://qlib.readthedocs.io/)
- [Qlib GitHub](https://github.com/microsoft/qlib)
- [论文列表](https://github.com/microsoft/qlib#related-papers)
