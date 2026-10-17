# 变更日志（CHANGELOG）

> 版本号的**唯一权威**是仓库根的 `VERSION` 文件（一行，形如 `2026.10.17`）。
> 备份 manifest、运维手册、发布 tag 都取它 —— 不要在别处另写一份版本号。

格式约定：`YYYY.MM.DD`；同一天多次发布用 `YYYY.MM.DD-N`。

---

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
