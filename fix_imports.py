#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量修复导入路径脚本
将alphaHome的导入路径修改为my_stock的路径
"""
import os
import re
from pathlib import Path

def fix_imports_in_file(file_path):
    """修复单个文件的导入路径"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        original_content = content

        # 修复规则列表
        replacements = [
            # alphahome绝对导入 → data相对导入
            (r'from alphahome\.fetchers\.base\.fetcher_task import', 'from data.collectors.base.fetcher_task import'),
            (r'from alphahome\.fetchers\.', 'from data.collectors.'),
            (r'from alphahome\.processors\.', 'from data.processors.'),
            (r'from alphahome\.common\.', 'from data.common.'),

            # 三层相对导入 → 绝对导入
            (r'from \.\.\.common\.task_system\.base_task import', 'from data.common.task_system.base_task import'),
            (r'from \.\.\.common\.task_system import', 'from data.common.task_system import'),
            (r'from \.\.\.common\.logging_utils import', 'from data.common.logging_utils import'),
            (r'from \.\.\.common\.db_manager import', 'from data.common.db_manager import'),
            (r'from \.\.\.common\.constants import', 'from data.common.constants import'),
            (r'from \.\.\.common\.', 'from data.common.'),

            # 两层相对导入 → 绝对导入 (collectors)
            (r'from \.\.sources\.tushare\.batch_utils import', 'from data.collectors.sources.tushare.batch_utils import'),
            (r'from \.\.sources\.tushare import', 'from data.collectors.sources.tushare import'),
            (r'from \.\.base\.fetcher_task import', 'from data.collectors.base.fetcher_task import'),

            # 两层相对导入 → 绝对导入 (processors)
            (r'from \.\.common\.task_system import', 'from data.common.task_system import'),
            (r'from \.\.common\.', 'from data.common.'),

            # 一层相对导入 → 绝对导入 (collectors/sources/tushare)
            (r'from \.tushare_api import', 'from data.collectors.sources.tushare.tushare_api import'),
            (r'from \.tushare_data_transformer import', 'from data.collectors.sources.tushare.tushare_data_transformer import'),
            (r'from \.tushare_batch_processor import', 'from data.collectors.sources.tushare.tushare_batch_processor import'),
            (r'from \.batch_utils import', 'from data.collectors.sources.tushare.batch_utils import'),

            # 一层相对导入 → 绝对导入 (processors/base)
            (r'from \.base\.block_processor import', 'from data.processors.base.block_processor import'),
            (r'from \.processor_task import', 'from data.processors.base.processor_task import'),

            # 一层相对导入 → 绝对导入 (processors/operations)
            (r'from \.base_operation import', 'from data.processors.operations.base_operation import'),

            # 特殊情况：processor_task.py中的导入
            (r'from \.\.processor_task import', 'from data.processors.base.processor_task import'),
        ]

        # 执行替换
        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)

        # 如果内容有变化，写回文件
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "已修复"
        else:
            return False, "无需修复"

    except Exception as e:
        return False, f"错误: {str(e)}"

def main():
    """主函数"""
    base_path = Path(__file__).parent / 'data'

    # 统计
    total_files = 0
    fixed_files = 0

    print("=" * 60)
    print("开始批量修复导入路径")
    print("=" * 60)

    # 遍历所有Python文件
    for py_file in base_path.rglob('*.py'):
        total_files += 1
        changed, message = fix_imports_in_file(py_file)

        if changed:
            fixed_files += 1
            print(f"✓ {py_file.relative_to(base_path)}: {message}")
        else:
            print(f"  {py_file.relative_to(base_path)}: {message}")

    print("\n" + "=" * 60)
    print(f"修复完成！")
    print(f"总文件数: {total_files}")
    print(f"已修复: {fixed_files}")
    print(f"无需修复: {total_files - fixed_files}")
    print("=" * 60)

if __name__ == "__main__":
    main()
