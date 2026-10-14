# -*- coding: utf-8 -*-
"""第三行（重做）：要件数据源状态不得由环节 `has_data` 决定 —— 改为"权威可用优先"。

与前两次不同（不移动 `_avail`、不产生重复定义）：
  · 抽 `_available_of(s)` 作为「本轮已提供资料清单」的**唯一取法**，优先路径与回退路径共用；
  · 回退路径的节点状态：**有清单** ⇒ 走资料齐备性唯一权威 `clue_chain.materials_available`；
    **无清单**（权威无从判定）⇒ 保留原口径 has_data，并如实不 pretend。
  · 既有 P0-5 闸门继续守"权威不可用时不得误判"；另加 ④ 断言守"有清单时必须走权威"。

幂等：写前/写后各断言锚点唯一。
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
CCP = os.path.join(ROOT, "engine", "constituent_checkpoint.py")
AUDIT = os.path.join(ROOT, "tools", "audit_consistency.py")


def rd(p):
    return io.open(p, "r", encoding="utf-8", newline="").read()


def wr(p, s):
    io.open(p, "w", encoding="utf-8", newline="").write(s)


# ══ ① 抽唯一取法 + 回退路径改走权威 ═══════════════════════════════════
H1 = 'def build_constituent_checkpoints('
NEWFN = (
    'def _available_of(s: Dict[str, Any]) -> List[str]:' + NL +
    '    """本轮**已提供资料清单**的唯一取法（优先路径与回退路径共用）。' + NL +
    '' + NL +
    '    ★ 2026-10-04（合并批次第三行）：此前两条路各写一遍取法（`constituent_checkpoint` 内），' + NL +
    '    改一处漏一处。抽成本函数后**单一权威**，且不移动任何既有定义（避免顺序踩坑）。' + NL +
    '    """' + NL +
    '    _ec = s.get("evidence_chain") or {}' + NL +
    '    if not isinstance(_ec, dict):' + NL +
    '        return []' + NL +
    '    return [str(a) for a in (_ec.get("available_materials") or []) if a]' + NL +
    NL + NL + H1
)
OLD_AVAIL_BLOCK = (
    '    _avail: List[str] = []' + NL +
    '    _ec = s.get("evidence_chain") or {}' + NL +
    '    if isinstance(_ec, dict):' + NL +
    '        _avail = [str(a) for a in (_ec.get("available_materials") or []) if a]'
)
NEW_AVAIL_BLOCK = '    _avail: List[str] = _available_of(s)'
OLD_NODE = (
    '    for n in _nodes:' + NL +
    '        nm = "\u3001".join(x for x in (_norm(n.get("source")), _norm(n.get("output"))) if x)' + NL +
    '        if nm:' + NL +
    '            _cands.append((nm, "\u5df2\u6709" if n.get("has_data") else "\u672a\u53d6\u5f97"))'
)
NEW_NODE = (
    '    # \u2605 2026-10-04\uff08\u5408\u5e76\u6279\u6b21\u7b2c\u4e09\u884c / \u7591\u70b92 D13\uff09\uff1a**\u56de\u9000\u8def\u5f84\u4e0d\u5f97\u7528\u73af\u8282' + NL +
    '    #   `has_data` \u5f53"\u8d44\u6599\u6709\u65e0"\u3002`has_data` \u7684\u8bed\u4e49\u662f"\u672c\u73af\u8282\u6709\u6ca1\u6709**\u5bf9\u9898\u8bfb\u6570**"\uff0c' + NL +
    '    #   \u4e0d\u662f"\u8fd9\u4efd\u8d44\u6599\u6709\u6ca1\u6709\u63d0\u4f9b"\u3002\u6df7\u7528\u5c31\u4f1a\u51fa\u73b0"\u8d44\u6599\u5df2\u63d0\u4f9b\u5374\u5224\u300c\u672a\u53d6\u5f97\u300d"' + NL +
    '    #   \u21d2 \u8981\u4ef6\u672a\u5355\u72ec\u6838\u5bf9"\uff0c\u4e14**\u5bf9\u9898\u8bfb\u6570\u8d8a\u4e25\u8bef\u5224\u8d8a\u591a**\u3002' + NL +
    '    #   \u6709\u6e05\u5355 \u21d2 \u8d70\u8d44\u6599\u9f50\u5907\u6027\u552f\u4e00\u6743\u5a01\uff1b\u65e0\u6e05\u5355\uff08\u6743\u5a01\u65e0\u4ece\u5224\u5b9a\uff09\u21d2 \u4fdd\u7559\u539f\u53e3\u5f84\u3002' + NL +
    '    for n in _nodes:' + NL +
    '        nm = "\u3001".join(x for x in (_norm(n.get("source")), _norm(n.get("output"))) if x)' + NL +
    '        if not nm:' + NL +
    '            continue' + NL +
    '        _st_node = ""' + NL +
    '        _avail_node = _available_of(s)' + NL +
    '        if _avail_node:' + NL +
    '            try:' + NL +
    '                from engine.clue_chain import materials_available as _ma_node' + NL +
    '                _ok_node, _miss_node = _ma_node(_norm(n.get("source")), _avail_node)' + NL +
    '                if _ok_node:' + NL +
    '                    _st_node = "\u5df2\u6709"' + NL +
    '                elif _miss_node:' + NL +
    '                    _st_node = "\u672a\u53d6\u5f97"' + NL +
    '            except Exception:  # noqa: BLE001' + NL +
    '                _st_node = ""' + NL +
    '        _cands.append((nm, _st_node or ("\u5df2\u6709" if n.get("has_data") else "\u672a\u53d6\u5f97")))'
)

