@echo off
REM 激活环境并运行示例
REM 前提：已创建 mystock 环境

echo ========================================
echo 激活 Conda 环境并运行示例
echo ========================================
echo.

echo 激活环境: mystock
call conda activate mystock

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================
    echo 环境激活失败！
    echo.
    echo 请先创建环境:
    echo   scripts\setup_env.bat
    echo.
    echo 或手动创建:
    echo   conda env create -f environment.yml
    echo ========================================
    pause
    exit /b 1
)

echo.
echo 环境已激活！
echo.
echo 运行策略: CSI300 + LightGBM + Alpha158
echo.

qrun configs\workflow_config_lightgbm_Alpha158.yaml

echo.
echo ========================================
echo 运行完成！
echo.
echo 查看结果:
echo   mlflow ui
echo   然后访问: http://localhost:5000
echo ========================================
echo.
pause
