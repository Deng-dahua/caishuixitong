# 测试夹具（tests/fixtures/）

本目录存放**版本库内固化的测试样本**，供测试在"真实数据"上断言。

## 为什么样本放在这里，而不是 `scripts/four_reports/`

`scripts/four_reports/` 是**生产运行时产物目录**（`runtime_storage.offline_reports_root()`
管辖，`.gitignore` 已忽略）。它有三个致命属性：

1. **会随「删除账套」被清理** —— 2026-10-20 用户拍板清理 company 1 幽灵账套时，
   唯一权威 `main.purge_company_analysis_artifacts` 按「删了就是真删干净」铁律
   清掉了 `company_1_*.json` ⇒ **33 项测试立刻变红**（16 个套件硬编码该路径）。
2. **全新克隆的仓库里根本不存在**（gitignore） ⇒ 新环境跑测试大面积红。
3. **可被任意运维动作清空**。

⇒ 测试依赖它 = 判据依赖**可变的运行时状态**，违反本项目「判据不得依赖可变运行时状态」
「夹具缺失必须报错、不得静默跳过」两条铁律。

## 口径

- 所有测试**只通过 `tests/fixtures/_paths.py` 取夹具路径**（唯一构造点），
  不各自硬编码 `ROOT / "scripts" / "four_reports" / ...`。
- `_paths.offline_report()` 缺文件 ⇒ **抛 FileNotFoundError**（不返回空 ⇒ 不假绿）。
- 测试里原 `if not p.exists(): pytest.skip("无真跑产物")` 一律改为
  `assert p.exists(), "测试夹具缺失..."` —— 夹具是版本库内样本，**缺失即错误**。

## 夹具清单

| 文件 | 大小 | 内容 | 来源 |
|---|---|---|---|
| `company_1_full.json` | ~36MB | company 1 全量分析产物快照（`total_risks=24`） | 清理前 `scripts/four_reports/company_1_full.json`（36163599 字节那版），副本在 `data/trash/company_1_full.1.json` |
| `company_1_summary.json` | 13KB | 摘要产物 | 同上（`company_1_summary.1.json`） |
| `wb_trisk_001_baseline.json` | 138KB | WB-2026-10-001 基线（早于本次） | 既有 |

## 刷新口径（何时、如何更新）

夹具是**历史快照**，只在下列情形更新，且必须**同时**更新 `_paths` 与本文档：

1. 报告载荷结构发生**不兼容变更**（如新增必填章节）⇒ 用新版本重新生成一份样本覆盖；
2. 需要覆盖不同行业/规模企业的样本 ⇒ **新增**文件（勿覆盖既有，避免同时改变多套断言）。

刷新命令（在真实分析完成后）：

```bash
cp scripts/four_reports/company_1_full.json tests/fixtures/company_1_full.json
./.venv/Scripts/python.exe -m pytest tests/ -q      # 必须全量回归
```

★ 注意：更新夹具会**改变多套断言的输入**，因此必须在**同一次提交**里跑全量回归并
核对失败集合与基线一致（零新增）。不得只跑"新文档通过"就宣称全部通过。