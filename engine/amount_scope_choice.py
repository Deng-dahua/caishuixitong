# -*- coding: utf-8 -*-
"""金额口径取舍（Skill 2 唯一权威）：毛差额 / 净敞口 / 取舍依据。

## 为什么要它
用户复核（2026-10-07，疑点4「银行收款大于申报收入」）：
  报告同时写着「未开票/账外敞口（收款−申报侧）：**1,734,859.35** 元
  （剔除明显非销售流入后约 **227,659.35** 元）」——
  **两个口径并存、未指明哪个是最终风险敞口**，读者无法据以判断量级。

## 三条口径（本模块是它们的唯一解析点）
1. **毛差额（起点口径）**：不做任何性质甄别的原始差额（收款 − 申报侧）。
   作用 = **定位线索**；**不得**作为最终风险敞口（含大量非销售流入，会系统性高估）。
2. **净敞口（最终口径）**：剔除明显非销售流入后的差额。**报告的风险敞口只认它。**
3. **取舍依据**：为什么采用净敞口（逐项写明剔除了什么、依据什么资料）。

## 口径
- **只允许一个最终口径**：报告里出现多个金额时，必须由本模块 `choose()` 明确"谁是最终口径"，
  其余一律标注「仅作起点参考，不作为最终风险敞口」。
- **取不到净敞口时**（未做性质甄别）**不得**拿毛差额顶替充当最终口径 ——
  必须如实写「本轮未做性质甄别，净敞口未测算」，并保留毛差额作为**起点参考**。
- 本模块不负责"怎么算"（数值唯一权威是 `engine.numparse` 与各业务域），**只负责口径取舍与措辞**。
"""
from __future__ import annotations
from typing import Any, Dict, Optional

VERSION = "1.0.0"

LABEL_GROSS = "毛差额（起点口径）"
LABEL_FINAL = "净敞口（最终口径）"
NOTE_GROSS_ONLY = "仅作起点参考，不作为最终风险敞口。"
NOTE_FINAL = "本项风险敞口以**净敞口**为准。"
NOTE_NO_NET = ("本轮未做性质甄别，**净敞口未测算**；毛差额%s元仅作起点参考，"
               "不作为最终风险敞口。")


def _amount_opt(v: Any) -> Optional[float]:
    """宽松取数（仅用于展示占位，计算仍以业务域为准）：取不到返回 None，不返回 0。"""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        from engine.numparse import to_number_checked
        n, ok = to_number_checked(v)
        return float(n) if ok and n is not None else None
    except Exception:
        try:
            return float(str(v).replace(",", "").strip())
        except Exception:
            return None


def choose(gross: Any = None, net: Any = None, basis: str = "") -> Dict[str, Any]:
    """选出**唯一最终口径**。

    返回：
      `final`         最终风险敞口（float 或 None）
      `final_label`   最终口径名称
      `final_source`  net|gross|none
      `gross`         毛差额（起点口径，float 或 None）
      `gross_note`    毛差额的标注（非最终口径时**必填**说明）
      `basis`         取舍依据
    """
    g, n = _amount_opt(gross), _amount_opt(net)
    out: Dict[str, Any] = {"gross": g, "final": None, "final_label": LABEL_FINAL,
                           "final_source": "none", "gross_note": "", "basis": str(basis or "")}
    if n is not None:
        out.update({"final": n, "final_source": "net"})
        out["gross_note"] = NOTE_GROSS_ONLY if g is not None else ""
        if not out["basis"]:
            out["basis"] = "以剔除明显非销售流入后的净敞口为准（毛差额含非销售流入，会高估）。"
        return out
    if g is not None:
        # ★ 净敞口取不到 ⇒ **不得**拿毛差额顶替当最终口径
        out.update({"final": None, "final_source": "none",
                    "final_label": "净敞口（最终口径，本轮未测算）",
                    "gross_note": NOTE_NO_NET % f"{g:,.2f}",
                    "basis": out["basis"] or "本轮未做性质甄别，净敞口未测算。"})
        return out
    return out


def exposure_sentence(gross: Any = None, net: Any = None, basis: str = "",
                      item: str = "本项") -> str:
    """报告标准口径句（**禁止各处自写**）。"""
    c = choose(gross, net, basis)
    if c["final_source"] == "net":
        s = ("%s风险敞口（最终口径，净敞口）%s元（%s）" % (item, f'{c["final"]:,.2f}', c["basis"]))
        if c["gross"] is not None:
            s += "　起点口径（毛差额）%s元，%s" % (f'{c["gross"]:,.2f}', NOTE_GROSS_ONLY)
        return s
    if c["gross"] is not None:
        return "%s%s元；%s" % (item, f'{c["gross"]:,.2f}', c["gross_note"])
    return "%s金额本轮未取到（不填零、不顶替，须补资料后再测算）。" % item


def is_final_label(text: Any) -> bool:
    """该措辞是否声称自己是**最终口径**（供闸门核对：最终口径只能有一个）。"""
    s = str(text or "")
    return ("最终口径" in s) or ("风险敞口" in s and "起点" not in s and "参考" not in s)


__all__ = ["VERSION", "LABEL_GROSS", "LABEL_FINAL", "NOTE_GROSS_ONLY", "NOTE_FINAL",
           "NOTE_NO_NET", "choose", "exposure_sentence", "is_final_label"]
