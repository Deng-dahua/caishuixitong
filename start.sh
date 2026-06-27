#!/bin/bash
# 财税系统启动脚本（Git Bash/Linux）
PORT=8001
VENV="C:/Users/26726/.workbuddy/binaries/python/envs/zhangwu/Scripts/python.exe"

echo "[1/4] 清除端口 $PORT..."
PID=$(netstat -ano 2>/dev/null | grep ":$PORT" | grep LISTENING | awk '{print $5}' | head -1)
if [ -n "$PID" ]; then
    echo "  杀掉 PID $PID"
    taskkill //F //PID $PID 2>/dev/null
fi
sleep 2

echo "[2/4] 清除字节码缓存..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null

echo "[3/4] 启动服务器... 访问地址：http://localhost:$PORT"
echo "[4/4] 登录页：打开浏览器访问 http://localhost:$PORT/"
PYTHONDONTWRITEBYTECODE=1 $VENV -B -m uvicorn main:app --host 0.0.0.0 --port $PORT --reload
