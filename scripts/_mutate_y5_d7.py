# -*- coding: utf-8 -*-
"""疑点5 · D7：环节声称的「对应资料」必须与**实际取数来源**一致。

★ 根因（读码确认）：`clue_chain` 的 `template = list(redline.get("clue_chain") or [])`
  ⇒ 环的 `source` 是**红线模板里写死的静态声明**，直接 `"source": tpl.get("source", "")` 照抄。
  同一函数里 `_gap_reason()` **已经**用 `materials_available(source, provided_materials)`
  判定「该资料到底有没有提供」——**机制已存在，只是没用来校正显示**。
  ⇒ 事故：环2 声称「对应资料＝利润表（收入、利润总额、工资总额）」，
    而证据表写「利润总额计算底稿未逐字见到」——**声称的来源与实际取数不符**（D7）。

修法（只改显示，不改判定）
------------------------
新增 `_src_disp(source_text)`：该资料**已提供** ⇒ 原样显示；
**未提供** ⇒ 追加「（本轮未提供）」如实标注。
两处 `"source": tpl.get("source", "")` 全部改用它（保持**单行**，不破坏缩进）。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
P = os.path.join(ROOT, "engine", "clue_chain.py")

HELPER = '''    def _src_disp(_s: str) -> str:
        """环节「对应资料」的显示：**已提供**原样；**未提供**如实标注（本轮未提供）。

        ★ 2026-08-05（疑点5 D7）：环的 `source` 原本是**红线模板写死的静态声明**，
          与实际取数来源可能不符（实测环2 声称「利润表…」而证据表写「底稿未逐字见到」）。
          同一函数已有 `materials_available` 判资料有无的能力，这里只用于**校正显示**，
          **不改任何判定**。
        """
        _t = str(_s or "").strip()
        if not _t:
            return _t
        try:
            _ok, _miss = materials_available(_t, provided_materials)
        except Exception:  # noqa: BLE001
            return _t
        if _ok or not _miss:
            return _t
        return _t + "\uff08\u672c\u8f6e\u672a\u63d0\u4f9b\uff09"

'''

OLD_CALL = '                    "source": tpl.get("source", ""),' + NL
NEW_CALL = '                    "source": _src_disp(tpl.get("source", "")),' + NL
OLD_CALL2 = '                    "source": tpl.get("source", ""),' + NL
ANCHOR_HELPER = '    if template:' + NL

raw = io.open(P, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)

# ① 插 helper（放在 `if template:` 之前，函数级缩进 4）
c_h = t.count(ANCHOR_HELPER)
print("helper 锚点命中 =", c_h)
if c_h != 1:
    print("!! helper 锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(ANCHOR_HELPER, HELPER + ANCHOR_HELPER, 1)

# ② 两处 source 显示（全量、保持单行缩进）
n1 = t.count('"source": tpl.get("source", ""),')
print("source 赋值命中 =", n1)
if n1 == 0:
    print("!! source 锚点异常 ⇒ 不写盘")
    sys.exit(2)
t = t.replace('"source": tpl.get("source", ""),', '"source": _src_disp(tpl.get("source", "")),')
io.open(P, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("[DONE] 疑点5 D7：环节对应资料已加实际取数校验（共改 %d 处）" % n1)
