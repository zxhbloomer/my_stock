#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
导入测试脚本
验证所有模块的导入是否正常
"""
import sys
import io
from pathlib import Path

# 设置标准输出为UTF-8编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_common_imports():
    """测试common模块导入"""
    try:
        from data.common import get_logger
        from data.common.logging_utils import get_logger as get_logger2
        from data.common.db_manager import DBManager
        from data.common.task_system.base_task import BaseTask
        from data.common.task_system.task_decorator import task_register
        from data.common.task_system.task_factory import UnifiedTaskFactory
        from data.common.constants import UpdateTypes, ApiParams
        from data.common.config import Config
        print("✓ common模块导入成功")
        return True
    except Exception as e:
        print(f"✗ common模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_collectors_base_imports():
    """测试collectors基础模块导入"""
    try:
        from data.collectors.base import FetcherTask
        from data.collectors.base.fetcher_task import FetcherTask as FT
        from data.collectors.exceptions import TushareAuthError, FetcherError
        print("✓ collectors.base模块导入成功")
        return True
    except Exception as e:
        print(f"✗ collectors.base模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_collectors_tushare_imports():
    """测试collectors.tushare模块导入"""
    try:
        from data.collectors.sources.tushare import TushareTask, TushareAPI
        from data.collectors.sources.tushare.tushare_task import TushareTask as TT
        from data.collectors.sources.tushare.tushare_api import TushareAPI as TA
        from data.collectors.sources.tushare.tushare_data_transformer import TushareDataTransformer
        print("✓ collectors.tushare模块导入成功")
        return True
    except Exception as e:
        print(f"✗ collectors.tushare模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_collectors_tasks_imports():
    """测试collectors任务模块导入"""
    try:
        from data.collectors.tasks.stock import (
            TushareStockBasicTask,
            TushareStockDailyTask,
            TushareStockAdjFactorTask
        )
        print("✓ collectors.tasks模块导入成功")
        return True
    except Exception as e:
        print(f"✗ collectors.tasks模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_processors_base_imports():
    """测试processors基础模块导入"""
    try:
        from data.processors.base import ProcessorTask, BlockProcessorMixin
        from data.processors.base.processor_task import ProcessorTask as PT
        from data.processors.base.block_processor import BlockProcessorMixin as BPM
        print("✓ processors.base模块导入成功")
        return True
    except Exception as e:
        print(f"✗ processors.base模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_processors_operations_imports():
    """测试processors.operations模块导入"""
    try:
        from data.processors.operations.base_operation import Operation, OperationPipeline
        from data.processors.operations.missing_data import FillNAOperation, DropNAOperation
        from data.processors.operations.technical_indicators import (
            MovingAverageOperation,
            RSIOperation,
            MACDOperation
        )
        print("✓ processors.operations模块导入成功")
        return True
    except Exception as e:
        print(f"✗ processors.operations模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_processors_utils_imports():
    """测试processors.utils模块导入"""
    try:
        from data.processors.utils.query_builder import QueryBuilder
        from data.processors.utils.data_validator import DataValidator
        print("✓ processors.utils模块导入成功")
        return True
    except Exception as e:
        print(f"✗ processors.utils模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_processors_tasks_imports():
    """测试processors.tasks模块导入"""
    try:
        from data.processors.tasks.stock import (
            StockAdjustedPriceTask,
            StockAdjdailyProcessorTask
        )
        print("✓ processors.tasks模块导入成功")
        return True
    except Exception as e:
        print(f"✗ processors.tasks模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("开始导入测试")
    print("=" * 60)
    print()

    tests = [
        ("Common模块", test_common_imports),
        ("Collectors基础模块", test_collectors_base_imports),
        ("Collectors Tushare模块", test_collectors_tushare_imports),
        ("Collectors任务模块", test_collectors_tasks_imports),
        ("Processors基础模块", test_processors_base_imports),
        ("Processors操作模块", test_processors_operations_imports),
        ("Processors工具模块", test_processors_utils_imports),
        ("Processors任务模块", test_processors_tasks_imports),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n测试 {name}:")
        result = test_func()
        results.append((name, result))

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    failed = len(results) - passed

    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {name}")

    print()
    print(f"总计: {len(results)} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {failed} 个")

    if failed == 0:
        print("\n✅ 所有导入测试通过！")
        return 0
    else:
        print(f"\n❌ {failed} 个测试失败，请检查导入路径")
        return 1

if __name__ == "__main__":
    sys.exit(main())
