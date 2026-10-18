# -*- coding: utf-8 -*-
"""法规时效校验 —— 「引用是否还能用」的**唯一判定入口**。

★★ 2026-10-18 重写（META-SYSTEM-COMPLETENESS-AUDIT / GAP-02）

原实现的四个致命缺陷（均已实测复现，修复后各配反向用例）：
  1. **把现行法本身当废止条目**：`DEPRECATED_LAWS` 里有 `"增值税法"`，
     于是 `check_law_validity("《中华人民共和国增值税法》第二十一条")` 返回
     `valid=False, alert=ERROR, suggested=中华人民共和国增值税法` —— 现行法被判死。
  2. **无序子串匹配**：`"土地增值税暂行条例"` 先被 `"增值税暂行条例"` 吃掉，
     生成合成词「土地中华人民共和国增值税法」；字典里为它写的条目**永不可达**。
  3. **造出不存在的法名**：`"房产税暂行条例" → "中华人民共和国房产税法"`（该法不存在，
     映射表自己的备注写着"待审议"）。房产税至今仍适用 1986 年暂行条例且登记为 current。
  4. **裸 `str.replace` 不看上下文**：已带「中华人民共和国」前缀的引用被替换成
     「中华人民共和国**中华人民共和国**增值税法」。

★★ 现在的口径（三层，互斥）
  | 层 | 触发条件 | 动作 |
  |---|---|---|
  | `replace`   | 法规**确已废止**且**确有现行替代法**（两张表都在） | 改写为替代法名（幂等、长名优先） |
  | `warn_only` | 未登记 / 已废止但无替代法 / 状态为 amended | **不改写**，只回执告警（人工核对） |
  | `noop`      | 版本登记为 current | 什么都不做 |
  「全称规范化」（如「增值税法」→「中华人民共和国增值税法」）**不属于废止**，
  由 `legal_version.canonical_law()` 负责，本模块**不当作废止**。

★★ 单一权威
  `config/legal_versions.json` 的 `status` 是**唯一状态来源**（经 `engine/legal_version`）。
  本模块的 `REPLACEMENT_TARGETS` 只补一件版本表没有的信息：**废止后由哪部法承接**。
  ⇒ 新增一部废止法：先在版本表登记 status，再（若确有承接法）在 `REPLACEMENT_TARGETS` 加一行。
  ⇒ 只加版本表、不加减接表 ⇒ 自动降级为 `warn_only`（不改写、只告警），不会静默放过。

★ 反向验证（`tests/test_law_validity_rewrite.py`）：
  · 现行法名不得被判 `is_deprecated`
  · 「土地增值税暂行条例」必须整体命中它自己，不得被拆
  · 「房产税暂行条例」不得被改名
  · 已带全称前缀不得重复叠加
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Dict, List, Tuple

# ★ 允许 `python engine/law_validity_checker.py` 自检（否则 `engine.legal_version` 导入失败 ⇒
#   所有状态被判 unknown ⇒ 全部降级为 warn_only，看着"安全"其实是瞎的）。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ═════════ 废止法 → 承接法（版本表没有的信息，只此一处） ═════════
# 格式："已废止/被替代的名称（含简称）": (承接法名, 施行日期, 备注)
# ★ 铁律：右侧必须是**真实存在且现行有效**的法名；确无承接法时写 ""（走 warn_only）。
# ★ 铁律：不得把「现行法」写进这张表（那会让现行法被判死）。
REPLACEMENT_TARGETS: Dict[str, Tuple[str, str, str]] = {
    # ── 增值税（2026-01-01《增值税法》施行，原条例及细则废止）──
    "增值税暂行条例实施细则": ("中华人民共和国增值税法实施条例", "2026-01-01", "原细则随条例废止"),
    "中华人民共和国增值税暂行条例实施细则": ("中华人民共和国增值税法实施条例", "2026-01-01", "原细则随条例废止"),
    # ★ 长名必须排在短名之前（虽然命中逻辑已按长度排序，这里保持可读性）
    "中华人民共和国增值税暂行条例": ("中华人民共和国增值税法", "2026-01-01", "原条例全文废止"),
    "增值税暂行条例": ("中华人民共和国增值税法", "2026-01-01", "原条例全文废止"),
    "增值税条例": ("中华人民共和国增值税法", "2026-01-01", "原条例全文废止"),

    # ── 营业税（营改增后废止，无单行承接法）──
    "中华人民共和国营业税暂行条例": ("", "2016-05-01", "营改增后全文废止，无单行承接法"),
    "营业税暂行条例": ("", "2016-05-01", "营改增后全文废止，无单行承接法"),

    # ── 已上升为法律的税种（原暂行条例废止）──
    "城建税暂行条例": ("中华人民共和国城市维护建设税法", "2021-09-01", "原暂行条例全文废止"),
    "城市维护建设税暂行条例": ("中华人民共和国城市维护建设税法", "2021-09-01", "原暂行条例全文废止"),
    "印花税暂行条例": ("中华人民共和国印花税法", "2022-07-01", "原暂行条例全文废止"),
    "资源税暂行条例": ("中华人民共和国资源税法", "2020-09-01", "原暂行条例全文废止"),
    "契税暂行条例": ("中华人民共和国契税法", "2021-09-01", "原暂行条例全文废止"),
    "车辆购置税暂行条例": ("中华人民共和国车辆购置税法", "2019-07-01", "原暂行条例全文废止"),
    "耕地占用税暂行条例": ("中华人民共和国耕地占用税法", "2019-09-01", "原暂行条例全文废止"),
}

#: 兼容旧名（既有调用点用 `DEPRECATED_LAWS`）：**只含真废止条目**，
#: 值结构与旧版一致 (承接法, 施行日, 备注)。空承接法用 "(已废止-无承接法)" 表示。
DEPRECATED_LAWS: Dict[str, Tuple[str, str, str]] = {
    old: (tgt or "(已废止-无承接法)", date, note)
    for old, (tgt, date, note) in REPLACEMENT_TARGETS.items()
}

#: 「暂行但现行有效」的法规（不得改名、不得判废止，只提示"名暂行而有效"）
#: ★ 只列**版本表登记为 current** 的暂行条例；新增须先在 `config/legal_versions.json` 核对。
PROVISIONAL_BUT_CURRENT = (
    "房产税暂行条例",
    "城镇土地使用税暂行条例",
    "土地增值税暂行条例",
    "增值税法",              # 不是暂行条例，此处仅为"不得当作废止"的显式登记
)

#: 明显的引用体例错误（不是法律名，而是法律附件/条款名）——只告警，不改写
_CITATION_STYLE_ERRORS = ("税目税率表",)

_PREFIX_CN = "中华人民共和国"
_ENGAGED = False


# --------------------------------------------------------------------------
# 版本状态（唯一权威 = config/legal_versions.json，经 engine.legal_version）
# --------------------------------------------------------------------------
def _status(law: str) -> str:
    try:
        from engine.legal_version import status_of          # noqa: PLC0415
        return status_of(law)
    except Exception:                                       # noqa: BLE001
        return "unknown"


def _is_dead_status(st: str) -> bool:
    """只有 expired / superseded 才可能触发改写（amended 属"部分修改"，不改写）。"""
    return st in ("expired", "superseded")


def _sorted_targets() -> List[Tuple[str, Tuple[str, str, str]]]:
    """按 **key 长度降序** 排列 —— 保证「土地增值税暂行条例」先于「增值税暂行条例」被检查。

    ★ 这是修复"合成词"缺陷的核心：旧实现按 dict 插入序，"增值税暂行条例"在前，
      于是「土地增值税暂行条例」被切成「土地」+「增值税暂行条例」。
    """
    return sorted(REPLACEMENT_TARGETS.items(), key=lambda kv: -len(kv[0]))


def _is_cjk(ch: str) -> bool:
    """是否汉字（含扩展区）—— 用于判定"命中的是不是更短的同尾名"。"""
    return bool(ch) and ("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf")


def _hits(text: str, old: str) -> bool:
    """`old` 是否作为**独立法名**出现在 `text` 中。

    ★ 关键：不能用裸 `old in text`。否则「增值税暂行条例」会命中
      「中华人民共和国**土地**增值税暂行条例」的尾部 ⇒
      ① 告警指向错误对象；② 若土地增值税将来被废止，会把它误改。
    判据：每个出现位置的**前一个字符不得是汉字**（后面的字符不限，允许「》」「第X条」等）。
    """
    start = 0
    while True:
        pos = text.find(old, start)
        if pos < 0:
            return False
        if pos == 0 or not _is_cjk(text[pos - 1]):
            return True
        start = pos + 1


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------
def check_law_validity(law_text: str) -> Dict:
    """检查一条法规引用是否可继续使用。

    返回 `{valid, action, alert, suggested, reason, matched}`：
      `action` ∈ {`noop`, `warn_only`, `replace`} —— **调用方按 action 决定要不要改写**。
      （旧版只有 `valid` 布尔，调用方无从区分"要改"与"只需要提示"，是本轮缺陷 1/3 的成因。）
    """
    text = str(law_text or "")
    out = {"valid": True, "action": "noop", "alert": "OK",
           "suggested": text, "reason": "", "matched": ""}

    # ① 体例错误（不是法名）——最高优先，且**不改写**
    for bad in _CITATION_STYLE_ERRORS:
        if bad in text:
            return {**out, "valid": False, "action": "warn_only", "alert": "WARN",
                    "reason": "引用体例错误：「%s」不是法律名称（应为法条或附件条款），须人工改写" % bad,
                    "matched": bad}

    # ② 暂行但现行有效 —— 显式 NOTE，绝不改写
    for name in PROVISIONAL_BUT_CURRENT:
        if _hits(text, name) and _status(name) == "current":
            return {**out, "valid": True, "action": "noop", "alert": "NOTE",
                    "reason": "虽冠名「暂行」但现行有效（版本表 status=current），保留原名不改写",
                    "matched": name}

    # ③ 真废止：长名优先，且两条都要成立（版本表已死 + 有承接法）
    for old, (target, date, note) in _sorted_targets():
        if not _hits(text, old):
            continue
        st = _status(old)
        if not _is_dead_status(st):
            # 版本表说它还活着（或未登记）⇒ 不信本表，降级告警
            return {**out, "valid": True, "action": "warn_only", "alert": "WARN",
                    "reason": "「%s」的版本登记状态为 %s，不做自动改写；如确认已废止请先更新 config/legal_versions.json"
                              % (old, st),
                    "matched": old}
        if not target:
            return {**out, "valid": False, "action": "warn_only", "alert": "ERROR",
                    "reason": "「%s」已于 %s 废止，且无单行承接法（%s）；**不得直接改写**，须人工改为具体政策依据"
                              % (old, date, note or ""),
                    "matched": old}
        return {**out, "valid": False, "action": "replace", "alert": "ERROR",
                "suggested": target,
                "reason": "「%s」已于 %s 废止（%s）→ 承接法「%s」" % (old, date, note or "", target),
                "matched": old}

    # ④ 未登记的法名：如实说明，不改写（★ 必须先拆引用，不能把「法名+条号」当法名去查）
    try:
        from engine.legal_citation import split_citations      # noqa: PLC0415
        from engine.legal_version import entry_of              # noqa: PLC0415
        cites = split_citations(text) or []
        unknown = [c[0] for c in cites if c and c[0] and entry_of(c[0]) is None]
        if unknown:
            return {**out, "valid": True, "action": "warn_only", "alert": "NOTE",
                    "reason": "「%s」未在 config/legal_versions.json 登记，无法判定现行有效性，须人工核对"
                              % "、".join(sorted(set(unknown))),
                    "matched": unknown[0]}
    except Exception:                                       # noqa: BLE001
        pass
    return out


def is_deprecated(law_text: str) -> bool:
    """是否**确已废止**（只有 action=replace 或"废止且无承接法"才算 True）。

    ★ 与旧版的区别：旧版把「增值税法」判 True（现行法被判死），本版不会。
    """
    r = check_law_validity(law_text)
    return r["alert"] == "ERROR"


def get_valid_citation(text: str) -> Tuple[str, bool, str]:
    """(修正后文本, 是否改动, 说明)。**只有 action=replace 才改动。**"""
    r = check_law_validity(text)
    if r["action"] == "replace":
        return apply_replacements(text)[0], True, r["reason"]
    return text, False, r["reason"]


# --------------------------------------------------------------------------
# 安全改写（幂等 + 长名优先 + 不重复前缀）
# --------------------------------------------------------------------------
def _already_full_name(text: str, target: str) -> bool:
    """文本里是否**已经**是这个全称（避免把「中华人民共和国增值税法」再包一层）。"""
    if target in text:
        return True
    # target = 中华人民共和国X，文本里出现 X 且紧邻前面已有「中华人民共和国」
    if target.startswith(_PREFIX_CN):
        short = target[len(_PREFIX_CN):]
        return (_PREFIX_CN + short) in text
    return False


def _replace_all(text: str, old: str, repl: str) -> Tuple[str, int]:
    """**只替换独立法名**的所有出现（跳过"嵌在更长法名里"的那些）。返回 (新文本, 次数)。

    从右往左替换 ⇒ 位置下标不会因为长度变化而失效。
    """
    positions = []
    start = 0
    while True:
        pos = text.find(old, start)
        if pos < 0:
            break
        if pos == 0 or not _is_cjk(text[pos - 1]):
            positions.append(pos)
        start = pos + 1
    for pos in reversed(positions):
        text = text[:pos] + repl + text[pos + len(old):]
    return text, len(positions)


def apply_replacements(text: str) -> Tuple[str, List[Dict]]:
    """对一段引用文本执行**安全的**废止替换。

    返回 `(新文本, 替换明细)`。三条不变式：
      1. **幂等**：对结果再跑一次，替换明细必为空；
      2. **长名优先 + 独立法名**：不命中「土地增值税暂行条例」里的「增值税暂行条例」；
      3. **不叠前缀**：已含承接法全称时不再替换（旧版的「中华人民共和国中华人民共和国」由此消失）。
    """
    src = str(text or "")
    applied: List[Dict] = []
    if not src:
        return src, applied

    # 占位替换：把命中片段换成不可读的哨兵，避免后续规则二次命中（长名优先的前提）
    work = src
    for i, (old, (target, date, note)) in enumerate(_sorted_targets()):
        if not _hits(work, old):
            continue
        st = _status(old)
        if not _is_dead_status(st) or not target:
            continue
        if _already_full_name(work, target):
            continue
        sentinel = "\x00%d\x00" % i
        work, n = _replace_all(work, old, sentinel)
        if not n:
            continue
        applied.append({"found": old, "suggested": target, "date": date,
                        "note": note, "severity": "ERROR", "count": n,
                        "action": "replace"})
    # 回填
    for i, item in enumerate(_sorted_targets()):
        work = work.replace("\x00%d\x00" % i, item[1][0])
    return work, applied


def scan_text(text: str) -> List[Dict]:
    """扫描文本中的法规引用，返回全部发现（含 `action`，供调用方决定改不改）。

    ★ 与旧版区别：旧版**无条件**返回 suggested 并让 pipeline 裸替换；
      本版对 `warn_only` 项 `suggested` 等于 `found`（即"不要动它"）。
    """
    src = str(text or "")
    findings: List[Dict] = []
    if not src:
        return findings

    for old, (target, date, note) in _sorted_targets():
        if not _hits(src, old):
            continue
        st = _status(old)
        if _is_dead_status(st) and target:
            findings.append({"found": old, "suggested": target, "date": date,
                             "note": note, "severity": "ERROR", "action": "replace"})
        else:
            findings.append({"found": old, "suggested": old, "date": date,
                             "note": note or ("版本登记状态=%s" % st),
                             "severity": "WARN", "action": "warn_only"})

    for bad in _CITATION_STYLE_ERRORS:
        if bad in src:
            findings.append({"found": bad, "suggested": bad, "date": "",
                             "note": "引用体例错误：不是法律名称", "severity": "WARN",
                             "action": "warn_only"})
    return findings


class LawValidityCache:
    """兼容旧接口的缓存壳（判定逻辑全在模块级函数，本类不再持有第二套规则）。"""

    def is_deprecated(self, law_text: str) -> bool:
        return is_deprecated(law_text)

    def get_replacement(self, old_law: str) -> str:
        r = check_law_validity(old_law)
        return r["suggested"] if r["action"] == "replace" else old_law

    def scan_text(self, text: str) -> List[Dict]:
        return scan_text(text)


_law_cache = LawValidityCache()


def init_law_checker():
    """兼容旧调用：确保版本表缓存已就绪。"""
    try:
        from engine.legal_version import reset_caches      # noqa: PLC0415
        reset_caches()
    except Exception:                                       # noqa: BLE001
        pass
    return _law_cache


# --------------------------------------------------------------------------
# 批量修复工具（人工触发的离线脚本用，运行期**不得**调用）
# --------------------------------------------------------------------------
def batch_fix_law_refs_in_files(file_paths: List[str], dry_run: bool = True) -> Dict:
    """批量修复指定文件中的过期法规引用（只做 `action=replace` 的项）。"""
    results = {}
    for fp in file_paths:
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, "r", encoding="utf-8") as fh:
                content = fh.read()
            new_content, applied = apply_replacements(content)
            fixed_count = sum(a.get("count", 0) for a in applied)
            if fixed_count > 0 and not dry_run:
                with open(fp, "w", encoding="utf-8") as fh:
                    fh.write(new_content)
                if fp.endswith(".json"):
                    json.loads(new_content)
            results[os.path.basename(fp)] = {
                "fixed_count": fixed_count,
                "details": ["%s→%s (%d处)" % (a["found"], a["suggested"], a["count"])
                            for a in applied],
                "dry_run": dry_run,
            }
        except Exception as exc:                            # noqa: BLE001
            results[os.path.basename(fp)] = {"error": str(exc)}
    return results


if __name__ == "__main__":
    for t in ("《中华人民共和国增值税法》第二十一条",
              "《中华人民共和国土地增值税暂行条例》第七条",
              "《房产税暂行条例》第二条",
              "《增值税暂行条例》第十九条",
              "《营业税暂行条例》第五条",
              "《印花税法》税目税率表"):
        r = check_law_validity(t)
        print("%-46s %-9s %-6s %s" % (t, r["action"], r["alert"], r["reason"][:70]))
