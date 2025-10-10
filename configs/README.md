# 配置文件说明

本目录包含 Qlib 工作流配置文件，所有配置文件格式参考 Qlib 官方示例。

## 配置文件列表

### 1. workflow_config_lightgbm_Alpha158.yaml
- **市场**: CSI300 (沪深300)
- **基准**: SH000300
- **模型**: LightGBM
- **因子**: Alpha158 (158个技术指标)
- **用途**: 基线策略

### 2. workflow_config_lightgbm_Alpha158_csi500.yaml
- **市场**: CSI500 (中证500)
- **基准**: SH000905
- **模型**: LightGBM
- **因子**: Alpha158
- **用途**: 中小盘股票策略

## 配置文件结构

```yaml
qlib_init:              # Qlib 初始化
    provider_uri: ...   # 数据路径
    region: cn          # 区域

market: csi300          # 市场
benchmark: SH000300     # 基准

data_handler_config:    # 数据配置
    start_time: ...
    end_time: ...
    instruments: ...

task:                   # 任务配置
    model: ...          # 模型
    dataset: ...        # 数据集
    record: ...         # 记录器
```

## 运行配置文件

```bash
# 方式1: 使用 qrun 命令
qrun configs/workflow_config_lightgbm_Alpha158.yaml

# 方式2: 使用脚本
scripts\run_example.bat
```

## 自定义配置

可以复制现有配置文件并修改：

```bash
# 复制配置
cp workflow_config_lightgbm_Alpha158.yaml my_custom_config.yaml

# 修改市场、时间范围、模型参数等
# 然后运行
qrun configs/my_custom_config.yaml
```

## 参考

- [Qlib 配置文档](https://qlib.readthedocs.io/en/latest/component/workflow.html)
- [官方配置示例](https://github.com/microsoft/qlib/tree/main/examples/benchmarks)