base = rd(CCP)
crlf = CRLF in base
t = base.replace(CRLF, NL)
for nm, old, new in (("helper", H1, NEWFN),
                    ("avail块", OLD_AVAIL_BLOCK, NEW_AVAIL_BLOCK),
                    ("节点回退", OLD_NODE, NEW_NODE)):
    c = t.count(old)
    if c != 1:
        print("!! %s 命中 %d 次（应为 1）" % (nm, c))
        sys.exit(2)
    t = t.replace(old, new, 1)
assert t.count("_available_of") == 3, t.count("_available_of")
wr(CCP, t.replace(NL, CRLF) if crlf else t)
print("OK constituent_checkpoint 已改（唯一取法 + 权威优先）")

# ══ ② 闸门 ④（幂等） ═══════════════════════════════════════════════════
MARK = '        # \u2463 \u8981\u4ef6\u6570\u636e\u6e90\u72b6\u6001'
ANCH = '                           "\u5254\u9664\u4e86\u6c47\u603b\u884c\u5374\u672a\u5982\u5b9e\u62ab\u9732\uff08\u4e0d\u5f97\u9759\u9ed8\u5c11\u7b97\uff09"))'
GATE = MARK + NL + (
    '        # \u2463 \u8981\u4ef6\u6570\u636e\u6e90\u72b6\u6001\uff082026-10-04 \u5408\u5e76\u6279\u6b21\u7b2c\u4e09\u884c\uff09\uff1a' + NL +
    '        #    \u72b6\u6001**\u4e0d\u5f97**\u7531\u73af\u8282 `has_data` \u51b3\u5b9a\uff08\u6709\u6e05\u5355\u65f6\uff09\u2014\u2014\u5426\u5219' + NL +
    '        #    "\u8d44\u6599\u5df2\u63d0\u4f9b\u5374\u5224\u672a\u53d6\u5f97" \u21d2 \u8981\u4ef6"\u672a\u5355\u72ec\u6838\u5bf9" \uff08= \u6709\u6570\u636e\u5374\u653e\u5f03\u6838\u5bf9\uff09\u3002' + NL +
    '        try:' + NL +
    '            from engine.constituent_checkpoint import (' + NL +
    '                build_constituent_checkpoints as _bcc4)' + NL +
    '            _syn4 = {' + NL +
    '                "constituents": ["\u8981\u4ef6\u4e00\uff1a\u5b58\u5728\u5927\u989d\u672a\u4ed8\u6b3e"],' + NL +
    '                # \u2605 \u523b\u610f**\u4e0d\u58f0\u660e** constituent_sources \u21d2 \u8d70\u56de\u9000\u8def\u5f84\uff1b' + NL +
    '                #   available_materials **\u6709\u503c** \u21d2 \u6743\u5a01\u53ef\u7528\uff0c\u5fc5\u987b\u8d70\u6743\u5a01\u3002' + NL +
    '                "clue_chain": {"nodes": [{"step": 1, "source": "\u5de5\u8d44\u8868",' + NL +
    '                                         "output": "\u5de5\u8d44\u53f0\u8d26", "has_data": False}]},' + NL +
    '                "evidence_chain": {"available_materials": ["\u5de5\u8d44\u8868"], "elements": []},' + NL +
    '                "argumentation": {"constituent_hits": []},' + NL +
    '            }' + NL +
    '            for _c4 in (_bcc4(_syn4, {"id": "RL-T", "name": "n",' + NL +
    '                                        "constituents": ["\u8981\u4ef6\u4e00\uff1a\u5b58\u5728\u5927\u989d\u672a\u4ed8\u6b3e"]}) or []):' + NL +
    '                if "\u672a\u53d6\u5f97" in str(_c4.get("\u6570\u636e\u6e90\u72b6\u6001") or ""):' + NL +
    '                    issues.append(("ERROR", "engine/constituent_checkpoint.py",' + NL +
    '                                   "\u8d44\u6599\u5df2\u63d0\u4f9b\uff08\u5de5\u8d44\u8868\uff09\u5374\u56e0\u73af\u8282 has_data=False \u5224\u672a\u53d6\u5f97 \u21d2"' + NL +
    '                                   "\u6709\u6570\u636e\u5374\u653e\u5f03\u6838\u5bf9\uff1b\u6570\u636e\u6e90\u72b6\u6001\u987b\u8d70\u8d44\u6599\u9f50\u5907\u6027\u552f\u4e00\u6743\u5a01"))' + NL +
    '        except Exception as _e4:  # noqa: BLE001' + NL +
    '            issues.append(("ERROR", "engine/constituent_checkpoint.py",' + NL +
    '                           f"\u8981\u4ef6\u6570\u636e\u6e90\u72b6\u6001\u65ad\u8a00\u6267\u884c\u5931\u8d25\uff1a{_e4}"))'
)
s = rd(AUDIT)
crlf2 = CRLF in s
t2 = s.replace(CRLF, NL)
n_mark = t2.count(MARK)
if n_mark == 0:
    if t2.count(ANCH) != 1:
        print("!! 闸门插入锚点命中 %d 次" % t2.count(ANCH))
        sys.exit(2)
    t2 = t2.replace(ANCH, ANCH + NL + GATE, 1)
