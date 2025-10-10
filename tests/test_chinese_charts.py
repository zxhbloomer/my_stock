"""
测试中文图表模块
验证所有中文图表函数是否正常工作
"""
import sys
import io

# 设置标准输出为UTF-8编码 (解决Windows GBK编码问题)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import qlib
import pandas as pd
from pathlib import Path
import yaml
from qlib.workflow import R

# 导入中文图表模块 (从utils包)
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils.chinese_charts import (
    score_ic_graph_cn,
    model_performance_graph_cn,
    report_graph_cn,
    risk_analysis_graph_cn,
    show_all_charts_cn
)


def test_chinese_charts():
    """测试中文图表功能"""
    print("=" * 80)
    print("Qlib中文图表模块测试")
    print("=" * 80)

    # 1. 初始化Qlib
    print("\n[1/5] 初始化Qlib...")
    mlflow_path = Path("mlruns").resolve()
    mlflow_uri = "file:///" + str(mlflow_path).replace("\\", "/")

    qlib.init(
        provider_uri="~/.qlib/qlib_data/cn_data",
        region="cn",
        exp_manager={
            "class": "MLflowExpManager",
            "module_path": "qlib.workflow.expm",
            "kwargs": {
                "uri": mlflow_uri,
                "default_exp_name": "Experiment",
            },
        }
    )
    print("[OK] Qlib初始化成功")

    # 2. 查找最新回测
    print("\n[2/5] 查找最新回测记录...")
    mlruns_dir = Path("mlruns")
    recorder_id, exp_name = None, None

    for exp_dir in mlruns_dir.iterdir():
        if not exp_dir.is_dir():
            continue
        meta_file = exp_dir / "meta.yaml"
        if not meta_file.exists():
            continue

        with open(meta_file, 'r', encoding='utf-8') as f:
            meta = yaml.safe_load(f)

        if meta.get('name') == 'backtest_analysis':
            run_dirs = [d for d in exp_dir.iterdir() if d.is_dir()]
            if run_dirs:
                latest_run = max(run_dirs, key=lambda x: x.stat().st_mtime)
                recorder_id = latest_run.name
                exp_name = "backtest_analysis"
                break

    if not recorder_id:
        print("[ERROR] 未找到回测记录")
        return False

    print(f"[OK] 找到回测记录: {recorder_id}")

    # 3. 加载数据
    print("\n[3/5] 加载回测数据...")
    recorder = R.get_recorder(recorder_id=recorder_id, experiment_name=exp_name)
    pred_df = recorder.load_object("pred.pkl")
    label_df = recorder.load_object("label.pkl")
    report_df = recorder.load_object("portfolio_analysis/report_normal_1day.pkl")
    analysis_df = recorder.load_object("portfolio_analysis/port_analysis_1day.pkl")

    print(f"[OK] 数据加载成功")
    print(f"  - 预测记录: {len(pred_df):,}条")
    print(f"  - 交易日数: {len(report_df)}天")

    # 4. 准备数据
    print("\n[4/5] 准备图表数据...")
    pred_label = pd.concat([label_df, pred_df], axis=1, sort=True).reindex(label_df.index)
    if isinstance(pred_label.columns, pd.MultiIndex):
        pred_label.columns = ['label', 'score']
    else:
        pred_label.columns = ['label', 'score']
    print("[OK] 数据准备完成")

    # 5. 测试图表生成 (不显示，仅验证能否生成)
    print("\n[5/5] 测试图表生成...")

    try:
        # 测试IC图表
        print("  - 测试 score_ic_graph_cn()...", end=" ")
        fig1 = score_ic_graph_cn(pred_label, show_notebook=False)
        print("[OK]")

        # 测试模型性能图表
        print("  - 测试 model_performance_graph_cn()...", end=" ")
        fig2 = model_performance_graph_cn(pred_label, show_notebook=False)
        print("[OK]")

        # 测试投资组合图表
        print("  - 测试 report_graph_cn()...", end=" ")
        fig3 = report_graph_cn(report_df, show_notebook=False)
        print("[OK]")

        # 测试风险分析图表
        print("  - 测试 risk_analysis_graph_cn()...", end=" ")
        fig4 = risk_analysis_graph_cn(analysis_df, report_df, show_notebook=False)
        print("[OK]")

        print("\n" + "=" * 80)
        print("[SUCCESS] 所有中文图表测试通过！")
        print("=" * 80)
        print("\n使用说明:")
        print("1. 启动Jupyter Notebook")
        print("2. 打开 notebooks/backtest_analysis_cn.ipynb")
        print("3. 运行所有cells查看中文图表")
        print("\n或在Python脚本中:")
        print("  from utils.chinese_charts import score_ic_graph_cn")
        print("  # 或者: from utils import score_ic_graph_cn")
        print("  score_ic_graph_cn(pred_label)  # 显示中文IC图表")

        return True

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_chinese_charts()
    exit(0 if success else 1)
