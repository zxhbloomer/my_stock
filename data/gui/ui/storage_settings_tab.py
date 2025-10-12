"""
存储设置标签页 UI

负责创建"存储设置"标签页的全部Tkinter控件。
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict
from ..utils.dpi_manager import get_dpi_manager, DisplayMode
from ..utils.dpi_aware_ui import get_ui_factory


def create_storage_settings_tab(parent: ttk.Frame) -> Dict[str, tk.Widget]:
    """创建"存储设置"标签页的Tkinter布局。"""
    widgets = {}

    # --- PostgreSQL 框架 ---
    db_frame = ttk.LabelFrame(parent, text="PostgreSQL 设置 (从 .env 文件读取)", padding="10")
    db_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

    # 显示提示信息而不是输入框
    db_info_text = (
        "数据库配置已从项目根目录的 .env 文件中读取:\n\n"
        "配置项: DATABASE_URL\n"
        "格式: postgresql://用户名:密码@主机:端口/数据库名\n"
        "示例: postgresql://root:123456@localhost:5432/my_stock\n\n"
        "💡 请直接编辑 .env 文件来修改数据库配置"
    )
    db_info_label = ttk.Label(
        db_frame,
        text=db_info_text,
        justify=tk.LEFT,
        foreground="blue",
        wraplength=600
    )
    db_info_label.pack(fill=tk.X, padx=5, pady=5)
    widgets["db_info_label"] = db_info_label

    db_frame.grid_columnconfigure(0, weight=1)

    # --- Tushare 框架 ---
    ts_frame = ttk.LabelFrame(parent, text="Tushare 设置 (从 .env 文件读取)", padding="10")
    ts_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

    # 显示提示信息而不是输入框
    ts_info_text = (
        "Tushare Token 已从项目根目录的 .env 文件中读取:\n\n"
        "配置项: TUSHARE_TOKEN\n"
        "示例: TUSHARE_TOKEN=c4fa0e779d637814a2f22bacebaa63ac71c9daae4932dd8d24375ef7\n\n"
        "💡 请直接编辑 .env 文件来修改 Tushare Token\n"
        "🔗 获取Token: https://tushare.pro/register"
    )
    ts_info_label = ttk.Label(
        ts_frame,
        text=ts_info_text,
        justify=tk.LEFT,
        foreground="blue",
        wraplength=600
    )
    ts_info_label.pack(fill=tk.X, padx=5, pady=5)
    widgets["tushare_info_label"] = ts_info_label

    ts_frame.grid_columnconfigure(0, weight=1)

    # --- 显示设置框架 ---
    display_frame = ttk.LabelFrame(parent, text="显示设置", padding="10")
    display_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
    
    # 获取DPI管理器和UI工厂
    dpi_manager = get_dpi_manager()
    ui_factory = get_ui_factory()
    
    # 当前显示信息
    info_text = f"当前分辨率: {dpi_manager.dpi_info.logical_resolution[0]}x{dpi_manager.dpi_info.logical_resolution[1]}\n"
    info_text += f"DPI缩放: {dpi_manager.dpi_info.scale_factor:.0%}\n"
    info_text += f"高DPI环境: {'是' if dpi_manager.dpi_info.is_high_dpi else '否'}"
    
    display_info_label = ui_factory.create_label(display_frame, text=info_text, justify=tk.LEFT)
    display_info_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
    widgets["display_info_label"] = display_info_label
    
    # 显示模式选择
    mode_label = ui_factory.create_label(display_frame, text="显示模式:", width=12, anchor=tk.W)
    mode_label.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
    
    mode_values = [
        ("自动检测", DisplayMode.AUTO.value),
        ("标准模式", DisplayMode.STANDARD.value),
        ("高DPI模式", DisplayMode.HIGH_DPI.value),
        ("4K优化模式", DisplayMode.UHD_4K.value)
    ]
    
    mode_combo = ui_factory.create_combobox(
        display_frame, 
        values=[item[0] for item in mode_values],
        state="readonly",
        width=20
    )
    mode_combo.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)
    
    # 设置当前值
    current_mode = dpi_manager.current_mode.value
    for display_name, mode_value in mode_values:
        if mode_value == current_mode:
            mode_combo.set(display_name)
            break
    
    widgets["display_mode_combo"] = mode_combo
    widgets["display_mode_values"] = mode_values  # 保存映射关系
    
    # 推荐模式提示
    recommended_mode = dpi_manager.recommend_display_mode()
    recommended_text = f"推荐模式: "
    for display_name, mode_value in mode_values:
        if mode_value == recommended_mode.value:
            recommended_text += display_name
            break
    
    recommend_label = ui_factory.create_label(display_frame, text=recommended_text, foreground="blue")
    recommend_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))
    widgets["display_recommend_label"] = recommend_label
    
    # 应用按钮和重启按钮
    button_subframe = ui_factory.create_frame(display_frame)
    button_subframe.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="w")
    
    apply_display_button = ui_factory.create_button(
        button_subframe,
        text="应用显示设置"
    )
    apply_display_button.pack(side=tk.LEFT, padx=(0, 10))
    widgets["apply_display_button"] = apply_display_button
    
    restart_app_button = ui_factory.create_button(
        button_subframe,
        text="重启应用"
    )
    restart_app_button.pack(side=tk.LEFT)
    widgets["restart_app_button"] = restart_app_button

    # --- 底部按钮框架 ---
    button_frame = ttk.Frame(parent, padding=(0, 10))
    button_frame.pack(side=tk.TOP, fill=tk.X, pady=5)

    test_db_button = ttk.Button(
        button_frame,
        text="测试数据库连接",
    )
    test_db_button.pack(side=tk.LEFT, padx=(0, 10))
    widgets["test_db_button"] = test_db_button

    # --- 状态/信息标签 ---
    info_label = ttk.Label(
        parent,
        text="💾 数据库连接URL不能为空。",
        justify=tk.LEFT,
        foreground="red",
        wraplength=600,
    )
    info_label.pack(side=tk.TOP, fill=tk.X, pady=(10, 0))
    widgets["settings_info_label"] = info_label

    return widgets 