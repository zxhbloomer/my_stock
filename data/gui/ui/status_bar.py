"""
状态栏UI组件

Windows风格的状态栏,显示任务执行的实时状态、进度、速度和时间统计。
不显示"状态栏"标题,直接展示信息。
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict


def create_status_bar(parent: tk.Widget) -> Dict[str, tk.Widget]:
    """
    创建Windows风格的状态栏(无标题)

    布局: [任务状态 40%] | [进度 20%] | [速度 20%] | [时间 20%]

    Args:
        parent: 父容器widget

    Returns:
        包含状态栏各部分widget的字典
    """
    # 主状态栏容器 - SUNKEN边框,类似Windows状态栏
    status_frame = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=1)
    status_frame.pack(side=tk.BOTTOM, fill=tk.X)

    # 内部容器,用于布局
    inner_frame = ttk.Frame(status_frame)
    inner_frame.pack(fill=tk.X, padx=2, pady=2)

    # 区域1: 任务状态 (左侧,可扩展)
    task_status_label = ttk.Label(
        inner_frame,
        text="空闲",
        anchor=tk.W,
        font=("", 8)  # 小字体
    )
    task_status_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

    # 分隔符1
    sep1 = ttk.Separator(inner_frame, orient=tk.VERTICAL)
    sep1.pack(side=tk.LEFT, fill=tk.Y, padx=3)

    # 区域2: 进度 (固定宽度)
    progress_label = ttk.Label(
        inner_frame,
        text="0/0 (0%)",
        anchor=tk.CENTER,
        width=15,
        font=("", 8)
    )
    progress_label.pack(side=tk.LEFT, padx=5)

    # 分隔符2
    sep2 = ttk.Separator(inner_frame, orient=tk.VERTICAL)
    sep2.pack(side=tk.LEFT, fill=tk.Y, padx=3)

    # 区域3: 速度 (固定宽度)
    speed_label = ttk.Label(
        inner_frame,
        text="- 条/秒",
        anchor=tk.CENTER,
        width=12,
        font=("", 8)
    )
    speed_label.pack(side=tk.LEFT, padx=5)

    # 分隔符3
    sep3 = ttk.Separator(inner_frame, orient=tk.VERTICAL)
    sep3.pack(side=tk.LEFT, fill=tk.Y, padx=3)

    # 区域4: 时间统计 (右侧,固定宽度)
    time_label = ttk.Label(
        inner_frame,
        text="00:00 | 剩余 --",
        anchor=tk.E,
        width=18,
        font=("", 8)
    )
    time_label.pack(side=tk.LEFT, padx=(5, 5))

    return {
        "status_bar_frame": status_frame,
        "task_status_label": task_status_label,
        "progress_label": progress_label,
        "speed_label": speed_label,
        "time_label": time_label
    }
