"""
采集任务模块

导入所有任务类以触发@task_register装饰器注册
"""

# 导入所有任务类别以触发装饰器注册
from . import finance  # 财务数据任务
from . import fund     # 基金数据任务
from . import future   # 期货数据任务
from . import hk       # 港股数据任务
from . import index    # 指数数据任务
from . import macro    # 宏观数据任务
from . import option   # 期权数据任务
from . import others   # 其他数据任务
from . import stock    # 股票数据任务

__all__ = [
    "finance",
    "fund",
    "future",
    "hk",
    "index",
    "macro",
    "option",
    "others",
    "stock",
]
