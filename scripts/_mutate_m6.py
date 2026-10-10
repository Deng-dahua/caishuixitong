# -*- coding: utf-8 -*-
"""一次性把「门禁豁免跨轮失效 / 自愈未接线」两处根因收敛为单一权威。

做法：归一化为 LF → 纯字符串替换（不用正则，避开 CRLF 转义坑）→ 还原原换行风格。
每个 old 必须命中且只命中 1 次，否则脚本以退出码 2 中止（不留下半改的半成品）。
"""
import io, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = {}

def swap(path, pairs):
    p = os.path.join(ROOT, path)
    with io.open(p, "r", encoding="utf-8", newline="") as fh:
        raw = fh.read()
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for old, new in pairs:
        if s.count(old) != 1:
            print("!! %s: anchor命中 %d 次(应为1): %r" % (path, s.count(old), old[:60]))
            sys.exit(2)
        s = s.replace(old, new, 1)
    if crlf:
        s = s.replace("\n", "\r\n")
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(s)
    print("OK %s (%d 处)" % (path, len(pairs)))

# ── ① findingkit: 新增 finding_identity 唯一权威 ──────────────────────
swap("engine/findingkit.py", [(
    '    "redline_id", "indicator", "indicator_value",\n)\n',
    '    "redline_id", "indicator", "indicator_value",\n)\n'
    '\n'
    '\n'
    '# ★ 发现身份键在此**唯一**定义。原先 `output_governance.seal_governed_findings`\n'
    '#   （封印去重）与 `self_learning`（门禁跨轮豁免记账）**各手写一份**同样的\n'
    '#   「scene_fact_id → fact_id → type」取值 ⇒ 两处会各自漂移；本函数是唯一权威。\n'
    '_IDENTITY_FIELDS = ("scene_fact_id", "fact_id", "type")\n'
    '\n'
    '\n'
    'def finding_identity(finding: Any) -> str:/n'
    '    """一条发现的稳定身份键；三条字段都取不到时返回 ""（调用方据此判定不可跟踪）。\n'
    '\n'
    '    字段取值与 `seal_governed_findings` 现网行为逐字节一致（换成本函数后封印去重\n'
    '    结果不变），只是把「怎么取身份」收敛到一处。\n'
    '    """\n'
    '    if not isinstance(finding, dict):\n'
    '        return ""\n'
    '    for _k in _IDENTITY_FIELDS:/n'
    '        _v = finding.get(_k)\n'
    '        if _v is None or _v == "":\n'
    '            continue\n'
    '        return str(_v).strip()\n'
    '    return ""\n'
)])

# ── ② self_learning ──────────────────────────────────────────────────
swap("engine/self_learning.py", [
    ('from engine.legal_citation import legal_reference_of  # ★ 法条字段唯一权威（判据与产出同源）',
     'from engine.legal_citation import legal_reference_of  # ★ 法条字段唯一权威（判据与产出同源）\n'
     'from engine.findingkit import finding_identity  # ★ 发现身份键唯一权威（跨轮记账用）'),
    ('        self._m06_non_tax_viol_ids = set()',
     '        # ★ 2026-10-04（疑点10-21 合并批次）：豁免/非税**按发现身份记账**，不再按\n'
     '        #   违规对象的 id()。事故：以 id(violation) 为键 ⇒ 一旦复检（自动修复后\n'
     '        #   重跑门禁）就会生成全新的违规字典对象，豁免标记当场失效 ⇒ 上次"已豁免"\n'
     '        #   的元发现/非税项又变回阻断，实测把阻断数从 21 拖到 4 再拖到 2，\n'
     '        #   **每修一次就复发一次**；本轮实证这正是「合规门禁阻断」反复调不完的病根。\n'
     '        #   豁免是这条发现的**固有属性**（元发现/非税/外部核验），不是"这轮跑出来的\n'
     '        #   某个对象"，因此必须锚在发现身份上才能跨轮存活。\n'
     '        self._m06_non_tax_keys = set()'),
    ('        self._m06_exempt_viol_ids = set()',
     '        self._m06_exempt_keys = set()'),
    ('                        self._m06_exempt_viol_ids.add(id(_v))',
     '                        self._m06_exempt_keys.add(finding_identity(f) or (\n'
     '                            "type=" + str(f.get("type", ""))))'),
    ('                        self._m06_non_tax_viol_ids.add(id(_v))',
     '                        self._m06_non_tax_keys.add(finding_identity(f) or (\n'
     '                            "type=" + str(f.get("type", ""))))'),
    ('        blocking = [v for v in self.violations\n'
     '                    if v.get("rule", "") in BLOCKING_RULES\n'
     '                    and id(v) not in self._m06_non_tax_viol_ids\n'
     '                    and id(v) not in self._m06_exempt_viol_ids]',
     '        blocking = [v for v in self.violations\n'
     '                    if v.get("rule", "") in BLOCKING_RULES\n'
     '                    and self._violation_finding_index(v) not in self._m06_non_tax_keys\n'
     '                    and self._violation_finding_index(v) not in self._m06_exempt_keys]'),
    ('    def _verdict(self):',
     '    def _violation_finding_index(self, violation):\n'
     '        """把一条违规还原成**发现身份键**（唯一权威 findingkit.finding_identity）。\n'
     '\n'
     '        还原不出时退回违规对象 id —— 宁可"记不住豁免"也不要"误放行"，\n'
     '        因此这里不做任何兜底成"已豁免"。\n'
     '        """\n'
     '        _key = ""\n'
     '        try:/n'
     '            _key = finding_identity(violation.get("finding_raw"))\n'
     '        except Exception:  # noqa: BLE001\n'
     '            _key = ""\n'
     '        return _key or ("type=" + str(violation.get("finding", "")))\n'
     '\n'
     '\n'
     '    def _verdict(self):'),
    ('            if (f.get("score", 0) or 0) >= 8 and not f.get("law_ref"):',
     '            # ★ 修复判据与 M06 判罚同源（唯一权威 legal_reference_of）：旧实现写\n'
     '            #   not f.get("law_ref")，而门禁判罚读 policy_ref/law_ref ⇒ 同一项在\n'
     '            #   "修前/修后"用两套口径，互为盲区。\n'
     '            if (f.get("score", 0) or 0) >= 8 and not legal_reference_of(f):'),
])
print("[DONE] ① findingkit / ② self_learning 判据与记账已收敛")
