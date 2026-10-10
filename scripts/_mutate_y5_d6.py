# -*- coding: utf-8 -*-
"""疑点5 · D6 落地：`_on_topic_reading` 取不到时，回落到**本条发现自己的 observed_metrics**。

★ 锚点与实现均已在上一轮**读代码确认**（`engine/clue_chain.py`）：
  - 两处调用点（324 / 379）形如：
        observed = _on_topic_reading(tpl, hits, redline.get("constituents"))
        if not observed:
            _reason = _gap_reason(...)
  - `finding` 变量就在该作用域内（`finding.get('scene_fact_id')` 已在用）
    ⇒ 直接 `finding.get("observed_metrics")`，不需经 engine_data。

为什么（事故原文）：`_on_topic_reading` 只从 `constituent_hits` 取读数；疑点5（RL-CIT-007）
5 条要件全部「未单独核对」⇒ hits 为空 ⇒ 三环都写"未产出读数"；而「分项扣除限额测算」表里
**确实有金额**（业务招待费账面 411,111.53／超限 377,927.53；广宣费 2,729,730.26／1,734,210.17）
⇒ 数据在**同疑点内可回指**，不是"未产出"。

守两条铁律：① 只取与本环节 action **对题**的键（同一 2-gram 阈值）；
② 只用**本条发现自己**的指标，不得改用别的环节/别的发现的数；未达阈值仍走现有如实标注。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "clue_chain.py")

FUNC = '''

def _metrics_reading(node: Dict, finding: Dict) -> str:
    """从**本条发现自己的 observed_metrics** 取与本环节 action 对题的读数（取不到返回 ""）。

    ★ 2026-10-05（疑点5 D6）：`_on_topic_reading` 的唯一来源是 `constituent_hits`；
      疑点5（RL-CIT-007）5 条要件全部「未单独核对」⇒ hits 为空 ⇒ 三环都写"未产出读数"，
      而「分项扣除限额测算」表里**确实有金额**（业务招待费账面 411,111.53／超限 377,927.53；
      广告费和业务宣传费账面 2,729,730.26／超限 1,734,210.17）
      ⇒ 数据在**同疑点内可回指**，不是"未产出"。
      ⚠ 守铁律：只用**本条发现自己**的指标、只取与本环节 action **对题**的键；
        不得改用别的环节/别的发现的数；未达阈值返回 ""（沿用调用方的如实标注）。
    """
    _m = (finding or {}).get("observed_metrics")
    if not isinstance(_m, dict) or not _m:
        return ""
    _nt = _two_grams(str(node.get("action", "")) + str(node.get("output", "")) + str(node.get("source", "")))
    if not _nt:
        return ""
    _best = (0, "", "")
    for _k in _m:
        _v = _m.get(_k)
        if _v in (None, ""):
            continue
        _sc = len(_nt & _two_grams(str(_k)))
        if _sc > _best[0]:
            _best = (_sc, str(_k), _v)
    if _best[0] < _ON_TOPIC_MIN_BIGRAMS:
        return ""
    try:
        _txt = "{:,.2f}".format(float(str(_best[2]).replace(",", "")))
    except Exception:  # noqa: BLE001
        _txt = str(_best[2])
    return "本环节读数（来自本项测算表）：%s = %s" % (_best[1], _txt)

'''

ANCHOR_FUNC = "def _on_topic_reading(node: Dict, hits: List[Dict],"

OLD_CALL = (
    "            observed = _on_topic_reading(tpl, hits, redline.get(\"constituents\"))" + NL +
    "            if not observed:" + NL
)
NEW_CALL = (
    "            observed = _on_topic_reading(tpl, hits, redline.get(\"constituents\"))" + NL +
    "            if not observed:" + NL +
    "                # ★ 2026-10-05（疑点5 D6）：回落到**本条发现自己的** observed_metrics ——" + NL +
    "                #   数据在同疑点内可回指时，不得写「未产出读数」（那是否定已算出的数）。" + NL +
    "                observed = _metrics_reading(tpl, finding)" + NL +
    "            if not observed:" + NL
)

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)

# ① 插入新函数（放在 build_clue_chain 之前，避免改变既有函数顺序）
if "_metrics_reading" in t:
    print("SKIP 函数已在（幂等）")
else:
    c = t.count("def build_clue_chain(")
    if c != 1:
        print("!! build_clue_chain 命中 %d ⇒ 不写盘" % c)
        sys.exit(2)
    t = t.replace("def build_clue_chain(", FUNC.lstrip(NL) + "def build_clue_chain(", 1)
    print("OK 已插入 _metrics_reading")

# ② 两处调用点加回落
n = t.count(OLD_CALL)
print("调用点命中 %d 处" % n)
if n == 0:
    print("!! 找不到调用点 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(OLD_CALL, NEW_CALL)
print("OK 已在 %d 处调用点加回落" % n)

io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 疑点5 D6 修法①已落地")
