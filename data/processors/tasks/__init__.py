"""
处理任务模块

导入所有任务类以触发@task_register装饰器注册
"""

# 导入所有股票处理任务以触发装饰器注册
from .stock import (
    StockAdjustedPriceTask,
    StockAdjdailyProcessorTask,
)

__all__ = [
    "StockAdjustedPriceTask",
    "StockAdjdailyProcessorTask",
]
