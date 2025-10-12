"""
状态栏事件处理器

负责更新状态栏的显示内容,包括任务状态、进度、速度和时间统计。
"""
import tkinter as tk
from typing import Dict, Any


def format_time(seconds: float) -> str:
    """
    格式化时间为 MM:SS 格式

    Args:
        seconds: 秒数

    Returns:
        格式化的时间字符串,如 "02:35"
    """
    if seconds < 0 or seconds > 86400:  # 超过24小时显示--
        return "--"

    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02d}:{secs:02d}"


def update_status_bar_idle(widgets: Dict[str, tk.Widget]):
    """
    更新状态栏为空闲状态

    Args:
        widgets: UI组件字典
    """
    task_status_label = widgets.get("task_status_label")
    progress_label = widgets.get("progress_label")
    speed_label = widgets.get("speed_label")
    time_label = widgets.get("time_label")

    if task_status_label:
        task_status_label.config(text="空闲")
    if progress_label:
        progress_label.config(text="0/0 (0%)")
    if speed_label:
        speed_label.config(text="- 条/秒")
    if time_label:
        time_label.config(text="00:00 | 剩余 --")


def update_status_bar_progress(widgets: Dict[str, tk.Widget], progress_data: Dict[str, Any]):
    """
    更新状态栏进度信息

    Args:
        widgets: UI组件字典
        progress_data: 进度数据字典,包含以下字段:
            - task_name: 任务名称
            - current_batch: 当前批次
            - total_batches: 总批次数
            - progress_percent: 完成百分比
            - records_processed: 处理的记录数
            - elapsed_time: 已用时间(秒)
            - estimated_remaining: 预计剩余时间(秒)
            - speed_records_per_sec: 每秒处理记录数
            - speed_sec_per_batch: 每批次耗时(秒)
    """
    task_status_label = widgets.get("task_status_label")
    progress_label = widgets.get("progress_label")
    speed_label = widgets.get("speed_label")
    time_label = widgets.get("time_label")

    # 更新任务状态
    task_name = progress_data.get("task_name", "")
    if task_status_label and task_name:
        task_status_label.config(text=f"正在执行: {task_name}")

    # 更新进度
    current = progress_data.get("current_batch", 0)
    total = progress_data.get("total_batches", 0)
    percent = progress_data.get("progress_percent", 0)
    if progress_label:
        progress_label.config(text=f"{current}/{total} ({percent:.1f}%)")

    # 更新速度 (优先显示条/秒)
    if speed_label:
        speed_rps = progress_data.get("speed_records_per_sec")
        if speed_rps is not None and speed_rps > 0:
            speed_label.config(text=f"{int(speed_rps)} 条/秒")
        else:
            speed_spb = progress_data.get("speed_sec_per_batch", 0)
            if speed_spb > 0:
                speed_label.config(text=f"{speed_spb:.2f} 秒/批")
            else:
                speed_label.config(text="- 条/秒")

    # 更新时间
    if time_label:
        elapsed = progress_data.get("elapsed_time", 0)
        remaining = progress_data.get("estimated_remaining", 0)

        elapsed_str = format_time(elapsed)
        remaining_str = format_time(remaining) if remaining > 0 else "--"

        time_label.config(text=f"{elapsed_str} | 剩 {remaining_str}")


def update_status_bar_completed(widgets: Dict[str, tk.Widget], task_name: str,
                                 total_time: float, avg_speed: float = 0):
    """
    更新状态栏为任务完成状态

    Args:
        widgets: UI组件字典
        task_name: 任务名称
        total_time: 总用时(秒)
        avg_speed: 平均速度(条/秒)
    """
    task_status_label = widgets.get("task_status_label")
    progress_label = widgets.get("progress_label")
    speed_label = widgets.get("speed_label")
    time_label = widgets.get("time_label")

    if task_status_label:
        task_status_label.config(text=f"已完成: {task_name}")
    if progress_label:
        progress_label.config(text="100%")
    if speed_label:
        if avg_speed > 0:
            speed_label.config(text=f"平均 {int(avg_speed)} 条/秒")
        else:
            speed_label.config(text="已完成")
    if time_label:
        total_str = format_time(total_time)
        time_label.config(text=f"总用时 {total_str}")
