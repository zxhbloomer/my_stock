"""
采集器异常类定义
"""


class FetcherError(Exception):
    """采集器基础异常"""
    pass


class TushareAuthError(FetcherError):
    """Tushare认证错误"""
    pass


class TushareAPIError(FetcherError):
    """Tushare API调用错误"""
    pass


class RateLimitError(FetcherError):
    """速率限制错误"""
    pass


class DataFetchError(FetcherError):
    """数据获取错误"""
    pass
