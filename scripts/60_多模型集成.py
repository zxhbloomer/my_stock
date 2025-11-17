"""
多模型集成训练脚本
基于Qlib官方最佳实践，训练多个模型并集成预测

使用方法:
    python scripts/60_多模型集成.py --config configs/workflow_config_top50.yaml

作者: 基于Qlib官方文档
日期: 2025-11-17
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import qlib
import yaml
import pandas as pd
from qlib.model.trainer import TrainerR
from qlib.contrib.model.gbdt import LGBModel, XGBModel
from qlib.utils import init_instance_by_config
from qlib.workflow import R


def train_ensemble_models(config_path):
    """训练多个模型并集成"""

    # 读取配置
    with open(config_path, 'r', encoding='utf-8') as f:
        base_config = yaml.safe_load(f)

    dataset_config = base_config['task']['dataset']

    # 定义3个不同的模型任务
    tasks = [
        {
            "model": {
                "class": "LGBModel",
                "module_path": "qlib.contrib.model.gbdt",
                "kwargs": {
                    "loss": "mse",
                    "learning_rate": 0.05,
                    "num_leaves": 128,
                    "max_depth": 8,
                    "num_threads": 20
                }
            },
            "dataset": dataset_config
        },
        {
            "model": {
                "class": "LGBModel",
                "module_path": "qlib.contrib.model.gbdt",
                "kwargs": {
                    "loss": "mse",
                    "learning_rate": 0.1,
                    "num_leaves": 210,
                    "max_depth": 10,
                    "num_threads": 20
                }
            },
            "dataset": dataset_config
        },
        {
            "model": {
                "class": "XGBModel",
                "module_path": "qlib.contrib.model.gbdt",
                "kwargs": {
                    "loss": "mse",
                    "eta": 0.05,
                    "max_depth": 8,
                    "n_jobs": 20
                }
            },
            "dataset": dataset_config
        }
    ]

    # 训练所有模型
    print("="*80)
    print("开始训练集成模型")
    print("="*80)

    trainer = TrainerR(
        experiment_name="ensemble_models",
        call_in_subproc=False  # 在主进程训练
    )

    recorders = trainer.train(tasks)
    print(f"\n✅ 成功训练 {len(recorders)} 个模型")

    # 初始化数据集
    dataset = init_instance_by_config(dataset_config)

    # 生成集成预测
    print("\n生成集成预测...")
    ensemble_pred = pd.DataFrame()

    for i, recorder in enumerate(recorders, 1):
        model = recorder.load_object("model.pkl")
        pred = model.predict(dataset, segment="test")
        ensemble_pred[f'model_{i}'] = pred
        print(f"  模型{i}预测完成")

    # 平均集成
    final_pred = ensemble_pred.mean(axis=1)

    # 保存集成结果
    with R.start(experiment_name="ensemble_prediction"):
        R.save_objects(**{
            "ensemble_pred.pkl": final_pred,
            "individual_preds.pkl": ensemble_pred
        })

        # 计算IC
        label = dataset.prepare("test", col_set="label")
        merged = pd.concat([label, final_pred], axis=1, sort=True)
        merged.columns = ['label', 'score']

        ic_series = merged.groupby(level=0).apply(
            lambda x: x['label'].corr(x['score'])
        )

        ic_mean = ic_series.mean()
        ic_std = ic_series.std()
        ic_ir = ic_mean / ic_std if ic_std > 0 else 0

        R.log_metrics(
            ensemble_ic_mean=ic_mean,
            ensemble_ic_std=ic_std,
            ensemble_ic_ir=ic_ir
        )

        rid = R.get_recorder().id

    print("\n="*80)
    print("集成模型训练完成")
    print("="*80)
    print(f"\n集成模型IC指标:")
    print(f"  IC均值: {ic_mean:.4f}")
    print(f"  IC标准差: {ic_std:.4f}")
    print(f"  IC_IR: {ic_ir:.4f}")
    print(f"\n📊 MLflow Recorder ID: {rid}")
    print(f"\n下一步:")
    print(f"  使用集成预测运行回测: python scripts/30_运行工作流.py")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='多模型集成训练')
    parser.add_argument('--config', type=str, required=True, help='配置文件路径')

    args = parser.parse_args()

    # 初始化Qlib
    print("初始化Qlib...")
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')
    print("[OK] Qlib初始化完成\n")

    # 训练集成模型
    train_ensemble_models(args.config)
