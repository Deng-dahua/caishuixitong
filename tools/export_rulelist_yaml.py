# -*- coding: utf-8 -*-
"""规则清单 → YAML 导出器（唯一实现，可重跑）。覆盖 V1.0 + V1.1 + V1.2。

为什么需要导出器而不是手写 YAML：手写 YAML 会与数据表**分叉**（一处改、另一处忘）
——本项目的惯例是「唯一权威 + 薄转发」。故：
  · 权威：`config/rulelist_v1.json`（V1.0 VAT/CIT 60 条）
         + `config/rulelist_v11.json`（V1.1 补充 174 条）
         + `config/rulelist_v12.json`（V1.2 补充 224 条）
  · 本脚本：只做格式转换（JSON → YAML），输出 `rules_export/*.yaml`
  · YAML 是**交换/审阅格式**，`status: draft` + `wired: false`，**未接入系统**

★ 前缀唯一归属：每个命名空间前缀**只属于一个输出文件**，避免同一前缀跨文件分叉。
  两个例外通过「额外 ID / 排除 ID」显式声明（FUND-011 归 finance，FUND-001~010 归 financial；
  EXPORT 整体归 customs_export，故 invoice_rules.yaml 只留 INV）。

用法：
    .venv/Scripts/python.exe tools/export_rulelist_yaml.py
    .venv/Scripts/python.exe tools/export_rulelist_yaml.py --check   # 只校验不写盘

自检（失败即非零退出）：
  ① 三表 ID 不冲突；② 每条都有 logic/inputs/suggestion；③ 各表 stats 与实测计数一致；
  ④ condition 不含可参数化阈值（须引用 params.*；`> 0`/`= 0` 属存在性判据，豁免）；
  ⑤ 前缀唯一归属（无前缀落在两个文件）；⑥ 导出条数 == 候选总数。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    ("V1.0", ROOT / "config" / "rulelist_v1.json"),
    ("V1.1", ROOT / "config" / "rulelist_v11.json"),
    ("V1.2", ROOT / "config" / "rulelist_v12.json"),
]
OUT_DIR = ROOT / "rules_export"
RULE_SET_VERSION = "2026.10"

TAX_TYPE_CN = {
    "VAT": "增值税", "CIT": "企业所得税", "IIT": "个人所得税", "SI": "社保与非税收入",
    "SD": "印花税", "PCT": "房产税", "LUT": "城镇土地使用税", "LAT": "土地增值税",
    "SUR": "附加税费", "INV": "发票合规", "FIN": "财务报表勾稽", "REL": "关联交易",
    "FUND": "资金流", "EXPORT": "出口退税", "CONS": "消费税", "RES": "资源税",
    "ENV": "环境保护税", "TAXINC": "税收优惠", "GEN": "通用申报",
    "DEED": "契税", "GOT": "耕地占用税", "VET": "车船税", "VPT": "车辆购置税", "CUS": "关税",
    "TON": "船舶吨税", "TOB": "烟叶税", "CUL": "文化事业建设费", "WAT": "水利建设基金",
    "ADM": "税收征管与申报", "AA": "反避税与转让定价", "INT": "国际税收与非居民",
    "REO": "企业重组与资本交易", "EST": "房地产", "CONSTR": "建筑安装",
    "PLAT": "平台经济", "FLEX": "灵活用工", "HNW": "高净值个人",
    "FINA": "金融", "LEASE": "融资租赁", "FACT": "保理", "MICRO": "小额贷款", "GUAR": "担保",
    "PAWN": "典当", "PE": "私募基金", "FUNDM": "公募基金", "TRUST": "信托", "REIT": "REITs",
    "PPP": "PPP", "EPC": "EPC", "BOT": "BOT", "ABS": "资产证券化",
    "CUSTOMS": "海关", "BOND": "保税", "FTZ": "自贸区", "HAINAN": "海南自贸港",
    "ASSESS": "核定征收", "LIQ": "注销清算", "BANKR": "破产重整",
    "EINV": "电子发票", "RRT": "留抵退税",
    "HNTECH": "高新技术企业", "RD": "研发", "SOFT": "软件企业", "IC": "集成电路",
    "ANIME": "动漫", "CULT": "文化企业", "EDU": "教育", "MED": "医疗", "ELDER": "养老",
    "CHILD": "托育", "HOUSE": "家政", "SPORT": "体育", "TOUR": "旅游", "HOTEL": "住宿",
    "CATER": "餐饮", "ENT": "娱乐", "CBEC": "跨境电商",
}

# 输出文件 ← (前缀列表, 额外 ID 列表, 排除 ID 列表)
FILES = [
    ("vat_rules.yaml", ["VAT"], [], []),
    ("cit_rules.yaml", ["CIT"], [], []),
    ("iit_rules.yaml", ["IIT"], [], []),
    ("other_tax_rules.yaml",
     ["SI", "SD", "PCT", "LUT", "LAT", "SUR", "CONS", "RES", "ENV",
      "DEED", "GOT", "VET", "VPT", "CUS", "TON", "TOB", "CUL", "WAT"], [], []),
    ("invoice_rules.yaml", ["INV"], [], []),
    ("financial_rules.yaml", ["FIN", "REL", "FUND"], [], ["FUND-011"]),
    ("general_rules.yaml", ["GEN"], [], []),
    ("adm_rules.yaml", ["ADM"], [], []),
    ("aa_rules.yaml", ["AA"], [], []),
    ("intl_rules.yaml", ["INT"], [], []),
    ("reo_rules.yaml", ["REO"], [], []),
    ("realestate_construction_rules.yaml", ["EST", "CONSTR"], [], []),
    ("platform_flex_hnw_rules.yaml", ["PLAT", "FLEX", "HNW"], [], []),
    ("finance_rules.yaml",
     ["FINA", "LEASE", "FACT", "MICRO", "GUAR", "PAWN", "PE", "FUNDM", "TRUST", "REIT",
      "PPP", "EPC", "BOT", "ABS"], ["FUND-011"], []),
    ("customs_export_rules.yaml", ["EXPORT", "CUSTOMS", "BOND", "FTZ", "HAINAN"], [], []),
    ("incentive_assess_liquidation_rules.yaml", ["TAXINC", "ASSESS", "LIQ", "BANKR"], [], []),
    ("einvoice_rrt_rules.yaml", ["EINV", "RRT"], [], []),
    ("industry_rules.yaml",
     ["HNTECH", "RD", "SOFT", "IC", "ANIME", "CULT", "EDU", "MED", "ELDER", "CHILD",
      "HOUSE", "SPORT", "TOUR", "HOTEL", "CATER", "ENT", "CBEC"], [], []),
]

_EXIST = re.compile(r"[<>=!]=?\s*0(?![\d.])")   # 存在性判据（> 0 / >= 0 / = 0 / != 0）


def _q(s) -> str:
    s = "" if s is None else str(s)
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _collect() -> list[dict]:
    params: dict = {}
    for _tag, path in SOURCES:
        d = json.loads(path.read_text(encoding="utf-8"))
        params.update({k: v for k, v in (d.get("params") or {}).items() if not k.startswith("_")})

    rows, ids = [], []
    for tag, path in SOURCES:
        d = json.loads(path.read_text(encoding="utf-8"))
        for r in d["rules"]:
            ids.append(r["src"])
            rows.append({"rid": r["src"], "src_set": tag, "raw": r, "params": params.get(r["src"])})
    clash = sorted({x for x in ids if ids.count(x) > 1})
    assert not clash, "三表 ID 冲突: %s" % clash
    return rows


def _check_stats(rows: list[dict]) -> None:
    """各表 stats 必须与实测计数一致（防人工填错 stats）。"""
    for tag, path in SOURCES:
        d = json.loads(path.read_text(encoding="utf-8"))
        st = d.get("stats") or {}
        sub = [r for r in rows if r["src_set"] == tag]
        cnt = Counter(r["raw"]["status"] for r in sub)
        for k in ("covered", "partial", "missing", "placeholder"):
            declared = st.get(k)
            if declared is None:
                continue
            assert declared == cnt.get(k, 0), \
                "%s stats.%s 声明 %s ≠ 实测 %s" % (tag, k, declared, cnt.get(k, 0))
        if st.get("total") is not None:
            assert st["total"] == len(sub), "%s stats.total 声明 %s ≠ 实测 %d" % (
                tag, st["total"], len(sub))
        print("[stats] %s: total=%d %s ✓" % (
            tag, len(sub), dict(cnt)))


def _check(rows: list[dict]) -> None:
    bad_missing, bad_inline = [], []
    for row in rows:
        r, rid = row["raw"], row["rid"]
        for f in ("name", "sev", "status", "logic", "inputs", "suggestion", "action"):
            if not r.get(f):
                bad_missing.append("%s 缺 %s" % (rid, f))
        if r["status"] not in ("covered", "partial", "missing", "placeholder"):
            bad_missing.append("%s status 非法: %s" % (rid, r["status"]))
        logic = r.get("logic", "")
        if re.search(r"[<>=!]\s*\d", _EXIST.sub(" ", logic)) and "params." not in logic:
            bad_inline.append("%s: %s" % (rid, logic))
    assert not bad_missing, "字段缺失/非法: %s" % bad_missing[:10]
    assert not bad_inline, "阈值内联（应引用 params.*）: %s" % bad_inline[:10]

    # 前缀唯一归属
    seen: dict[str, str] = {}
    for fname, prefixes, extra, exclude in FILES:
        for p in prefixes:
            if p in seen:
                raise AssertionError("前缀 %s 同时属于 %s 与 %s" % (p, seen[p], fname))
            seen[p] = fname
    print("[check] 字段完整 ✓  阈值零内联 ✓  前缀唯一归属 ✓  共 %d 条" % len(rows))


def _bucket(fname: str, prefixes: list[str], extra: list[str], exclude: list[str],
            rows: list[dict]) -> list[dict]:
    pref = set(prefixes)
    ext, exc = set(extra), set(exclude)
    return [r for r in rows
            if r["rid"] not in exc
            and (r["rid"].split("-")[0] in pref or r["rid"] in ext)]


def _render(fname: str, sub: list[dict]) -> str:
    cnt = Counter(r["raw"]["status"] for r in sub)
    L = []
    L.append("# " + "=" * 74)
    L.append("# 自动生成，请勿手工编辑 —— 导出器：tools/export_rulelist_yaml.py")
    L.append("# 唯一权威：config/rulelist_v1.json + rulelist_v11.json + rulelist_v12.json")
    L.append("# 所有阈值集中在上述文件的 params 段；本文件只引用（params_ref），不内联。")
    L.append("# " + "=" * 74)
    L.append("schema: 1")
    L.append("file: " + _q(fname))
    L.append("rule_set: " + _q("外部候选规则清单 V1.0 + V1.1 + V1.2"))
    L.append("rule_set_version: " + _q(RULE_SET_VERSION))
    L.append("status: draft")
    L.append("wired: false")
    L.append("wired_note: " + _q(
        "未接入系统：不新增红线、不改判定逻辑、不改前端。系统内部权威为 config/rulelist_*.json。"))
    L.append("coverage_summary:")
    L.append("  total: %d" % len(sub))
    for k in ("covered", "partial", "missing", "placeholder"):
        if cnt.get(k, 0):
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
                else:
                    L.append("      %s: %s" % (pk, json.dumps(pv, ensure_ascii=False)))
        else:
            L.append("    params: {}")
            if raw["status"] == "covered":
                L.append("    params_note: " + _q(
                    "阈值权威在**系统内部实现**（见 coverage.mapped_to）；本清单不另设阈值，避免两头各写一份。"))
            elif _EXIST.search(raw.get("logic", "")):
                L.append("    params_note: " + _q(
                    "本规则为「存在即触发」判据（> 0 / = 0 型），无比例阈值；符合项目铁律「不要阈值」。"))
            else:
                L.append("    params_note: " + _q(
                    "待登记：阈值/地区参数尚未提供，检测器须输出「待核」，禁止默认值顶替。"))
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只校验不写盘")
    args = ap.parse_args()

    rows = _collect()
    _check_stats(rows)
    _check(rows)

    if not args.check:
        OUT_DIR.mkdir(exist_ok=True)
    total, reports, covered_ids = 0, [], set()
    for fname, prefixes, extra, exclude in FILES:
        sub = _bucket(fname, prefixes, extra, exclude, rows)
        assert sub, "%s 无规则" % fname
        total += len(sub)
        covered_ids |= {r["rid"] for r in sub}
        reports.append((fname, len(sub), dict(Counter(r["raw"]["status"] for r in sub))))
        if not args.check:
            (OUT_DIR / fname).write_text(_render(fname, sub), encoding="utf-8")

    assert total == len(rows), "导出条数 %d ≠ 候选 %d" % (total, len(rows))
    missing = {r["rid"] for r in rows} - covered_ids
    assert not missing, "有规则未被任何文件收录: %s" % sorted(missing)[:10]

    print("\n[export] 分组（%d 个文件）：" % len(reports))
    for fname, n, cnt in reports:
        print("  %-42s %3d 条  %s" % (fname, n, cnt))
    print("[export] 合计 %d 条（应 == 候选 %d）✓" % (total, len(rows)))
    print("[export] 输出目录: %s%s" % (
        OUT_DIR.relative_to(ROOT), "（--check 未写盘）" if args.check else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
