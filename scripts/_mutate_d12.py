# -*- coding: utf-8 -*-
"""疑点2 D12：`missing_materials` 改为输出**具体材料名**（唯一权威＝证据项名）。

病根（实测）：`evidence_chain.build_evidence_chain` 组装待补清单时追加的是**类别名**
（`category`），而同一份报告的证据表用的是**证据项名**（`text`，如「采购合同与入库验收单」）
⇒ 同一件事两套粒度：疑点2 的 `missing_materials=["合同文件"]` vs 证据表缺失项
`["采购合同与入库验收单","物流单据与承运记录"]`，读者无法对上要补什么。

修法：**只改输出粒度，不改判定**。
  · 剔除仍按**类别**判（`category in _na_docs` 是对的：业态不适用是类别级事实）；
  · 进清单的名字改为**证据项名**（具体材料名），符合项目铁律
    「面向企业的『要补什么』只能用具体材料名，类别名 ≠ 资料名」；
  · 若同一类别下有多个具体名，逐个列出（企业要补的是具体那几样）。

★ 本文件文案不含 ASCII 引号（前几轮栽在字符串收尾引号上）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "evidence_chain.py")

OLD = (
    "        bucket = verify_materials if e[\"status\"] == \"待核\" else missing_materials" + NL +
    "        text = e[\"name\"]"
)
NEW = (
    "        bucket = verify_materials if e[\"status\"] == \"待核\" else missing_materials" + NL +
    "        text = e[\"name\"]" + NL +
    "        # ★★ 2026-10-04（疑点2 D12）：**待补清单必须给具体材料名，不能给类别名**。" + NL +
    "        #   实测事故：清单写「合同文件」（类别级），而同一份报告的证据表写" + NL +
    "        #   「采购合同与入库验收单」（具体名）⇒ 同一件事两套粒度，读者对不上要补什么。" + NL +
    "        #   项目铁律：面向企业的『要补什么』只能用**具体材料名**（类别名 ≠ 资料名）。" + NL +
    "        #   ⚠ **只改输出粒度，不改判定**：业态剔除仍按**类别**判（类别级事实）。" + NL +
    "        _out_name = str(text or \"\").strip() or str(category)"
)

base = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in base
t = base.replace(CRLF, NL)
if t.count(OLD) != 1:
    print("!! 锚点命中 %d 次" % t.count(OLD))
    sys.exit(2)
t = t.replace(OLD, NEW, 1)

# 把后续的 category 追加改成具体名（该文件里 `missing_materials.append(category)` 形态）
import re
n_before = len(re.findall(r"(\s*)(bucket)\.append\(category\)", t))
t2 = re.sub(r"(\s*)bucket\.append\(category\)",
            r"\1bucket.append(_out_name)   # D12：具体材料名（唯一权威＝证据项名）", t)
n = len(re.findall(r"bucket\.append\(_out_name\)", t2))
io.open(P, "w", encoding="utf-8", newline="").write(t2.replace(NL, CRLF) if crlf else t2)
print("OK D12 已改：待补清单输出具体材料名（bucket.append 命中 %d 处）" % n)
