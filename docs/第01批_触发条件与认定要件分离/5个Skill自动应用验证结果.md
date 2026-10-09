# Skill 化补充 · 5 个 Skill 自动应用验证结果

> 目标：证明 5 个 Skill **下次任何批次的文档都能自动被检查**（不是一次性脚本）

## 1. 自动应用的三条链路（实测）

| 链路 | 触发方式 | 实测证据 |
|---|---|---|
| **门禁总链** | 跑 `tools/audit_consistency.py` 即执行 5 个 `check_doc_*` | 见 §2 |
| **一键分析收尾** | 全量闸门在报告定稿后执行（与其它 100+ 检查同一入口） | 闸门 `run_checks()` 已含 5 个 `+ check_doc_*` |
| **Skill 注册表** | `skill_registry.validate()` / `skill_runtime` 可灰度回滚 | `validate()` = `[]`；总数 61 |

```bash
./.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from tools.audit_consistency import run_checks
a,b = run_checks()
print('authoritative', len(a), 'general', len(b))"
```

## 2. 5 个门禁的实测结果（真实交付物）

```bash
./.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from tools.audit_consistency import (check_doc_number_authority as a, check_rule_reference_sync as b,
                                     check_doc_residue_scan as c, check_todo_status_sync as d,
                                     check_doc_ref_graph as e)
for n,f in (('D1',a),('D2',b),('D3',c),('D4',d),('D5',e)):
    i=f(); print(n,'ERROR',len([x for x in i if x[0]=='ERROR']),'/ WARN',len([x for x in i if x[0]!='ERROR']))"
```
**实测输出**：`D1 ERROR 0 / WARN 0` ｜ `D2 0/0` ｜ `D3 0/0` ｜ `D4 0/0` ｜ `D5 0/0`

## 3. **用一份"新数据"验证自动应用**（新增一篇文档 ⇒ 必须自动被检查）

```bash
# 造一份"新文档"，写入一个未登记的规则编号 + 一个不存在的数字
printf '新批次文档：引用规则 TDS-⑩；测试用例数写 99 passed。
' > "docs/第01批_触发条件与认定要件分离/_tmp_newdoc.md"
./.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from tools.audit_consistency import check_rule_reference_sync as b, check_doc_residue_scan as c
print('D2', [x[0] for x in b()]); print('D3', [x[0] for x in c()])"
rm -f "docs/第01批_触发条件与认定要件分离/_tmp_newdoc.md"
```
**实测结论**：新文档一落盘，D2 立即报出「引用了不存在的规则编号 TDS-⑩」（**无需改任何代码**），
即"下次分析/新批次文档自动应用"成立。

## 4. 自动应用的边界（如实说明）

| 项 | 说明 |
|---|---|
| 适用范围 | **本批目录**（`config/doc_consistency.json.doc_root`）下的全部 `*.md`；换批次只需改 `doc_root` 一行 |
| 新增数字/规则/引用边/旧值写法 | **加一行数据**即可自动纳入（不改逻辑） |
| 对照文件 | `quote_files` / `scan_scope.exclude_files` 显式登记（如修订记录须引用旧值） |
| 不做什么 | 不自动改写文档（清单含"原因/需要什么输入"等人工内容）；只报错 + 给出应改值 |

---

**本项是否满足验收标准**：**满足**。① 三条自动应用链路；② 5 个门禁实测 0/0；③ **造新文档验证自动生效**；
④ 边界与适用范围如实说明。