elif n_mark == 1:
    print("闸门 ④ 已存在，跳过")
else:
    print("!! 闸门 ④ 出现 %d 次，需先清理" % n_mark)
    sys.exit(2)
wr(AUDIT, t2.replace(NL, CRLF) if crlf2 else t2)
print("OK 闸门 ④ 已插入/已存在（写后标记数 =", rd(AUDIT).count(MARK), "）")

# ══ ③ 基线 + 反向验证 ═════════════════════════════════════════════════
RUN = ("import sys; sys.path.insert(0, %r);"
       "from tools.audit_consistency import check_report_consistency as f;"
       "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
       "[print(chr(32)*4, i[1], i[2][:92]) for i in iss]") % ROOT
RUN2 = ("import sys; sys.path.insert(0, %r);"
        "from tools.audit_consistency import check_audit_doctrine as f;"
        "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
        "[print(chr(32)*4, i[1], i[2][:92]) for i in iss]") % ROOT


def run(r=RUN):
    p = subprocess.run([sys.executable, "-c", r], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return ((p.stdout or "") + (p.stderr or "")).strip()


print("\n=== 基线（report_consistency）===")
print(run())
print("=== 基线（audit_doctrine，含既有 P0-5）===")
print(run(RUN2))

b2 = rd(CCP)
c2 = CRLF in b2
t3 = b2.replace(CRLF, NL)
OLDM = '        _cands.append((nm, _st_node or ("\u5df2\u6709" if n.get("has_data") else "\u672a\u53d6\u5f97")))'
NEWM = '        _cands.append((nm, "\u5df2\u6709" if n.get("has_data") else "\u672a\u53d6\u5f97"))  # MUTATED'
if t3.count(OLDM) == 1:
    t3 = t3.replace(OLDM, NEWM, 1)
    wr(CCP, t3.replace(NL, CRLF) if c2 else t3)
    print("\n=== 反向验证：退回 has_data 判据 ⇒ ===")
    print(run())
    wr(CCP, b2)
    print("\n=== 还原后 ===")
    print(run())
    print(run(RUN2))
else:
    print("\n!! 反向变异锚点命中 %d 次" % t3.count(OLDM))
