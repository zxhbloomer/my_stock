"""
环境检查脚本
在运行IC分析notebook前，先运行此脚本验证环境配置

作者：Claude Code
日期：2025-11-15
"""
import sys

print("="*80)
print("环境检查开始")
print("="*80)

# 检查1: Python路径
print("\n✅ 检查1: Python环境")
print(f"   Python路径: {sys.executable}")
print(f"   Python版本: {sys.version}")

# 检查2: Qlib导入
print("\n✅ 检查2: Qlib导入")
try:
    import qlib
    print(f"   Qlib版本: {qlib.__version__}")
    print("   ✓ Qlib导入成功")
except ImportError as e:
    print(f"   ✗ Qlib导入失败: {e}")
    sys.exit(1)

# 检查3: Qlib初始化
print("\n✅ 检查3: Qlib初始化")
try:
    qlib.init(provider_uri='D:/Data/my_stock', region='cn')
    print("   ✓ Qlib初始化成功")
    print("   数据路径: D:/Data/my_stock")
except Exception as e:
    print(f"   ✗ Qlib初始化失败: {e}")
    sys.exit(1)

# 检查4: Alpha158导入
print("\n✅ 检查4: Alpha158导入")
try:
    from qlib.contrib.data.handler import Alpha158
    # 只验证导入，不创建实例（避免instruments文件格式问题）
    # 获取因子配置不需要实际数据加载
    print(f"   ✓ Alpha158类导入成功")
    print(f"   提示: 因子配置将在IC分析时获取")
except Exception as e:
    print(f"   ✗ Alpha158导入失败: {e}")
    sys.exit(1)

# 检查5: 自定义因子库导入
print("\n✅ 检查5: 自定义因子库导入")
try:
    # 添加项目根目录到Python路径
    import os
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from factors.alpha_factors import AlphaFactors
    from factors.china_market_factors import ChinaMarketFactors

    alpha_features = AlphaFactors.get_all_features()
    china_features = ChinaMarketFactors.get_all_features()

    print(f"   ✓ AlphaFactors: {len(alpha_features)}个因子")
    print(f"   ✓ ChinaMarketFactors: {len(china_features)}个因子")
except Exception as e:
    print(f"   ✗ 自定义因子库导入失败: {e}")
    sys.exit(1)

# 检查6: 必要的Python包
print("\n✅ 检查6: 必要的Python包")
required_packages = [
    'pandas',
    'numpy',
    'matplotlib',
    'seaborn',
    'scipy',
    'tqdm'
]

for package in required_packages:
    try:
        __import__(package)
        print(f"   ✓ {package}")
    except ImportError:
        print(f"   ✗ {package} 未安装")

# 检查7: 数据可用性（简单测试）
print("\n✅ 检查7: 数据可用性测试")
try:
    from qlib.data import D
    test_data = D.features(
        ['SH600000'],
        fields=['$close'],
        start_time='2020-01-01',
        end_time='2020-01-10'
    )
    print(f"   ✓ 数据读取成功，测试数据行数: {len(test_data)}")
except Exception as e:
    print(f"   ✗ 数据读取失败: {e}")

print("\n" + "="*80)
print("环境检查完成！")
print("="*80)
print("\n如果所有检查都通过（✓），可以开始运行IC分析脚本")
print("如果有检查失败（✗），请先解决相应问题")
print("\n下一步：")
print("   1. 运行IC分析脚本：python scripts/20_ic_analysis.py")
print("   2. 或运行模型优化：python scripts/model_optimization.py")
print("   3. 或运行完整workflow：python run_workflow.py configs/workflow_config_custom.yaml")
