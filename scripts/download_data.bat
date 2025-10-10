@echo off
REM 下载 Qlib 中国A股数据
REM 参考: https://github.com/microsoft/qlib/tree/main/scripts

echo ========================================
echo Qlib 数据下载工具
echo ========================================
echo.

echo 正在下载中国A股日频数据...
echo 目标目录: %USERPROFILE%\.qlib\qlib_data\cn_data
echo.

REM 使用 Qlib 官方推荐的下载方式（Python 包内置方法）
python -m qlib.run.get_data qlib_data --target_dir ~/.qlib/qlib_data/cn_data --region cn

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo 数据下载完成！
    echo 数据位置: %USERPROFILE%\.qlib\qlib_data\cn_data
    echo ========================================
) else (
    echo.
    echo ========================================
    echo 下载失败！请检查：
    echo 1. 是否已安装 pyqlib
    echo 2. 网络连接是否正常
    echo 3. scripts/get_data.py 是否存在
    echo ========================================
)

echo.
pause
