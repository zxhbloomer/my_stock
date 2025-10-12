#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
启动My Stock数据同步GUI

本脚本用于启动基于Tkinter的数据采集和管理图形界面。
GUI提供以下功能：
- 数据采集任务管理
- 数据处理任务管理
- 任务执行控制和监控
- 存储设置配置
- 任务日志查看

## 使用方式

```bash
# 直接运行
python run_gui.py

# 或在conda环境中运行
conda activate mystock
python run_gui.py
```

## 依赖要求
- Python 3.8+
- tkinter (Python标准库)
- async-tkinter-loop (需要安装)

## 安装GUI依赖
```bash
pip install async-tkinter-loop tkcalendar
```
"""

if __name__ == "__main__":
    import os
    from pathlib import Path
    from dotenv import load_dotenv

    # 确保从项目根目录加载.env文件
    project_root = Path(__file__).parent
    env_file = project_root / ".env"

    if env_file.exists():
        load_dotenv(dotenv_path=env_file)
        print(f"[OK] 已从 {env_file} 加载环境变量")
    else:
        print(f"[WARNING] 未找到 {env_file} 文件")

    from data.gui.main_window import main
    main()
