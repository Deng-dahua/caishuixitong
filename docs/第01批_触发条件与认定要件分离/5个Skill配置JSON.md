# Skill 化补充 · 5 个 Skill 配置 JSON

> 日期：2026-10-07 ｜ 唯一数据表 2 份（新增同类只加一行，不改逻辑分支）

## 1. `config/doc_consistency.json` 的键与条数（实测）

| 键 | 作用 | 条数（实测） |
|---|---|---|
| `numbers` | 数字权威映射（id/name/authority/claims/must_state_in/**enforce**） | **22** |
| `sum_checks` | **分项加总 == 合计 == 权威值** | 1 |
| **`consistency_checks`** | **同文件内同一指标多个单值必须相等**（+`required_any` 口径注明） | **2** |
| `rule_catalog` | 规则清单（id/desc） | **9** |
| `rule_catalog_files` | 必须完整列出规则清单的文件 | 1 |
| `ref_graph` | 跨文件引用关系图（up/down/numbers） | 3 |
| `quote_files` | 允许引用旧值作对照的文件（D1/D2/D5 跳过；`enforce` 可逐条豁免） | **15** |
| `status_vocab` | 未完成事项状态词表（D4） | 5 |
| `todo_declaration_marker` | 状态声明必须带的标记（D4） | 1 |
| `d5_scope` | **D5 只管跨文件**（同文件内部一致性归 D1/D4） | 1 |
| **`declaration_scope`** | **声明类文件**（交付物正文）：里面的当前事实必须已登记权威 | **17** |
| **`meta_checks`** | **元判据**：指标短语模式清单（出现即须被 claims 覆盖） | **10** |
| **`naming_rules`** | **交付物命名规范**（常驻名前缀/轮次前缀/禁程度词） | 1 |
| **`deliverable_registry`** | **交付物登记表**（文件名/轮次的唯一权威） | **30** |

**`numbers` 的权威 kind（实测覆盖 `catalog_count、config_count、file_count、grep_line、json_len、product_count、pytest_collect、pytest_receipt`、`regex_count`，共 **9** 种 kind）**：

| kind | 怎么取权威值 | 用在哪 |
|---|---|---|
| `config_count` | `config/*.json` 计数/求和 | 风险指标 / 认定要件 / 前提条 |
| `pytest_collect` | `pytest <file> --collect-only` | 单文件测试用例数 |
| **`pytest_receipt`** | **读最近一次全量运行回执**（`data/logs/pytest_last_run.json`，由 `tests/conftest.py` 写） | **全量回归 passed**（缺回执/过期/非全绿 ⇒ 取不到） |
| **`json_len`** | 任意 JSON 的数组长度（`path` + `expr`） | **Skill 总数**（`config/skill_specs.json → skills`） |
| `grep_line` | `grep -n <pattern> <path>` 实测行号 | 门禁定义/调用行号（**02 / 06 / 01 / 03** 四个消费点） |
| `file_count` | 目录 `*.md` 计数 | 本批交付物份数 |
| `product_count` | 全量产物字段计数 | 疑点数 |
| `catalog_count` | `rule_catalog` 条数 | 门禁规则条数 |

**实条样例 `numbers[0]`（逐字取自文件）**：

```json
{
  "id": "rule_count",
  "name": "本批门禁规则条数",
  "authority": {
    "kind": "catalog_count"
  },
  "claims": [
    {
      "file": "02_系统配置变更清单.md",
      "regex": "质量门禁\\s*\\*{0,2}(\\d+)\\*{0,2}\\s*条规则"
    },
    {
      "file": "06_写入系统证据.md",
      "regex": "TDS-①~⑨（共\\s*(\\d+)\\s*条"
    },
    {
      "file": "最小检查集.md",
      "regex": "门禁\\s*\\*{0,2}(\\d+)\\*{0,2}\\s*条规则"
    }
  ],
  "must_state_in": [
    "02_系统配置变更清单.md",
    "06_写入系统证据.md",
    "最小检查集.md"
  ]
}
```

## 2. `config/doc_synonyms.json`（v1.0.0）

`stale_values` **6** 条；`scan_scope.include_globs` 1 个；
`scan_scope.exclude_files` 3 个。实条样例：

```json
{
  "id": "SV-testcount-25",
  "old": "25 例",
  "variants": [
    "25 例",
    "25例",
    "25 passed",
    "25passed",
    "25 tests",
    "25tests",
    "25 用例",
    "25用例",
    "25 个用例",
    "测试 25",
    "tests 25",
    "25 passed（修",
    "25 passed，修"
  ],
  "replaced_by": "28 例"
}
```

## 3. `config/skill_specs.json` 的 5 个 Skill 登记片段

| id | name | version | impl | entry_points |
|---|---|---|---|---|
| `doc_number_authority` | 文档数字一致性 | 1.0.0 | `engine/doc_number_authority.py` | `audit` |
| `rule_reference_sync` | 规则引用一致性 | 1.0.0 | `engine/rule_reference_sync.py` | `audit` |
| `doc_residue_scan` | 全文残留校验 | 1.0.0 | `engine/doc_residue_scan.py` | `audit, expand_grep` |
| `todo_status_sync` | 未完成事项状态同步 | 1.0.0 | `engine/todo_status_sync.py` | `audit, sync_status` |
| `doc_ref_graph` | 跨文件引用一致性 | 1.0.0 | `engine/doc_ref_graph.py` | `audit, affected_downstream` |

**Skill 总数 61**；`engine.skill_registry.validate()` = `[]`（合规）。

```bash
./.venv/Scripts/python.exe -c "import sys,json; sys.path.insert(0,'.'); from engine import skill_registry as SR; sp=json.load(open('config/skill_specs.json',encoding='utf-8')); print('validate', SR.validate(), '| total', len(sp['skills']))"
# 实测：validate [] | total 61
```

---

**本项是否满足验收标准**：**满足**。两数据表与 5 个登记片段逐字取自真实文件（非示例占位）；
新增【数字/规则/引用边/旧值写法】= 加一行数据；`validate()` = `[]`。
