# 触发条件与认定要件分离 Skill · 修订记录（C 情况：系统计算逻辑 bug）

> **快照时点：2026-10-07（R1 轮收口；该轮无精确回执时间戳，以日期为准）** ｜ 本文件是**该时刻的快照**：其中出现的「权威值 N」「破坏性 N」「口径锁 N」「反向验证 N」「正例/自证 N」都是**当时**的实测值，与**当前**值可能不同（当前值见 `最小检查集.md` 的规范数字表与 `最终判断.md`）。
> **防篡改**：本文件的每个历史值都在 `config/doc_consistency.json → snapshot_records` 登记为**探针**（门禁 **D3-R4**）—— 事后改动或删改 ⇒ **ERROR**。

> 日期：2026-10-07 ｜ 触发：用户验收「补做3」（疑点2/10/11 认定要件数 = 0）
> 诊断结论：**C 情况成立**（系统计算逻辑 bug）⇒ 按用户要求**输出本修订记录**
> 定性：**不是口径不同，是 bug**（配置里登记了要件，产物却不落）

---

## 1. 缺陷描述（3W：What / Where / Why）

| 项 | 内容 |
|---|---|
| **What（现象）** | 疑点2 / 10 / 11 的结构化块 `determination_criteria = []`（**0 条**）、`criterion_status = {}`，而 `config/risk_conditions.json` 里这 3 个风险键**各登记了 1 条**认定要件（`C1`，前提条） |
| **Where（位置）** | `engine/trigger_conditions.py::classify()`（`determination_criteria` 的构造段） |
| **Why（根因）** | `classify()` **只从 `checkpoints`（逐要件核对记录）构造要件**，**从不回退配置**。这 3 个疑点是"无红线绑定的综合/规则发现"，**没有 `constituents`** ⇒ `constituent_checkpoint.build_constituent_checkpoints()` 返回空 ⇒ `checkpoints=[]` ⇒ `criteria=[]`。**配置与产物两处判定割裂**（同一概念两处实现、互不相认） |

## 2. 连带发现的**门禁漏洞**（同源，必须一起修）

| 判据 | 层级 | 修复前行为 | 判定 |
|---|---|---|---|
| **TDS-①**（风险指标必须同时定义触发条件与认定要件） | **配置级** | ✅ **生效**：这 3 条各登记了 1 条触发条件 + 1 条认定要件 | 生效（**不是**"没生效"） |
| **TDS-⑤⑥⑦⑧**（产物级） | **产物级** | ⚠ **漏判**：`criteria=[]` 与 `criterion_status={}` 是**空↔空**，`[] == []` ⇒ TDS-⑦「一一对应」通过；TDS-⑧ 遍历 `determination_criteria` 时**空数组直接跳过** ⇒ "前提条必须写符合情形"**根本没被检查** | **判据不完整（漏洞）** |

**⇒ 漏洞根因**：产物级判据只约束"**已存在的要件**"，缺一条**同源一致性断言**——
"配置里有 N 条，产物就必须有 N 条"。这与 Skill 6/7 的"漏登记"同族（只校验已登记项）。

## 3. 修复内容（代码 + 门禁 + 测试）

### 3.1 计算逻辑（唯一权威）

**文件**：`engine/trigger_conditions.py` · **函数**：`classify()`（`if not crits:` 新增分支）

```python
# 无核对记录时**回退配置里的认定要件**（口径与用户规格第 6 条一致）：
#   · 前提条（is_precondition）且**触发已命中**（现象已检出）⇒ checked_hit + 「符合情形」
#   · 其余要件 ⇒ not_checked，如实写明"本项为综合/规则发现、未绑定构成要件，本轮未作逐条核对"
if not crits:
    _hit_any = int(ts.get("hit_count") or 0) > 0
    for _c in determination_criteria_of(risk_code):
        _is_pre = bool(_c.get("is_precondition"))
        _ok = _is_pre and _hit_any
        crits.append({
            "id": str(_c.get("id") or ("C%d" % (len(crits) + 1))),
            "desc": str(_c.get("desc") or "")[:200],
            "is_precondition": _is_pre,
            "status": "checked_hit" if _ok else "not_checked",
            "status_text": ("符合情形（这项属于现象/前提条，存在即成立）" if _ok else
                            "未单独核对（本项为综合/规则发现、未绑定构成要件，本轮未作逐条核对）"),
            "independent_source": "",
        })
```

**为什么不是"造假要件"**：配置里的 `C1` 是**真实登记**的前提条（现象本体），
触发命中本身就是它的证据（与其它 13 个疑点同一口径）⇒ 判「符合情形」**有据**；
其余要件如实 `not_checked`（**不判"未发现符合"**，符合"禁止虚假排除"铁律）。

### 3.2 门禁补**同源一致性断言**（TDS-⑨）

**文件**：`tools/audit_consistency.py::check_trigger_determination_separation()`

> 产物 `determination_criteria` **条数必须等于** 配置条数（仅当该风险键在配置登记过）；
> 不等 ⇒ **ERROR**：`疑点「X」结构化块认定要件 N 条 ≠ 配置 M 条（配置有、产物无 ⇒ 读者看不到该核哪条）`

### 3.3 测试（新增防回退）

