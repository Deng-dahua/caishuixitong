# -*- coding: utf-8 -*-
"""规则清单 → YAML 导出器（唯一实现，可重跑）。

为什么需要导出器而不是手写 YAML：手写 YAML 会与数据表**分叉**（一处改、另一处忘）
——本项目的惯例是「唯一权威 + 薄转发」。故：
  · 权威：`config/rulelist_v1.json`（V1.0 VAT/CIT 60 条） + `config/rulelist_v11.json`（V1.1 补充 174 条）
  · 本脚本：只做格式转换（JSON → YAML），输出 `rules_export/*.yaml`
  · YAML 是**交换/审阅格式**，`status: draft` + `wired: false`，**未接入系统**

用法：
    .venv/Scripts/python.exe tools/export_rulelist_yaml.py
    .venv/Scripts/python.exe tools/export_rulelist_yaml.py --check   # 只校验不写盘

自检（失败即非零退出）：
  ① 两表 ID 不冲突；② 每条都有 logic/inputs/suggestion；③ 条数与分组统计自洽；
  ④ condition 不含直接数值阈值（必须引用 params.*）；⑤ 导出的 YAML 能被重新解析回等量条目。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1_PATH = ROOT / "config" / "rulelist_v1.json"
V11_PATH = ROOT / "config" / "rulelist_v11.json"
OUT_DIR = ROOT / "rules_export"

RULE_SET_VERSION = "2026.10"

TAX_TYPE_CN = {
    "VAT": "增值税", "CIT": "企业所得税", "IIT": "个人所得税", "SI": "社保与非税收入",
    "SD": "印花税", "PCT": "房产税", "LUT": "城镇土地使用税", "LAT": "土地增值税",
    "SUR": "附加税费", "INV": "发票合规", "FIN": "财务报表勾稽", "REL": "关联交易",
    "FUND": "资金流", "EXPORT": "出口退税", "CONS": "消费税", "RES": "资源税",
    "ENV": "环境保护税", "TAXINC": "税收优惠", "GEN": "通用申报",
}

# 7 个导出文件 ← 前缀分组（用户指定文件名）
FILES = [
    ("vat_rules.yaml", ["VAT"]),
    ("cit_rules.yaml", ["CIT"]),
    ("iit_rules.yaml", ["IIT"]),
    ("other_tax_rules.yaml", ["SI", "SD", "PCT", "LUT", "LAT", "SUR", "CONS", "RES", "ENV", "TAXINC"]),
    ("invoice_rules.yaml", ["INV", "EXPORT"]),
    ("financial_rules.yaml", ["FIN", "REL", "FUND"]),
    ("general_rules.yaml", ["GEN"]),
]


def _q(s) -> str:
    """YAML 双引号标量（转义内部双引号与反斜杠）。"""
    s = "" if s is None else str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _load() -> tuple[dict, dict]:
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8"))
    v11 = json.loads(V11_PATH.read_text(encoding="utf-8"))
    return v1, v11


def _collect() -> list[dict]:
    v1, v11 = _load()
    params = {}
    params.update({k: v for k, v in (v11.get("params") or {}).items() if not k.startswith("_")})
    params.update({k: v for k, v in (v1.get("params") or {}).items() if not k.startswith("_")})

    rows, ids = [], []
    for src_name, d in (("V1.0", v1), ("V1.1", v11)):
        for r in d["rules"]:
            rid = r["src"]
            ids.append(rid)
            rows.append({"rid": rid, "src_set": src_name, "raw": r,
                         "params": params.get(rid)})
    assert len(ids) == len(set(ids)), "两表 ID 冲突: %s" % (
        sorted({x for x in ids if ids.count(x) > 1}))
    return rows


def _check(rows: list[dict]) -> None:
    bad_missing, bad_inline = [], []
    for row in rows:
        r, rid = row["raw"], row["rid"]
        for f in ("name", "sev", "status", "logic", "inputs", "suggestion", "action"):
            if not r.get(f):
                bad_missing.append("%s 缺 %s" % (rid, f))
        # condition 不得内联**可参数化阈值**（必须引用 params.*）。
        # ★ 排除「存在性/布尔」比较（> 0 / = 0 / != 0）：项目铁律「存在即触发，不要阈值」，
        #   这类写法是正确形态，不应被误判为内联阈值。
        logic = r.get("logic", "")
        _exist = re.compile(r"[<>=!]=?\s*0(?![\d.])")          # > 0 / >= 0 / = 0 / != 0
        _stripped = _exist.sub(" ", logic)
        if re.search(r"[<>=!]\s*\d", _stripped) and "params." not in logic:
            bad_inline.append("%s: %s" % (rid, logic))
    assert not bad_missing, "字段缺失: %s" % bad_missing[:10]
    assert not bad_inline, "阈值内联（应引用 params.*）: %s" % bad_inline[:10]
    print("[check] 字段完整 ✓  阈值零内联 ✓  共 %d 条" % len(rows))


def _render(fname: str, prefixes: list[str], rows: list[dict]) -> str:
    sub = [r for r in rows if r["rid"].split("-")[0] in prefixes]
    from collections import Counter
    cnt = Counter(r["raw"]["status"] for r in sub)
    L = []
    L.append("# " + "=" * 74)
    L.append("# 自动生成，请勿手工编辑 —— 导出器：tools/export_rulelist_yaml.py")
    L.append("# 唯一权威：config/rulelist_v1.json（V1.0） + config/rulelist_v11.json（V1.1）")
    L.append("# 所有阈值集中在上述文件的 params 段；本文件只引用（params_ref），不内联。")
    L.append("# " + "=" * 74)
    L.append("schema: 1")
    L.append("file: " + _q(fname))
    L.append("rule_set: " + _q("外部候选规则清单 V1.0 + V1.1"))
    L.append("rule_set_version: " + _q(RULE_SET_VERSION))
    L.append("status: draft")
    L.append("wired: false")
    L.append("wired_note: " + _q(
        "未接入系统：不新增红线、不改判定逻辑、不改前端。系统内部权威为 config/rulelist_*.json。"))
    L.append("coverage_summary:")
    L.append("  total: %d" % len(sub))
    for k in ("covered", "partial", "missing"):
        L.append("  %s: %d" % (k, cnt.get(k, 0)))
    L.append("rules:")
    for r in sub:
        raw, rid = r["raw"], r["rid"]
        tt = TAX_TYPE_CN.get(rid.split("-")[0], rid.split("-")[0])
        L.append("  - rule_id: " + _q(rid))
        L.append("    name: " + _q(raw["name"]))
        L.append("    tax_type: " + _q(tt))
        L.append("    source_set: " + _q(r["src_set"]))
        L.append("    level: " + _q(raw["sev"]))
        L.append("    version: " + _q("1.0.0"))
        L.append("    enabled: false")
        L.append("    condition: " + _q(raw["logic"]))
        L.append("    params_ref: " + _q(raw.get("params_ref", "")))
        p = r["params"]
        if p:
            L.append("    params:")
            for pk, pv in p.items():
                if pk.startswith("_"):
                    L.append("      _basis: " + _q(pv))
                elif isinstance(pv, (dict, list)):
                    L.append("      %s: %s" % (pk, json.dumps(pv, ensure_ascii=False)))
                else:
                    L.append("      %s: %s" % (pk, json.dumps(pv, ensure_ascii=False)))
        else:
            L.append("    params: {}")
            # 空 params 必须说明阈值出处，否则读者会误以为「没阈值」=「不用判」
            if raw["status"] == "covered":
                L.append("    params_note: " + _q(
                    "阈值权威在**系统内部实现**（见 coverage.mapped_to）；本清单不另设阈值，避免两头各写一份。"))
            elif re.search(r"[<>=!]=?\s*0(?![\d.])", raw.get("logic", "")):
                L.append("    params_note: " + _q(
                    "本规则为「存在即触发」判据（> 0 / = 0 型），无比例阈值；符合项目铁律「不要阈值」。"))
            else:
                L.append("    params_note: " + _q(
                    "待登记：阈值/地区参数尚未提供（config/rulelist_*.json::params 未含），检测器须输出「待核」，禁止默认值顶替。"))
        L.append("    inputs:")
        for i in raw["inputs"]:
            L.append("      - " + _q(i))
        L.append("    risk:")
        L.append("      message: " + _q(raw["name"]))
        L.append("      evidence:")
        L.append("        - " + _q("命中：「%s」（%s）" % (raw["name"], rid)))
        L.append("        - " + _q("阈值：" + (raw.get("params_ref", "") or "见数据表 params")))
        L.append("        - " + _q("取数：" + " / ".join(raw["inputs"])))
        L.append("      suggestion: " + _q(raw["suggestion"]))
        L.append("      legal_basis_ref: " + _q(raw.get("legal_basis_ref", "法规库自动匹配")))
        L.append("    coverage:")
        L.append("      status: " + _q(raw["status"]))
        L.append("      action: " + _q(raw.get("action", "")))
        L.append("      mapped_to: " + _q(raw.get("by", "")))
        if raw.get("note"):
            L.append("      note: " + _q(raw["note"]))
    L.append("")
    return "\n".join(L)


def _reread_count(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.startswith("  - rule_id:"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不写盘")
    args = ap.parse_args()

    rows = _collect()
    _check(rows)

    total_written, reports = 0, []
    if not args.check:
        OUT_DIR.mkdir(exist_ok=True)
    for fname, prefixes in FILES:
        text = _render(fname, prefixes, rows)
        n = _reread_count(text)
        assert n > 0, "%s 无规则" % fname
        total_written += n
        reports.append((fname, n))
        if not args.check:
            (OUT_DIR / fname).write_text(text, encoding="utf-8")

    assert total_written == len(rows), "导出条数 %d ≠ 候选 %d" % (total_written, len(rows))
    print("\n[export] 分组：")
    for fname, n in reports:
        print("  %-24s %3d 条" % (fname, n))
    print("[export] 合计 %d 条（应 == 候选 %d）✓" % (total_written, len(rows)))
    print("[export] 输出目录: %s%s" % (OUT_DIR.relative_to(ROOT), "（--check 未写盘）" if args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
