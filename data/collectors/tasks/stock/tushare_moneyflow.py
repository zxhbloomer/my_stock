from datetime import datetime
from typing import Dict, List

import pandas as pd

from ...sources.tushare import TushareTask
from data.common.task_system.task_decorator import task_register


@task_register()
class TushareMoneyflowTask(TushareTask):
    """个股资金流向数据任务

    获取沪深A股票资金流向数据，显示单子大小分类的买卖金额。
    该任务使用Tushare的moneyflow接口获取数据。

    单子大小定义：
    - 小单：< 5万元
    - 中单：5万元 ≤ 金额 < 20万元
    - 大单：20万元 ≤ 金额 < 100万元
    - 特大单：≥ 100万元
    """

    # 1.核心属性
    name = "tushare_moneyflow"
    description = "获取个股资金流向数据"
    table_name = "moneyflow"
    primary_keys = ["ts_code", "trade_date"]
    date_column = "trade_date"
    default_start_date = "20100101"  # moneyflow数据从2010年开始
    smart_lookback_days = 3

    # --- 代码级默认配置 (会被 config.json 覆盖) --- #
    default_concurrent_limit = 5
    default_page_size = 6000

    # 2.自定义索引
    indexes = [
        {"name": "idx_moneyflow_code", "columns": "ts_code"},
        {"name": "idx_moneyflow_date", "columns": "trade_date"},
        {"name": "idx_moneyflow_update_time", "columns": "update_time"},
    ]

    # 3.Tushare特有属性
    api_name = "moneyflow"
    fields = [
        "ts_code",
        "trade_date",
        "buy_elg_amount",
        "sell_elg_amount",
        "buy_lg_amount",
        "sell_lg_amount",
        "buy_md_amount",
        "sell_md_amount",
        "buy_sm_amount",
        "sell_sm_amount",
        "net_mf_amount",
    ]

    # 4.数据类型转换
    transformations = {
        "buy_elg_amount": float,
        "sell_elg_amount": float,
        "buy_lg_amount": float,
        "sell_lg_amount": float,
        "buy_md_amount": float,
        "sell_md_amount": float,
        "buy_sm_amount": float,
        "sell_sm_amount": float,
        "net_mf_amount": float,
    }

    # 5.列名映射（无需映射）
    column_mapping = {}

    # 6.表结构定义
    schema_def = {
        "ts_code": {"type": "VARCHAR(15)", "constraints": "NOT NULL"},
        "trade_date": {"type": "DATE", "constraints": "NOT NULL"},
        "buy_elg_amount": {"type": "FLOAT", "comment": "特大单买入金额(万元)"},
        "sell_elg_amount": {"type": "FLOAT", "comment": "特大单卖出金额(万元)"},
        "buy_lg_amount": {"type": "FLOAT", "comment": "大单买入金额(万元)"},
        "sell_lg_amount": {"type": "FLOAT", "comment": "大单卖出金额(万元)"},
        "buy_md_amount": {"type": "FLOAT", "comment": "中单买入金额(万元)"},
        "sell_md_amount": {"type": "FLOAT", "comment": "中单卖出金额(万元)"},
        "buy_sm_amount": {"type": "FLOAT", "comment": "小单买入金额(万元)"},
        "sell_sm_amount": {"type": "FLOAT", "comment": "小单卖出金额(万元)"},
        "net_mf_amount": {"type": "FLOAT", "comment": "净流入金额(万元)"},
    }

    # 7.数据验证规则
    validations = [
        (lambda df: df["buy_elg_amount"] >= 0, "特大单买入金额不能为负数"),
        (lambda df: df["sell_elg_amount"] >= 0, "特大单卖出金额不能为负数"),
        (lambda df: df["buy_lg_amount"] >= 0, "大单买入金额不能为负数"),
        (lambda df: df["sell_lg_amount"] >= 0, "大单卖出金额不能为负数"),
        (lambda df: df["buy_md_amount"] >= 0, "中单买入金额不能为负数"),
        (lambda df: df["sell_md_amount"] >= 0, "中单卖出金额不能为负数"),
        (lambda df: df["buy_sm_amount"] >= 0, "小单买入金额不能为负数"),
        (lambda df: df["sell_sm_amount"] >= 0, "小单卖出金额不能为负数"),
    ]

    # 8.验证模式配置
    validation_mode = "report"

    # 9. 分批配置
    batch_trade_days_single_code = 240  # 单代码查询时，每个批次的交易日数量 (约1年)
    batch_trade_days_all_codes = 5  # 全市场查询时，每个批次的交易日数量 (1周)

    async def get_batch_list(self, **kwargs) -> List[Dict]:
        """使用 BatchPlanner 生成批处理参数列表

        Args:
            **kwargs: 查询参数，包括start_date、end_date、ts_code等

        Returns:
            List[Dict]: 批处理参数列表
        """
        start_date = kwargs.get("start_date")
        end_date = kwargs.get("end_date")
        ts_code = kwargs.get("ts_code")
        exchange = kwargs.get("exchange", "SSE")

        # 支持基类的全量更新机制：如果没有提供日期范围，使用默认范围
        if not start_date:
            start_date = self.default_start_date
            self.logger.info(f"任务 {self.name}: 未提供 start_date，使用默认起始日期: {start_date}")
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
            self.logger.info(f"任务 {self.name}: 未提供 end_date，使用当前日期: {end_date}")

        self.logger.info(
            f"任务 {self.name}: 使用 BatchPlanner 生成批处理列表，范围: {start_date} 到 {end_date}"
        )

        try:
            # 使用标准的交易日批次生成工具
            from ...sources.tushare.batch_utils import generate_trade_day_batches

            # 根据是否有指定股票代码选择不同的批次大小
            batch_size = (
                self.batch_trade_days_single_code
                if ts_code
                else self.batch_trade_days_all_codes
            )

            batch_list = await generate_trade_day_batches(
                start_date=start_date,
                end_date=end_date,
                batch_size=batch_size,
                ts_code=ts_code,
                exchange=exchange,
                logger=self.logger,
            )

            self.logger.info(f"任务 {self.name}: 成功生成 {len(batch_list)} 个批次")
            return batch_list

        except Exception as e:
            self.logger.error(
                f"任务 {self.name}: 生成批次时出错: {e}", exc_info=True
            )
            return []
