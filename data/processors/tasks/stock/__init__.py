"""
股票处理任务模块
"""
from .stock_adjusted_price import StockAdjustedPriceTask
from .stock_adjdaily_processor import StockAdjdailyProcessorTask

__all__ = [
    'StockAdjustedPriceTask',
    'StockAdjdailyProcessorTask',
]
