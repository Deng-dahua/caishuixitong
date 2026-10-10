# -*- coding: utf-8 -*-
"""疑点5 · D6 回填**上移**到段落渲染之前 + except 留痕。

★ 根因（本轮确认）：`chain_desc = _clue_narrative(clue, ...)` 在 **2667** 行就把
  环节文本固化了；而上一版回填在 **3081** 行 ⇒ 改 `nodes` 太晚，文本不重算 ⇒ 完全没生效。

修法
----
① 在 2667 **之前**插入：算 `_limit_items_table(rid, findings)` → 把分项数字回填进
   `clue["nodes"][i]["observed"]`（只回填**动作对题**的环节，环3「核对是否作纳税调增」不填）；
② 3081 处改为**复用**已算好的 `_lit`，不重复计算；
③ 回填的 `except` **必须留痕**（写 `audit_sink`）——
   今天多次"改了没生效"正是被静默 `except` 掩盖的。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "enterprise_report.py")

BACKFILL = '''        # ★★ 2026-10-05（疑点5 D6）：分项扣除限额的数字**回填**到对题环节的 observed。
        #   事故：三环都写「本环节未产出对题读数」，而同疑点的分项测算表里确实有金额
        #   （业务招待费账面 411,111.53／超限 377,927.53；广宣费 2,729,730.26／1,734,210.17）
        #   ⇒ 数据在同疑点内可回指，写「未产出」等于否定已算出的数。
        #   ⚠ 必须在此处（`_clue_narrative` 之前）：那里会把环节文本固化，之后改 nodes 无效。
        #   ⚠ 只回填**动作对题**的环节（环3「核对是否作纳税调增」其读数确实缺汇算清缴明细）。
        _lit = None
        try:
            _lit = _limit_items_table(rid, findings)
        except Exception as _e1:  # noqa: BLE001
            if isinstance(audit_sink, dict):
                audit_sink.setdefault("issues", []).append({
                    "seq": None, "title": str(_title_raw)[:60],
                    "code": "分项限额取数失败", "detail": str(_e1)[:120], "redline_id": rid,
                })
        if _lit:
            try:
                _lim_txt = "；".join(
                    "%s 账面 %s、超限 %s" % (r.get("费用项目"), r.get("账面发生额（元）"), r.get("超限金额（元）"))
                    for r in ((_lit.get("rows") or [])[:3]))
                for _nd in (clue.get("nodes") or []):
                    if not isinstance(_nd, dict):
                        continue
                    _obs5 = str(_nd.get("observed") or "")
                    if "未产出对题读数" not in _obs5:
                        continue
                    _act5 = str(_nd.get("action") or "") + str(_nd.get("output") or "")
                    if not any(_k in _act5 for _k in ("限额", "归集", "扣除", "计算", "发生额")):
                        continue
                    _nd["observed"] = "本环节读数（来自本项分项扣除限额测算）：" + _lim_txt
                    _nd["has_data"] = True
            except Exception as _e2:  # noqa: BLE001
                if isinstance(audit_sink, dict):
                    audit_sink.setdefault("issues", []).append({
                        "seq": None, "title": str(_title_raw)[:60],
                        "code": "分项限额回填失败", "detail": str(_e2)[:120], "redline_id": rid,
                    })
'''

OLD_HEAD = '        chain_desc = _clue_narrative(clue, not_required=not_required_docs)' + NL
OLD_TAIL = '            _lit = _limit_items_table(rid, findings)' + NL
NEW_TAIL = '            _lit = _lit if _lit is not None else _limit_items_table(rid, findings)' + NL

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)

for tag, old in (("回填插入点", OLD_HEAD), ("3081 复用点", OLD_TAIL)):
    c = t.count(old)
    print("%s 命中 = %d" % (tag, c))
    if c != 1:
        print("!! 锚点异常 ⇒ 不写盘")
        sys.exit(2)

# 先移除上一版插在 3081 处的回填块（避免重复）
i = t.find("            # ★★ 2026-10-05（疑点5 D6）：分项数字**回填**到对题环节的 observed。")
if i > 0:
    j = t.find("        # ★ 2026-10-01：**分项扣除限额测算表**", i)
    if j > 0:
        t = t[:i] + t[j:]
        print("已移除上一版回填块")

t = t.replace(OLD_TAIL, NEW_TAIL, 1)
t = t.replace(OLD_HEAD, BACKFILL + OLD_HEAD, 1)
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 回填已上移到段落渲染之前 + except 留痕")
