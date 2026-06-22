#!/usr/bin/env python
"""检查服务器状态 & main.py 语法"""
import sys, os, subprocess, json

os.chdir(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("1. 编译检查 main.py...")
try:
    import py_compile
    py_compile.compile('main.py', doraise=True)
    print("   ✅ main.py 语法正确")
except py_compile.PyCompileError as e:
    print(f"   ❌ 语法错误: {e}")
    sys.exit(1)

print("\n2. 检查服务器端口 8001...")
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('127.0.0.1', 8001))
    s.close()
    print("   ✅ 服务器在运行 (端口 8001)")
except ConnectionRefusedError:
    print("   ❌ 服务器未运行! 需要启动服务器")
    print("\n   运行命令:")
    print("   cd caishuixitong && .venv\\Scripts\\python.exe -B -m uvicorn main:app --host 0.0.0.0 --port 8001")

print("\n3. Git 状态...")
try:
    r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, timeout=5)
    print(r.stdout if r.stdout.strip() else "   (无变更)")
except Exception as e:
    print(f"   git 状态检查失败: {e}")

print("\n4. 最新 git 提交...")
try:
    r = subprocess.run(["git", "log", "--oneline", "-3"], capture_output=True, text=True, timeout=5)
    print(r.stdout.strip() or "   (无提交)")
except Exception as e:
    print(f"   git log 失败: {e}")

print("=" * 60)
