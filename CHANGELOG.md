# 变更日志（CHANGELOG）

> 版本号的**唯一权威**是仓库根的 `VERSION` 文件（一行，形如 `2026.10.18`）。
> 备份 manifest、运维手册、发布 tag 都取它 —— 不要在别处另写一份版本号。

格式约定：`YYYY.MM.DD`；同一天多次发布用 `YYYY.MM.DD-N`。

---

## 2026.10.18

### 新增
- **API 公共边界唯一权威（R-02）**：新增 `engine/api_common.py`（`session_of` / `admin_of` /
  `require_perm` / `request_perm` / `call_boundary`）。此前 `_session` 在 **10 个** API 文件
  各复制一份、`_call` **8 份**、`_require_perm`/`_request_perm` 各 **6 份** —— 这是
  **权限口径漂移的机制**。现所有文件改为别名引用，`_call` 统一转发 `call_boundary`
  并**显式声明**本域异常类型。闸门 `check_api_boundary_single_source` 禁止回退。
- **批量解析（H-05）**：`POST /api/v1/projects/{id}/extract-batch`（逐条独立、部分失败不回滚、
  单次上限 50、`only_pending` 默认不重解析已成功的）+ 解析页「批量解析」面板。
  此前 102 份资料要点 102 次。
- **阈值告警（O-03）**：`engine/alerting.py` —— 5 条规则（5xx 错误率 / P95 延迟 / 磁盘 /
  备份过期 / 作业失败率），带**冷却窗口**与**分级**；`GET/POST /api/v1/system/alerts[/evaluate]`。
- **请求关联 id（O-04）**：`engine/request_context.py` —— 沿用或生成 `X-Request-ID`，
  写入 contextvar，**日志每行自动带 `[rid=...]`**，响应头回传。
- **部署手册**：`docs/部署手册.md`（前置条件 / 离线安装 / 首次启动 / 验收 / 升级 / 回滚 / 部署清单）。

### 修复
- **静态资源 `?v=` 漏项（系统级）**：`sync_asset_versions.py` 与闸门此前**只处理已带 `?v=` 的引用**，
  对"根本没有 `?v=`"完全无声。实测 **22 个页面 / 40 处**引用没有版本号，含**所有页面专属 JS**
  （`risks.js` / `projects.js` / `extract.js` / `documents.js` / `users.js` …）⇒
  浏览器按 URL 长期缓存，**这些文件的前端改动可能永远到不了用户**。已全部补齐（124 处引用），
  并把"缺 `?v=`"纳入闸门 ERROR。
- **`logkit.py` 提到根目录**：`engine/logging_setup` 会与 `engine/__init__` 形成循环导入，
  日志设施不该被业务包绑住（`engine/logging_setup` 保留同签名转发）。
- **`parse_batch` 的 `limit=0` 被静默替换成 50**：`int(0 or 50)` 的坑，测试抓到并修正。

### 变更
- `print → logger` 迁移 **138 处**（`database.py` 51 / `main.py` 30 / `audit.py` 11 /
  `engine/enterprise_report.py` 46 + 1 手工）。分级口径：失败但已兜底=warning，其余=info。
- 新增闸门 `check_print_budget`：print 总数**只许减不许增**（当前预算 55，实测 50）。
- 日志格式改为 `时间 [级别] [rid=...] 模块: 消息`。

### 已知问题（未在本版解决）
- 旧 `/api/*` 159 条路由与 `/api/v1/*` 并存，旧版权限更宽（R-03，需灰度下线）；
- 并发扩展性受 SQLite 单写者限制（PF-02，架构级）；
- 部分解析页以外模块（项目 / 模板 / 规则版本 / 用户）仍以逐条操作为主（价值密度低于解析与复核）。

---

## 2026.10.17
## 2026.10.17

### 新增
- **备份与恢复（S-10 / D-02）**：在线一致快照（`VACUUM INTO`）、SHA-256 + `integrity_check`
  双重校验、保留策略、启动时自动补一次 + 每小时判一次的每日调度；
  新增管理页「💾 备份与恢复」（仅管理员）、命令行 `scripts/backup_cli.py`（list/create/verify/restore）。
- **服务崩溃自动重启（D-03）**：`scripts/serve_supervisor.py`；`start8001.bat` 改为经守护器启动
  （1/2/5/10/30/60 秒退避；端口已占用时**拒绝**起第二个实例）。
- **法规库检索性能（PF-01）**：`article_entries` 改为「筛选 → 排序 → 切片 → 按法去重装饰」，
  正文库条目加 mtime 缓存。实测 `/api/v1/legal-library` P50 **3692~7313 ms → 36~45 ms**。
- `VERSION`、`CHANGELOG.md`、`docs/运维手册.md`、`docs/用户手册.md`。
- 前端权限门控覆盖扩到 **26 个页面**（新增 `backup.html`，管理员门控）。

### 修复
- **README 端口写错**：`127.0.0.1:8000` → `127.0.0.1:8001`（照 README 部署会访问失败）。
- `start8001.bat` 经守护器启动后仍保持 CRLF + 纯 ASCII（项目铁律）。

### 安全 / 数据
- 备份恢复路径增加**硬护栏** `_assert_inside()`：写入目标必须落在 `DATA_DIR` 之内；
  恢复前必须清理 `-wal` / `-shm` 边车，避免旧事务重放到刚恢复的库上。
- 新增回归判据：`tests/test_backup_restore.py::test_restore_never_touches_files_outside_data_dir`
  （恢复跑完后，`DATA_DIR` 之外的库文件大小与 mtime 必须不变）。

### 已知问题（未在本版解决）
- `_api/*` 旧路由与 `/api/v1/*` 并存（旧路由权限更宽），见优化建议 R-03；
- 产品代码仍有大量 `print` 而非 `logging`（O-01），线上排障只能翻 stdout；
- 无指标采集（O-02）、无阈值告警（O-03）；
- 17/21 模块不记忆上次选择（H-01）、7 个模块无回收站入口（H-04）。

---

## 2026.10.16 及更早

评估轮次与工程改动记录在 `docs/元质量_20261016/` 下的 23 份报告与各轮提交说明中。
从本版起，**每次发布必须在本文件顶部加一段**（`scripts/ci_check.py --version-check` 会检查
`VERSION` 与 CHANGELOG 首段是否一致）。
