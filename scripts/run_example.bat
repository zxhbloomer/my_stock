@echo off
REM 运行 Qlib 示例
REM 使用方法: run_example.bat [配置文件名]

set CONFIG_FILE=%1
if "%CONFIG_FILE%"=="" set CONFIG_FILE=configs\workflow_config_lightgbm_Alpha158.yaml

echo 正在运行配置: %CONFIG_FILE%
qrun %CONFIG_FILE%

echo.
echo 运行完成！查看结果请运行: mlflow ui
pause
