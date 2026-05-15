"""
数据模块
包含数据采集、处理、加载器
"""

__all__ = []

try:
    from .collectors import BaseCollector, BaseNormalize, BaseRun
except ModuleNotFoundError as exc:
    if exc.name != "data.collectors":
        raise
else:
    __all__ += ["BaseCollector", "BaseNormalize", "BaseRun"]

try:
    from .processors import DataNormalizer, DataValidator
except ModuleNotFoundError as exc:
    if exc.name != "data.processors":
        raise
else:
    __all__ += ["DataNormalizer", "DataValidator"]
