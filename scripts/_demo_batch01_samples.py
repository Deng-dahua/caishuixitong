# -*- coding: utf-8 -*-
"""批次一「失败样例 / 通过样例」可复现脚本（Skill 1 触发条件与认定要件分离）。

## 为什么需要它
用户要求：失败样例与通过样例必须**来自实际运行**，不得推断；且要附**命令 + 输出**。
当前产物已是**修复后**状态 ⇒ 若直接跑门禁只会 0 ERROR（无法展示"修复前报出 4 处"）。
故本脚本**从当前产物还原修复前的缺陷状态**（把 4 个样点的第 1 条前提条结论改回
「未形成核对结论（资料已取得但缺本要件的对应核对证据）」以及把 `trigger_determination`
里的前提条状态同步改回），再跑**同一个门禁**，看它是否报出这 4 处 ——
即"同一个判据，喂修复前的数据会红，喂修复后的数据为绿"。

用法：
  ./.venv/Scripts/python.exe scripts/_demo_batch01_samples.py fail      # 失败样例（期望报 4 处）
  ./.venv/Scripts/python.exe scripts/_demo_batch01_samples.py pass      # 通过样例（期望 0 ERROR）
"""
from __future__ import annotations
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "scripts" / "four_reports" / "company_1_full.json"
#: 用户点名的 4 个样例：疑点编号 → 红线编号
SAMPLES = {1: "RL-VAT-007", 3: "RL-PAY-001", 4: "RL-INC-001", 12: "RL-AST-001"}
#: 修复前的前提条结论原文（实测自 2026-10-07 修复前产物）
OLD_TEXT = "未形成核对结论（资料已取得但缺本要件的对应核对证据，不作『未发现符合』认定）"


def _load() -> dict:
    return json.loads(REPORT.read_text(encoding="utf-8"))


def _revert_to_broken(rep: dict) -> int:
    """把 4 个样点还原成"前提条已满足却写未形成核对结论"的**修复前**状态。"""
    er = rep.get("enterprise_readable_report") or rep
    n = 0
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict) or p.get("seq") not in SAMPLES:
            continue
        # ① 要件核对表第1条
        for np_ in (p.get("narrative_paragraphs") or []):
            for t in (np_.get("detail_tables") or []):
                if "构成要件" not in str((t or {}).get("title") or ""):
                    continue
                for r in (t.get("rows") or []):
                    if isinstance(r, dict) and str(r.get("要件序号")) == "第1条":
                        r["核对结论"] = OLD_TEXT
                        n += 1
        # ② 结构化块里的 C1（与核对表同源，必须同步改，否则不成"修复前状态"）
        blk = p.get("trigger_determination")
        if isinstance(blk, dict):
            cst = blk.get("criterion_status") or {}
            if "C1" in cst:
                cst["C1"]["status"] = "not_concluded"
                cst["C1"]["text"] = OLD_TEXT
        # ③ 要件 bullet 的第1条
        for np_ in (p.get("narrative_paragraphs") or []):
            for i, b in enumerate(np_.get("bullets") or []):
                s = str(b or "")
                if s.startswith("①") and "符合情形" in s:
                    np_["bullets"][i] = s.replace("符合情形（这项属于现象/前提条，存在即成立）",
                                                  OLD_TEXT)
    return n


def main() -> int:
    mode = (sys.argv[1] if len(sys.argv) > 1 else "pass").strip().lower()
    rep = _load()
    if mode == "fail":
        n = _revert_to_broken(rep)
        print("[还原] 已把 4 个样点的第1条前提条结论改回修复前状态（改 %d 处核对结论）" % n)
    else:
        print("[原样] 使用**修复后**的真实产物（不做任何还原）")
    import tools.audit_consistency as A
    A._canonical_report = lambda: rep            # 注入本次输入（同一判据）
    iss = A.check_trigger_determination_separation()
    errs = [i for i in iss if i[0] == "ERROR"]
    print("输入=%s ｜ 门禁 check_trigger_determination_separation() → ERROR %d / WARN %d"
          % (Path(REPORT).name, len(errs), len(iss) - len(errs)))
    for i in errs:
        print("  ERROR  %s" % str(i[2]))
    # 逐样点判定
    er = rep.get("enterprise_readable_report") or rep
    print("\n逐样点判定：")
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict) or p.get("seq") not in SAMPLES:
            continue
        blk = p.get("trigger_determination") or {}
        c1 = (blk.get("criterion_status") or {}).get("C1") or {}
        txt = str(c1.get("text") or "")
        ok = ("符合情形" in txt) and ("未形成核对结论" not in txt)
        print("  疑点%-3s %-12s C1前提条=%-5s 结论=%s ｜ 判定=%s"
              % (p.get("seq"), blk.get("risk_code"), c1.get("is_precondition"),
                 txt[:30], "通过" if ok else "不通过（前提条未写「符合情形」）"))
    return 0 if (len(errs) == 4 if mode == "fail" else len(errs) == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
