# 启动 8001 服务的可靠启动器：先 os.chdir 到仓库根，再调用 uvicorn.main()。
# 原因：本环境 Bash 的 cd 失效，后台任务的 cwd 非仓库根，main.py 用相对目录 "static" 挂载会报
# RuntimeError: Directory 'static' does not exist。os.chdir 保证 cwd 正确。
import os
import sys

REPO = r"c:/Users/Administrator/WorkBuddy/2026-08-04-21-37-33/caishuixitong"
os.chdir(REPO)
sys.path.insert(0, REPO)

sys.argv = ["uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001"]
import uvicorn

uvicorn.main()
