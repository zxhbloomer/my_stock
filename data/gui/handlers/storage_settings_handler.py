"""
存储设置UI事件处理器

负责为"存储设置"标签页提供UI更新和数据提取的辅助函数。
"""
import os
import tkinter as tk
from tkinter import messagebox
from typing import Dict, Any

from ..services import configuration_service as storage_logic

# This module no longer sends requests directly to the controller.
# It provides helper functions for the main_window to call.
# The main_window is responsible for dispatching requests.

def update_storage_settings_display(widgets: Dict[str, tk.Widget], settings: Dict[str, Any]):
    """更新存储设置显示 - 由于配置从.env读取,这里只更新状态信息。"""
    try:
        db_config = settings.get("database", {})
        api_config = settings.get("api", {})
        db_url = db_config.get("url", "")
        tushare_token = api_config.get("tushare_token", "")

        # 更新状态信息
        if db_url and tushare_token:
            _update_status(widgets, "✓ 配置已从 .env 文件加载", "green")
        elif not db_url:
            _update_status(widgets, "⚠ 数据库连接URL未配置,请检查 .env 文件中的 DATABASE_URL", "red")
        elif not tushare_token:
            _update_status(widgets, "⚠ Tushare Token未配置,请检查 .env 文件中的 TUSHARE_TOKEN", "red")

    except Exception as e:
        messagebox.showerror("UI 更新错误", f"更新设置界面时发生意外错误: {e}")
        _update_status(widgets, f"UI 更新错误: {e}", "red")

async def handle_test_db_connection(widgets: Dict[str, tk.Widget]):
    """处理测试数据库连接按钮点击事件。"""
    # 从环境变量获取数据库URL
    db_url = os.environ.get("DATABASE_URL")

    info_label = widgets.get("settings_info_label")
    if info_label:
        info_label.config(text="正在测试数据库连接...", foreground="blue")

    result = await storage_logic.test_database_connection(db_url)

    if result["status"] == "success":
        messagebox.showinfo("连接成功", result["message"])
        if info_label:
            info_label.config(text="✓ " + result["message"], foreground="green")
    else:
        messagebox.showerror("连接失败", result["message"])
        if info_label:
            info_label.config(text="✗ " + result["message"], foreground="red")

def _update_status(widgets: Dict[str, tk.Widget], message: str, color: str = "black"):
    """更新状态栏或信息标签。"""
    statusbar = widgets.get("settings_info_label")
    if statusbar:
        statusbar.config(text=message, foreground=color) 