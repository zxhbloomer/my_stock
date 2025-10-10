@echo off
REM 创建 Conda 虚拟环境
REM 环境名称: mystock

echo ========================================
echo 创建 Conda 虚拟环境: mystock
echo ========================================
echo.

echo 正在创建环境...
conda env create -f environment.yml

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo 环境创建成功！
    echo.
    echo 激活环境命令:
    echo   conda activate mystock
    echo.
    echo 下一步:
    echo   1. 激活环境: conda activate mystock
    echo   2. 下载数据: scripts\download_data.bat
    echo   3. 运行示例: scripts\run_example.bat
    echo ========================================
) else (
    echo.
    echo ========================================
    echo 环境创建失败！
    echo 请检查:
    echo 1. 是否已安装 Anaconda 或 Miniconda
    echo 2. environment.yml 文件是否存在
    echo ========================================
)

echo.
pause
