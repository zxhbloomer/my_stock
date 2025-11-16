from datetime import datetime
from typing import Dict, List

import pandas as pd

from ...sources.tushare import TushareTask
from data.common.task_system.task_decorator import task_register


@task_register()
class TushareIndexDailyTask(TushareTask):
    """指数日线数据任务

    获取指数的日线交易数据，包括开盘价、收盘价、最高价、最低价、成交量、成交额等信息。
    该任务使用Tushare的index_daily接口获取数据。
    """

    # 1.核心属性
    name = "tushare_index_daily"
    description = "获取A股指数日线行情数据"
    table_name = "index_daily"
    primary_keys = ["ts_code", "trade_date"]
    date_column = "trade_date"  # 日期列名，用于确认最新数据日期
    default_start_date = "19901219"  # A股最早交易日
    smart_lookback_days = 3  # 智能增量模式下，回看3天

    # --- 代码级默认配置 (会被 config.json 覆盖) --- #
    default_concurrent_limit = 5  # 默认并发限制
    default_page_size = 6000

    # 2.自定义索引
    indexes = [
        {"name": "idx_index_daily_code", "columns": "ts_code"},
        {"name": "idx_index_daily_date", "columns": "trade_date"},
        {"name": "idx_index_daily_update_time", "columns": "update_time"},
    ]

    # 3.Tushare特有属性
    api_name = "index_daily"
    fields = [
        "ts_code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "change",
        "pct_chg",
        "vol",
        "amount",
    ]

    # 4.数据类型转换
    transformations = {
        "open": float,
        "high": float,
        "low": float,
        "close": float,
        "pre_close": float,
        "change": float,
        "pct_chg": float,
        "vol": float,  # 原始字段名
        "amount": float,
    }

    # 5.列名映射
    column_mapping = {"vol": "volume"}  # 将vol映射为volume

    # 6.表结构定义
    schema_def = {
        "ts_code": {"type": "VARCHAR(15)", "constraints": "NOT NULL"},
        "trade_date": {"type": "DATE", "constraints": "NOT NULL"},
        "open": {"type": "FLOAT"},
        "high": {"type": "FLOAT"},
        "low": {"type": "FLOAT"},
        "close": {"type": "FLOAT"},
        "pre_close": {"type": "FLOAT"},
        "change": {"type": "FLOAT"},
        "pct_chg": {"type": "FLOAT"},
        "volume": {"type": "FLOAT"},  # 目标字段名
        "amount": {"type": "FLOAT"},
    }

    # 7.数据验证规则 (使用目标字段名 volume) - 真正生效的验证机制
    validations = [
        (lambda df: df["close"] > 0, "收盘价必须为正数"),
        (lambda df: df["open"] > 0, "开盘价必须为正数"),
        (lambda df: df["high"] > 0, "最高价必须为正数"),
        (lambda df: df["low"] > 0, "最低价必须为正数"),
        (lambda df: df["volume"] >= 0, "成交量不能为负数"),
        (lambda df: df["amount"] >= 0, "成交额不能为负数"),
        (lambda df: df["high"] >= df["low"], "最高价不能低于最低价"),
        (lambda df: df["high"] >= df["open"], "最高价不能低于开盘价"),
        (lambda df: df["high"] >= df["close"], "最高价不能低于收盘价"),
        (lambda df: df["low"] <= df["open"], "最低价不能高于开盘价"),
        (lambda df: df["low"] <= df["close"], "最低价不能高于收盘价"),
    ]

    # 8.验证模式配置 - 使用报告模式记录验证结果
    validation_mode = "report"  # 报告验证结果但保留所有数据

    # 9. 分批配置
    batch_trade_days_single_code = 240  # 单代码查询时，每个批次的交易日数量 (约1年)

    # 10. 默认指数代码列表(常用指数)
    default_index_codes = [
        "000300.SH",  # 沪深300
        "000905.SH",  # 中证500
        "000001.SH",  # 上证综指
        "399001.SZ",  # 深证成指
        "399006.SZ",  # 创业板指
        "000016.SH",  # 上证50
        "000852.SH",  # 中证1000
    ]

    async def get_batch_list(self, **kwargs) -> List[Dict]:
        """生成批处理参数列表

        注意: Tushare index_daily API 必须提供 ts_code 参数，不支持按日期查询全市场。
        如果用户未指定 ts_code，则使用默认的常用指数列表。

        Args:
            **kwargs: 查询参数，包括start_date、end_date、ts_code等

        Returns:
            List[Dict]: 批处理参数列表
        """
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        ts_code = kwargs.get("ts_code")

        # 支持基类的全量更新机制：如果没有提供日期范围，使用默认范围
        if not start_date:
            start_date = self.default_start_date
            self.logger.info(f"任务 {self.name}: 未提供 start_date，使用默认起始日期: {start_date}")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
            self.logger.info(f"任务 {self.name}: 未提供 end_date，使用当前日期: {end_date}")

        # Tushare index_daily API 要求必须提供 ts_code
        # 如果用户未指定，使用默认指数列表
        if not ts_code:
            index_codes = self.default_index_codes
            self.logger.info(
                f"任务 {self.name}: 未指定 ts_code，将获取默认指数列表: {', '.join(index_codes)}"
            )
        else:
            # 支持逗号分隔的多个指数代码
            index_codes = [code.strip() for code in ts_code.split(",")]
            self.logger.info(
                f"任务 {self.name}: 将获取指定指数: {', '.join(index_codes)}"
            )

        self.logger.info(
            f"任务 {self.name}: 生成批处理列表，日期范围: {start_date} 到 {end_date}"
        )

        try:
            # 使用标准的交易日批次生成工具
            from ...sources.tushare.batch_utils import generate_trade_day_batches

            batch_list = []

            # 为每个指数代码生成批次
            for code in index_codes:
                code_batches = await generate_trade_day_batches(
                    start_date=start_date,
                    end_date=end_date,
                    batch_size=self.batch_trade_days_single_code,
                    ts_code=code,
                    exchange="SSE" if code.endswith(".SH") else "SZSE",
                    logger=self.logger,
                )
                batch_list.extend(code_batches)
                self.logger.info(
                    f"任务 {self.name}: 为指数 {code} 生成 {len(code_batches)} 个批次"
                )

            self.logger.info(f"任务 {self.name}: 总共生成 {len(batch_list)} 个批次")
            return batch_list

        except Exception as e:
            self.logger.error(
                f"任务 {self.name}: 生成批次时出错: {e}", exc_info=True
            )
            return []


