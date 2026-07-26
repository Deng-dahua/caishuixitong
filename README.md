# 财税风险防控系统（安全加固版）

本副本在保留原业务代码和 1720 条规则库的基础上，完成了认证、租户隔离、
密钥、静态数据、上传、缓存、日志、数据库和启动方式的安全整改。发布包不含
原数据库、会话、密钥、上传件、缓存和访问日志。

## 首次启动（Windows）

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe manage_users.py create admin --role admin
.\start.bat
```

浏览器访问 `http://127.0.0.1:8000`。本地 HTTP 启动脚本只监听回环地址，并将
安全 Cookie 的 HTTPS 要求仅在本机开发会话中关闭。

Linux/macOS 使用 `.venv/bin/python manage_users.py ...` 和 `./start.sh`。

## 生产部署

1. 使用 HTTPS 反向代理，不要把 Uvicorn 直接暴露到公网。
2. 保持 `APP_COOKIE_SECURE=1`，把 `APP_ALLOWED_ORIGINS` 设为实际 HTTPS 域名。
3. 用进程管理器注入 `LLM_API_KEY`，不得写入项目文件或 Web 页面。
4. 将 `APP_DATA_DIR` 指向受限目录，只授予服务账号读写权限并纳入加密备份。
5. 通过 `python manage_users.py create USER --companies 1,2` 创建普通用户。
6. 定期执行 `python tools/verify_release.py`，升级依赖前先在测试环境验证。

## 数据与密钥迁移

- 旧会话全部作废，不迁移 `sessions.json`。
- 旧 LLM 密钥已经暴露过，必须在供应商控制台撤销并新建；只把新密钥写入环境。
- 使用 `python tools/migrate_legacy_data.py --source-root <旧项目目录>` 迁移数据库和
  上传文件。工具默认拒绝覆盖现有数据，并自动建立迁移前备份。
- Git 历史中的旧密钥不能靠删除工作区文件消失，参见 `docs/GIT_HISTORY_CLEANUP.md`。

## 关键安全行为

- 密码使用 scrypt 哈希；会话令牌仅以 SHA-256 摘要落库，8 小时过期且可撤销。
- 所有状态变更请求校验 CSRF；登录失败会渐进式锁定。
- 普通用户只可访问分配的 `company_id`；账套创建/删除仅管理员可用。
- `/api/apikey` 只返回“是否配置”和末四位，禁止网页写入、探测任意 URL。
- `data/` 保存数据库、上传、缓存和日志，`static/` 只保存公开前端资源。
- 缓存通过临时文件、同步落盘和原子替换写入；SQLite 启用外键、WAL 和账套索引。

## 管理命令

```text
python manage_users.py list
python manage_users.py create USER --role user --companies 1,2
python manage_users.py reset-password USER
python manage_users.py revoke-sessions USER
python tools/audit_rules.py
python tools/verify_release.py
```

OCR 功能还要求操作系统安装 Tesseract；没有安装时，其余功能仍可运行。
