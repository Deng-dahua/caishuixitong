# -*- coding: utf-8 -*-
"""补充 `config/legal_law_codes.json` 的法短码 —— 让**全量正文库**的条文都有规范条款 ID。

## 背景（实测，2026-10-15）
整部法全文入库后正文库 131 → 6569 条，但 `_gen_legal_index.py` 现算发现
**5312 条拿不到 `provision_id`**（`个人信息保护法 第一条` …）—— 原因是这些法
未登记在唯一权威表 `config/legal_law_codes.json`（原只覆盖 82 部「税务相关法」）。
条款级关联（遗留项②）与条款 ID 展示都依赖该短码 ⇒ 必须补齐。

## 纪律
- **只加数据行、不改逻辑**（项目铁律）：短码在 `CODES` 里一行一部法。
- `level` **不做人工判断**，直接取采集层 `data/legal_crawl/legal_texts_index.json`
  的 `effect_level`（数据源字段，权威）；查不到才留空并如实计入 `missing_level`。
- **幂等**：已登记的法（按 `name` 或 `aliases` 命中）跳过；短码冲突**直接报错中止**，不覆盖。

用法：`./.venv/Scripts/python.exe scripts/_extend_law_codes.py`
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
REG_PATH = ROOT / "config" / "legal_law_codes.json"
IDX_PATH = ROOT / "data" / "legal_crawl" / "legal_texts_index.json"

#: 法名 → 短码（一行一部；短码规则：主题/法名英文缩写 + 类型后缀 LAW/REG/…）
CODES: Dict[str, str] = {
    "民法典": "CIVIL-CODE",
    "刑事诉讼法": "CRIM-PROC-LAW",
    "民事诉讼法": "CIVIL-PROC-LAW",
    "公司法": "COMPANY-LAW",
    "证券法": "SECURITIES-LAW",
    "企业破产法": "BANKRUPTCY-LAW",
    "保险法": "INSURANCE-LAW",
    "立法法": "LEGISLATION-LAW",
    "合伙企业法": "PARTNERSHIP-LAW",
    "行政诉讼法": "ADMIN-LITIGATION-LAW",
    "劳动合同法": "LABOR-CONTRACT-LAW",
    "行政复议法": "ADMIN-RECONSIDER-LAW",
    "电子商务法": "E-COMMERCE-LAW",
    "土地管理法": "LAND-ADMIN-LAW",
    "教育法": "EDUCATION-LAW",
    "行政许可法": "ADMIN-LICENSE-LAW",
    "矿产资源法": "MINERAL-RESOURCE-LAW",
    "矿产资源法实施条例": "MINERAL-RESOURCE-REG",
    "个人信息保护法": "PI-PROTECT-LAW",
    "城市房地产管理法": "URBAN-REAL-ESTATE-LAW",
    "优化营商环境条例": "BUSINESS-ENV-REG",
    "行政强制法": "ADMIN-COERCION-LAW",
    "反垄断法": "ANTI-MONOPOLY-LAW",
    "残疾人保障法": "DISABLED-PROTECT-LAW",
    "工伤保险条例": "WORK-INJURY-REG",
    "票据法": "NEGOTIABLE-INSTRUMENT-LAW",
    "保守国家秘密法": "STATE-SECRET-LAW",
    "水土保持法": "SOIL-WATER-CONSERV-LAW",
    "海岛保护法": "ISLAND-PROTECT-LAW",
    "海南自由贸易港法": "HAINAN-FTP-LAW",
    "政府信息公开条例": "GOV-INFO-DISCLOSE-REG",
    "海域使用管理法": "SEA-AREA-USE-LAW",
    "人民防空法": "CIVIL-AIR-DEFENSE-LAW",
    "城镇国有土地使用权出让和转让暂行条例": "STATE-LAND-TRANSFER-REG",
    "军人保险法": "MILITARY-INSURANCE-LAW",
    "外商投资法实施条例": "FOREIGN-INVEST-REG",
    "个人独资企业法": "SOLE-PROPRIETORSHIP-LAW",
    "价格法": "PRICE-LAW",
    "城市市容和环境卫生管理条例": "CITY-SANITATION-REG",
    "行政执法监督条例": "ADMIN-ENFORCE-SUPERVISION-REG",
    "重大行政决策程序暂行条例": "MAJOR-DECISION-PROC-REG",
    "外商投资法": "FOREIGN-INVEST-LAW",
    "规章制定程序条例": "RULE-MAKING-PROC-REG",
    "促进个体工商户发展条例": "INDIVIDUAL-BUSINESS-REG",
    "劳动保障监察条例": "LABOR-SUPERVISION-REG",
    "废弃电器电子产品回收处理管理条例": "WEEE-RECYCLE-REG",
    "反不正当竞争法": "ANTI-UNFAIR-COMPETITION-LAW",
    "失业保险条例": "UNEMPLOYMENT-INSURANCE-REG",
    "劳动合同法实施条例": "LABOR-CONTRACT-REG",
    "社会保险费征缴暂行条例": "SOCIAL-INSURANCE-COLLECT-REG",
    "公平竞争审查条例": "FAIR-COMPETITION-REVIEW-REG",
    "法规规章备案审查条例": "REG-FILING-REVIEW-REG",
    "行政复议法实施条例": "ADMIN-RECONSIDER-REG",
    "国务院关于废止营业税暂行条例和修改增值税暂行条例的决定": "BT-VAT-REPEAL-DECISION",
    "城市房地产开发经营管理条例": "URBAN-REAL-ESTATE-DEV-REG",
    "国家赔偿法": "STATE-COMPENSATION-LAW",
    "行政执法机关移送涉嫌犯罪案件的规定": "ADMIN-ENFORCE-CRIMINAL-TRANSFER-REG",
    "环境保护税法实施条例": "EPT-REG",
    "关于工资总额组成的规定": "WAGE-TOTAL-REG",
    "互联网平台企业涉税信息报送规定": "PLATFORM-TAX-INFO-REG",
    "刑法修正案": "CRIM-LAW-AMEND-1",
    "刑法修正案（六）": "CRIM-LAW-AMEND-6",
    "刑法修正案（八）": "CRIM-LAW-AMEND-8",
    "刑法修正案（九）": "CRIM-LAW-AMEND-9",
    "刑法修正案（十一）": "CRIM-LAW-AMEND-11",
    "刑法修正案（十二）": "CRIM-LAW-AMEND-12",
    "对储蓄存款利息所得征收个人所得税的实施办法": "IIT-SAVING-INTEREST-MEASURE",
    "国务院关于修改对储蓄存款利息所得征收个人所得税的实施办法的决定":
        "IIT-SAVING-INTEREST-AMEND-DECISION",
    "对外合作开采海洋石油资源条例": "OFFSHORE-OIL-COOP-REG",
    "对外合作开采陆上石油资源条例": "ONSHORE-OIL-COOP-REG",
}


def _keys(l: Dict[str, Any]) -> List[str]:
    return [k for k in ([l.get("name")] + list(l.get("aliases") or [])) if k]


def main() -> int:
    reg = json.loads(REG_PATH.read_text(encoding="utf-8"))
    laws: List[Dict[str, Any]] = reg.get("laws") or []
    have_names = {k for l in laws for k in _keys(l)}
    have_codes = {l["code"] for l in laws}

    # level 权威取自采集层（不人工判定）
    levels: Dict[str, str] = {}
    if IDX_PATH.exists():
        from engine.legal_version import canonical_law as _cl
        for it in (json.loads(IDX_PATH.read_text(encoding="utf-8")).get("items") or []):
            if it.get("effect_level"):
                levels.setdefault(_cl(str(it.get("title") or "")), it["effect_level"])

    added, skipped = [], []
    missing_level = []
    for name, code in CODES.items():
        if name in have_names:
            skipped.append(name)
            continue
        if code in have_codes:
            print("!! 短码冲突：`%s` 已被占用（法名 %s）⇒ 中止，不覆盖" % (code, name))
            return 2
        lv = levels.get(name)
        if not lv:
            missing_level.append(name)
        laws.append({
            "code": code,
            "name": name,
            "aliases": ["中华人民共和国" + name] if not name.startswith("中华人民共和国") else [],
            "level": lv,
            "doc_num": None,
            "provision_id_prefix": code + "-",
        })
        have_codes.add(code)
        have_names.add(name)
        added.append("%s=%s" % (name, code))

    reg["laws"] = laws
    reg["law_count"] = len(laws)
    reg["coded_count"] = len([l for l in laws if l.get("code")])
    reg["updated"] = "2026-10-15"
    REG_PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print("登记：新增 %d 部（跳过已登记 %d 部）⇒ 法名表 %d 部"
          % (len(added), len(skipped), len(laws)))
    if missing_level:
        print("★ level 未取到（如实列出，未编造）：%s" % ("、".join(missing_level)))
    for a in added:
        print("   +", a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
