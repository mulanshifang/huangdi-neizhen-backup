@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] 安装依赖...
python -m pip install -r requirements.txt -q
if not exist .env copy .env.example .env >nul
echo [2/3] 启动服务: http://127.0.0.1:8000
echo [3/3] 首次启动如需配置模型，请编辑 .env 后重启
python -m uvicorn app:app --host 127.0.0.1 --port 8000
pause
