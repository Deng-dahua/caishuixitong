# -*- coding: utf-8 -*-
"""第三行（重做，最小改动）：回退路径的要件数据源状态改为「权威可用优先」。

与前两次不同：**不移动 `_avail`、不产生重复定义**——
  · 抽 `_available_of(s)` 作为已提供资料清单的唯一取法，优先/回退两条路共用；
  · 回退路径的节点状态：有清单 ⇒ 走资料齐备性唯一权威 `clue_chain.materials_available`；
    无清单（权威无从判定）⇒ 保留原口径 has_data。
  · 既有 P0-5 闸门继续守权威不可用的一侧。

★ 本文件所有中文文案**不含 ASCII 引号**（前两次栽在字符串收尾引号上）。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
CCP = os.path.join(ROOT, "engine", "constituent_checkpoint.py")

H1 = "def build_constituent_checkpoints("
NEWFN = (
    "def _available_of(s: Dict[str, Any]) -> List[str]:" + NL +
    "    # 2026-10-04（合并批次第三行）：本轮已提供资料清单的**唯一取法**。" + NL +
    "    #   此前优先路径与回退路径各写一遍取法，改一处漏一处；抽成本函数后单一权威。" + NL +
    "    _ec = s.get(\"evidence_chain\") or {}" + NL +
    "    if not isinstance(_ec, dict):" + NL +
    "        return []" + NL +
    "    return [str(a) for a in (_ec.get(\"available_materials\") or []) if a]" + NL +
    NL + NL + H1
)
OLD_AVAIL = (
    "    _avail: List[str] = []" + NL +
    "    _ec = s.get(\"evidence_chain\") or {}" + NL +
    "    if isinstance(_ec, dict):" + NL +
    "        _avail = [str(a) for a in (_ec.get(\"available_materials\") or []) if a]"
)
NEW_AVAIL = "    _avail: List[str] = _available_of(s)"
OLD_NODE = (
    "    for n in _nodes:" + NL +
    "        nm = \"、\".join(x for x in (_norm(n.get(\"source\")), _norm(n.get(\"output\"))) if x)" + NL +
    "        if nm:" + NL +
    "            _cands.append((nm, \"已有\" if n.get(\"has_data\") else \"未取得\"))"
)
NEW_NODE = (
    "    # 2026-10-04（合并批次第三行 / 疑点2 D13）：**回退路径不得用环节 has_data 当资料有无**。" + NL +
    "    #   has_data 的语义是「本环节有没有对题读数」，不是「这份资料有没有提供」。" + NL +
    "    #   混用 ⇒ 资料已提供却判未取得 ⇒ 要件未单独核对＝有数据却放弃核对；" + NL +
    "    #   且对题读数越严、误判越多。有清单 ⇒ 走资料齐备性唯一权威；无清单 ⇒ 保留原口径。" + NL +
    "    for n in _nodes:" + NL +
    "        nm = \"、\".join(x for x in (_norm(n.get(\"source\")), _norm(n.get(\"output\"))) if x)" + NL +
    "        if not nm:" + NL +
    "            continue" + NL +
    "        _st_node = \"\"" + NL +
    "        _avail_node = _available_of(s)" + NL +
    "        if _avail_node:" + NL +
    "            try:" + NL +
    "                from engine.clue_chain import materials_available as _ma_node" + NL +
    "                _ok_node, _miss_node = _ma_node(_norm(n.get(\"source\")), _avail_node)" + NL +
    "                if _ok_node:" + NL +
    "                    _st_node = \"已有\"" + NL +
    "                elif _miss_node:" + NL +
    "                    _st_node = \"未取得\"" + NL +
    "            except Exception:  # noqa: BLE001" + NL +
    "                _st_node = \"\"" + NL +
    "        _cands.append((nm, _st_node or (\"已有\" if n.get(\"has_data\") else \"未取得\")))"
)

p = CCP
raw = io.open(p, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
for nm, old, new in (("helper", H1, NEWFN), ("avail", OLD_AVAIL, NEW_AVAIL), ("node", OLD_NODE, NEW_NODE)):
    c = t.count(old)
    if c != 1:
        print("!! %s 命中 %d 次（应为 1）" % (nm, c))
        sys.exit(2)
    t = t.replace(old, new, 1)
assert t.count("_available_of") == 3, t.count("_available_of")
io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK constituent_checkpoint 回退路径已改为权威优先（唯一取法 _available_of）")