| 用例 | 断言 | 位置 |
|---|---|---|
| `TestStructuredOutput::test_every_problem_has_full_structured_block` | 16 疑点块齐全；**有要件核对表的疑点要件非空** | `tests/test_trigger_determination_separation.py` |
| `TestGateReverseValidation::test_reverse_missing_block` | 缺块 ⇒ 报红 | 同上 |
| **新增反向验证（本轮实测，命令级）** | 把疑点2 的 `determination_criteria` 清空 ⇒ 门禁**报红 TDS-⑨** | 见 §4.2 |

## 4. 修复验证（命令 + 实测输出）

### 4.1 正向：修复后 3 个疑点各有 1 条要件

```bash
./.venv/Scripts/python.exe -c "
import json; d=json.load(open('scripts/four_reports/company_1_full.json',encoding='utf-8'))
er=d['enterprise_readable_report']
for p in er['confirmed_problems']:
    if p.get('seq') in (2,10,11):
        b=p['trigger_determination']
        print(p['seq'], b['risk_code'], '认定要件', len(b['determination_criteria']),
              '状态键', list(b['criterion_status']),
              '|', str((b['criterion_status'].get('C1') or {}).get('text'))[:30])"
```
**实测输出**：
```
2 SYN-MULTI-TAX-PROFILE 认定要件 1 状态 ['C1'] | 符合情形（这项属于现象/前提条，存在即成立）
10 VR012 认定要件 1 状态 ['C1'] | 符合情形（这项属于现象/前提条，存在即成立）
11 VR019 认定要件 1 状态 ['C1'] | 符合情形（这项属于现象/前提条，存在即成立）
```

`_batch01_numbers.py` 复核：`认定要件为 0 条的疑点：无`；`认定要件合计 68`（16 疑点）。

### 4.2 反向验证：门禁**必须能报红**（否则判据是假的）

```bash
./.venv/Scripts/python.exe -c "
import sys,json; sys.path.insert(0,'.')
import tools.audit_consistency as A
rep=json.load(open('scripts/four_reports/company_1_full.json',encoding='utf-8'))
for p in rep['enterprise_readable_report']['confirmed_problems']:
    if p.get('seq')==2:
        p['trigger_determination']['determination_criteria']=[]
        p['trigger_determination']['criterion_status']={}
A._canonical_report=lambda: rep
iss=A.check_trigger_determination_separation()
e=[i for i in iss if i[0]=='ERROR']; print('ERROR', len(e))
[print(' ', i[2][:120]) for i in e]"
```
**实测输出**：
```
ERROR 1
  疑点「多税种联动稽查风险画像（收入、票账差异、」结构化块认定要件 0 条 ≠ 配置 1 条（配置有、产物无 ⇒ 读者看不到该核哪条）
```

### 4.3 真实产物门禁结果

```bash
./.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'.')
from tools.audit_consistency import check_trigger_determination_separation as f
iss=f(); print('ERROR',len([i for i in iss if i[0]=='ERROR']),'/ WARN',len([i for i in iss if i[0]!='ERROR']))"
# 实测输出：ERROR 0 / WARN 0
```

## 5. 影响面（诚实记录）

| 项 | 说明 |
|---|---|
| 受影响的疑点 | 仅 3 个（`SYN-MULTI-TAX-PROFILE` / `VR012` / `VR019`），即"无红线绑定的综合/规则发现" |
| 对 13 个红线疑点 | **无影响**（它们有构成要件 ⇒ 走 `checkpoints` 分支，不进回退分支） |
| 对金额 | **无影响**：`tax_impact` 数值全量 diff **变值 0**；`overall_level` 仍为 `已核定2项/待核151项` |
| 对结论方向 | **无影响**：这 3 个疑点 `risk_established` 仍为 `False`（唯一前提条满足 ≠ 风险成立） |
| 对交付物 | 需同步更新的表已更新：`05_回归测试报告.md` 的两张逐疑点表（疑点2/10/11 认定要件 0 → 1） |

## 6. 版本与登记

| 项 | 值 |
|---|---|
| Skill 版本 | `trigger_conditions.py` → **1.1.0**（本批内迭代，对外版本号不变；`config/skill_specs.json` 同） |
| 门禁规则数 | 8 → **9**（新增 TDS-⑨） |
| 测试用例数 | **28**（`pytest tests/test_trigger_determination_separation.py -q`）｜文档一致性专项另有 **32 passed** |
| 全量回归 | **1553 passed / 4 skipped / 166 subtests**（`pytest tests/ -q`；**本轮收口实测值**，Skill 化后新增用例 ⇒ 由当时的 1424 升至 1553） |
| 全量闸门 | **ERROR 0**（WARN 见 `最小检查集.md`：本轮 3 条，均为"同词不同义/统一入口名"，非缺陷） |
| `skill_registry.validate()` | **`[]`（合规）**，Skill 总数 **62**（Skill-1 落地后 56，Skill 化 +5） |

---

**本项是否满足验收标准**：**满足**。
① 记录缺陷（What/Where/Why 三段，含文件与函数）；② 记录连带门禁漏洞（TDS-① 生效、产物级漏判及根因）；
③ 记录修复内容（计算逻辑代码 + 门禁 TDS-⑨ + 测试）；④ 修复验证（正向实测 + **反向验证必须报红** + 真实产物 0 ERROR）；
⑤ 影响面（仅 3 疑点、金额不变式 0、结论不变）；⑥ 版本与登记（规则 9 条 / 测试 28 / 回归 1553 / validate `[]`、Skill 总数 62）。
