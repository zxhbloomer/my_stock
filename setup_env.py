#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
环境配置设置脚本
帮助用户快速设置.env文件
"""
import sys
from pathlib import Path


def setup_env():
    """交互式配置.env文件"""
    print("=" * 60)
    print("My Stock 项目环境配置向导")
    print("=" * 60)
    print()

    env_file = Path(".env")

    # 检查是否已存在.env文件
    if env_file.exists():
        print(f"⚠️  .env 文件已存在")
        overwrite = input("是否覆盖现有配置? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("❌ 已取消配置")
            return
        print()

    # 收集配置信息
    print("请输入配置信息（留空则使用默认值）:")
    print("-" * 60)

    # Tushare Token
    print("\n1. Tushare Token")
    print("   获取地址: https://tushare.pro/register")
    tushare_token = input("   请输入Tushare Token: ").strip()

    # Database URL
    print("\n2. PostgreSQL 数据库配置")
    db_host = input("   主机地址 [localhost]: ").strip() or "localhost"
    db_port = input("   端口 [5432]: ").strip() or "5432"
    db_user = input("   用户名 [postgres]: ").strip() or "postgres"
    db_pass = input("   密码: ").strip()
    db_name = input("   数据库名 [tusharedb]: ").strip() or "tusharedb"

    database_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    # 可选配置
    print("\n3. 可选配置")
    log_level = input("   日志级别 [INFO]: ").strip() or "INFO"

    # 生成.env文件内容
    env_content = f"""# ========================================
# My Stock 项目环境变量配置
# 自动生成于: {Path(__file__).name}
# ========================================

# Tushare Pro API Token
TUSHARE_TOKEN={tushare_token}

# PostgreSQL 数据库连接
DATABASE_URL={database_url}

# 日志级别 (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL={log_level}

# 数据缓存目录
CACHE_DIR=~/.my_stock/cache
"""

    # 写入.env文件
    try:
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write(env_content)
        print()
        print("=" * 60)
        print(f"✅ 配置已保存到 {env_file.absolute()}")
        print("=" * 60)
        print()

        # 验证配置
        print("验证配置...")
        if validate_config():
            print("✅ 配置验证通过！")
        else:
            print("⚠️  配置可能不完整，请检查")

        print()
        print("下一步:")
        print("1. 运行测试: python test_imports.py")
        print("2. 启动数据采集: python -m data.collectors.tasks.stock")
        print()

    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
        return


def validate_config():
    """验证配置是否完整"""
    try:
        from dotenv import load_dotenv
        import os

        load_dotenv()

        required_vars = ['TUSHARE_TOKEN', 'DATABASE_URL']
        missing = []

        for var in required_vars:
            value = os.getenv(var)
            if not value or value == 'your_tushare_token_here':
                missing.append(var)

        if missing:
            print(f"⚠️  缺少或未配置: {', '.join(missing)}")
            return False

        return True

    except Exception as e:
        print(f"⚠️  验证配置时出错: {e}")
        return False


def show_example():
    """显示配置示例"""
    print("=" * 60)
    print(".env 文件配置示例")
    print("=" * 60)
    print()

    example_file = Path(".env.example")
    if example_file.exists():
        with open(example_file, 'r', encoding='utf-8') as f:
            print(f.read())
    else:
        print("❌ 找不到 .env.example 文件")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--example":
        show_example()
    else:
        setup_env()
