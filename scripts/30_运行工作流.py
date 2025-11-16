"""
运行Qlib工作流
基于官方workflow_by_code示例
"""
import qlib
import yaml
import pandas as pd
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord, SigAnaRecord
from qlib.utils import init_instance_by_config
from qlib.contrib.evaluate import risk_analysis

def run_workflow(config_path):
    """运行Qlib工作流"""

    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    # 初始化Qlib
    qlib_init_config = config.get('qlib_init', {})
    qlib.init(**qlib_init_config)

    # 获取任务配置
    task_config = config['task']
    benchmark = config.get('benchmark', 'SH000300')

    print("=" * 50)
    print("开始运行Qlib工作流")
    print("=" * 50)

    # 第一阶段: 训练模型
    with R.start(experiment_name="train_model"):
        # 初始化模型
        print("\n[1/4] 初始化模型...")
        model = init_instance_by_config(task_config['model'])

        # 初始化数据集
        print("[2/4] 加载数据集...")
        dataset = init_instance_by_config(task_config['dataset'])

        # 训练模型
        print("[3/4] 训练模型...")
        model.fit(dataset)

        # 保存模型和获取recorder_id
        R.save_objects(trained_model=model)
        rid = R.get_recorder().id
        print(f"模型训练完成! Recorder ID: {rid}")

    # 第二阶段: 回测和分析
    print("\n[4/4] 执行回测和分析...")

    # 构建回测配置
    port_analysis_config = {
        "executor": {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        },
        "strategy": {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {
                "signal": "<PRED>",
                "topk": 50,
                "n_drop": 5,
            },
        },
        "backtest": {
            "start_time": "2017-01-01",
            "end_time": "2020-08-01",
            "account": 100000000,
            "benchmark": benchmark,
            "exchange_kwargs": {
                "freq": "day",
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        },
    }

    with R.start(experiment_name="backtest_analysis"):
        # 加载训练好的模型
        recorder = R.get_recorder(recorder_id=rid, experiment_name="train_model")
        model = recorder.load_object("trained_model")

        # 获取当前recorder
        ba_recorder = R.get_recorder()
        ba_rid = ba_recorder.id

        # 1. 生成信号记录 (SignalRecord)
        print("  - 生成预测信号...")
        sr = SignalRecord(model, dataset, ba_recorder)
        sr.generate()

        # 2. 生成信号分析 (SigAnaRecord)
        print("  - 分析预测信号质量...")
        sar = SigAnaRecord(ba_recorder)
        sar.generate()

        # 3. 执行回测和投资组合分析 (PortAnaRecord)
        print("  - 执行回测和投资组合分析...")
        par = PortAnaRecord(ba_recorder, port_analysis_config, "day")
        par.generate()

        # 加载分析结果
        pred_df = ba_recorder.load_object("pred.pkl")
        report_normal_df = ba_recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
        positions = ba_recorder.load_object("portfolio_analysis/positions_normal_1day.pkl")
        analysis_df = ba_recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

        # 显示回测结果
        print("\n" + "=" * 70)
        print("回测结果分析")
        print("=" * 70)
        print("\n1. 超额收益分析 (无交易成本):")
        print(analysis_df.loc["excess_return_without_cost"])
        print("\n2. 超额收益分析 (含交易成本):")
        print(analysis_df.loc["excess_return_with_cost"])

        print("\n" + "=" * 70)
        print("工作流完成!")
        print("=" * 70)
        print(f"\n训练记录: {rid}")
        print(f"回测记录: {ba_rid}")
        print(f"\n实验记录保存在: {R.get_uri()}")

        # 自动生成HTML报告
        print("\n" + "=" * 70)
        print("正在生成交互式HTML报告...")
        print("=" * 70)
        try:
            import sys
            from pathlib import Path
            # 添加scripts目录到Python路径,以便导入result模块
            scripts_dir = Path(__file__).parent
            if str(scripts_dir) not in sys.path:
                sys.path.insert(0, str(scripts_dir))

            # 导入result目录下的生成HTML报告模块
            # 由于是中文文件名,使用importlib动态导入
            import importlib.util
            html_module_path = scripts_dir / "result" / "生成HTML报告.py"
            spec = importlib.util.spec_from_file_location("generate_html", html_module_path)
            html_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(html_module)

            html_file = html_module.create_html_report(output_file="backtest_report.html", auto_open=True)
            print(f"\n[OK] HTML报告已自动打开: {html_file}")
        except Exception as e:
            print(f"\n[WARNING] HTML报告生成失败: {e}")
            print("   您可以手动运行: python scripts/result/生成HTML报告.py")

        print("\n其他查看方式:")
        print("  静态PNG图表: python scripts/result/生成图表.py")
        print("  终端结果: python scripts/result/查看结果.py")

if __name__ == "__main__":
    import sys
    from pathlib import Path

    # 默认配置文件（相对于项目根目录）
    default_config = Path(__file__).parent.parent / "configs" / "workflow_config_lightgbm_Alpha158.yaml"
    config_file = str(default_config)

    if len(sys.argv) > 1:
        # 如果提供的是相对路径，相对于项目根目录
        config_arg = sys.argv[1]
        if not Path(config_arg).is_absolute():
            config_file = str(Path(__file__).parent.parent / config_arg)
        else:
            config_file = config_arg

    print(f"使用配置文件: {config_file}\n")
    run_workflow(config_file)
