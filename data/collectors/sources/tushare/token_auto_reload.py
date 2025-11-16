"""
Tushare Token 自动重载模块

功能：
- 后台线程定期检查.env文件中的TUSHARE_TOKEN
- 检测到token变化时自动调用 TushareAPI.update_all_tokens()
- 支持长时间运行任务（如10天任务，token每3天更新）

使用方法：
    from data.collectors.sources.tushare.token_auto_reload import start_token_auto_reload

    # 在程序启动时调用一次即可
    start_token_auto_reload()  # 默认每1小时检查一次
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values


logger = logging.getLogger(__name__)


def _token_reload_loop(env_path: str, check_interval: int):
    """后台循环：定期检查并重载token"""
    env_file = Path(env_path).resolve()
    last_token: Optional[str] = None

    logger.info(f"🔍 Token自动检查已启动 (间隔: {check_interval}秒)")

    while True:
        try:
            # 读取.env文件
            if not env_file.exists():
                logger.warning(f"❌ .env文件不存在: {env_file}")
                time.sleep(check_interval)
                continue

            env_values = dotenv_values(str(env_file))
            new_token = env_values.get("TUSHARE_TOKEN")

            if not new_token:
                logger.warning("⚠️ TUSHARE_TOKEN未在.env文件中找到")
                time.sleep(check_interval)
                continue

            # 检查token是否变化
            if new_token != last_token:
                if last_token is None:
                    logger.info(f"📋 初始Token: {new_token[:10]}...{new_token[-6:]}")
                else:
                    logger.info(f"🔄 Token已变化，正在更新...")
                    logger.info(f"   旧: {last_token}")
                    logger.info(f"   新: {new_token}")

                    # 更新环境变量，TushareAPI会动态读取
                    try:
                        import os
                        os.environ["TUSHARE_TOKEN"] = new_token
                        logger.info(f"✅ Token已更新到环境变量")
                    except Exception as e:
                        logger.error(f"❌ 更新Token失败: {e}")

                last_token = new_token

        except Exception as e:
            logger.error(f"❌ Token检查出错: {e}")

        time.sleep(check_interval)


_reload_thread: Optional[threading.Thread] = None


def start_token_auto_reload(env_path: str = ".env", check_interval: int = 3600):
    """
    启动Token自动重载

    Args:
        env_path: .env文件路径
        check_interval: 检查间隔（秒），默认3600秒（1小时）

    示例:
        # 每1小时检查一次（生产环境推荐）
        start_token_auto_reload()

        # 每1分钟检查一次（用于测试）
        start_token_auto_reload(check_interval=60)
    """
    global _reload_thread

    if _reload_thread is not None and _reload_thread.is_alive():
        logger.warning("Token自动重载已经在运行")
        return

    _reload_thread = threading.Thread(
        target=_token_reload_loop,
        args=(env_path, check_interval),
        daemon=True,
        name="TokenAutoReloader"
    )
    _reload_thread.start()

    logger.info(f"✅ Token自动重载线程已启动")
