# -*- coding: utf-8 -*-
"""生成 `config/legal_law_codes.json`（**法名规范表** = 条款 ID 的前提，唯一权威）。

## 为什么必须有它
实测红线 `legal_basis` 与正文库的**同一部法有多种写法**：
  · `税收征收管理法` vs `中华人民共和国税收征收管理法`
  · `企业所得税税前扣除凭证管理办法` vs `企业所得税税前扣除凭证管理办法（国家税务总局公告2018年第28号）`
⇒ 不规范化，`legal_basis_ref` 无法稳定指向条款（一法多键 ⇒ 关联会断）。

本表：**一条法一行**（`code` 短码 + `name` 规范名 + `aliases` 别名 + `level` 层级 + `doc_num` 文号）。
条款 ID = `{code}-{条号阿拉伯数字:03d}`，如 `INVOICE-MEASURE-022`（发票管理办法第二十二条）。

用法（幂等；已有 code 保留）：
    ./.venv/Scripts/python.exe scripts/_gen_legal_law_codes.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "config" / "legal_law_codes.json"

#: 人工核定的短码（**新增一部法只加一行**）。键 = 去「中华人民共和国」前缀后的规范名。
CURATED: dict[str, tuple[str, str]] = {
    # ── 法律 ──
    "个人所得税法": ("IIT-LAW", "法律"),
    "企业所得税法": ("CIT-LAW", "法律"),
    "税收征收管理法": ("TAX-ADMIN-LAW", "法律"),
    "会计法": ("ACCOUNTING-LAW", "法律"),
    "增值税法": ("VAT-LAW", "法律"),
    "印花税法": ("STAMP-TAX-LAW", "法律"),
    "契税法": ("DEED-TAX-LAW", "法律"),
    "城市维护建设税法": ("UCT-LAW", "法律"),
    "资源税法": ("RESOURCE-TAX-LAW", "法律"),
    "环境保护税法": ("EPT-LAW", "法律"),
    "耕地占用税法": ("FARMLAND-TAX-LAW", "法律"),
    "车辆购置税法": ("VPT-LAW", "法律"),
    "车船税法": ("VVT-LAW", "法律"),
    "烟叶税法": ("TOBACCO-TAX-LAW", "法律"),
    "船舶吨税法": ("TONNAGE-TAX-LAW", "法律"),
    "关税法": ("CUSTOMS-DUTY-LAW", "法律"),
    "社会保险法": ("SOCIAL-INSURANCE-LAW", "法律"),
    "工会法": ("UNION-LAW", "法律"),
    "海关法": ("CUSTOMS-LAW", "法律"),
    "行政处罚法": ("APA-LAW", "法律"),
    "刑法": ("CRIMINAL-LAW", "法律"),
    # ── 行政法规 ──
    "个人所得税法实施条例": ("IIT-REG", "行政法规"),
    "企业所得税法实施条例": ("CIT-REG", "行政法规"),
    "发票管理办法": ("INVOICE-MEASURE", "行政法规"),
    "发票管理办法实施细则": ("INVOICE-MEASURE-RULES", "行政法规"),
    "税收征收管理法实施细则": ("TAX-ADMIN-LAW-REG", "行政法规"),
    "增值税法实施条例": ("VAT-REG", "行政法规"),
    "消费税暂行条例": ("CT-REG", "行政法规"),
    "土地增值税暂行条例": ("LVAT-REG", "行政法规"),
    "房产税暂行条例": ("PROPERTY-TAX-REG", "行政法规"),
    "城镇土地使用税暂行条例": ("ULT-REG", "行政法规"),
    "车船税法实施条例": ("VVT-REG", "行政法规"),
    "住房公积金管理条例": ("HPF-REG", "行政法规"),
    "残疾人就业条例": ("DISABILITY-EMP-REG", "行政法规"),
    "征收教育费附加的暂行规定": ("EDU-SURCHARGE-REG", "行政法规"),
    "企业会计准则——基本准则": ("ASBE-BASIC", "部门规章"),
    # ── 部门规章 / 规范性文件 / 公告通知 ──
    "企业所得税税前扣除凭证管理办法": ("CIT-VOUCHER-MEASURE", "规范性文件"),
    "增值税专用发票使用规定": ("VAT-INVOICE-RULE", "规范性文件"),
    "人民币银行结算账户管理办法": ("RMB-ACCOUNT-MEASURE", "部门规章"),
    "企业所得税核定征收办法": ("CIT-ASSESSED-MEASURE", "规范性文件"),
    "股权转让所得个人所得税管理办法（试行）": ("EQUITY-TRANSFER-IIT-MEASURE", "规范性文件"),
    "残疾人就业保障金征收使用管理办法": ("DISABILITY-FUND-MEASURE", "规范性文件"),
    "水利建设基金筹集和使用管理办法": ("WATER-FUND-MEASURE", "规范性文件"),
    "出口业务增值税和消费税退（免）税管理办法": ("EXPORT-REFUND-MEASURE", "规范性文件"),
    "农产品增值税进项税额核定扣除试点实施办法": ("AGRI-INPUT-DEDUCT", "规范性文件"),
    "纳税人提供不动产经营租赁服务增值税征收管理暂行办法": ("REALTY-LEASE-VAT", "规范性文件"),
    "纳税人跨县（市、区）提供建筑服务增值税征收管理暂行办法": ("CROSS-COUNTY-CONSTRUCT-VAT", "规范性文件"),
    "纳税人转让不动产增值税征收管理暂行办法": ("REALTY-TRANSFER-VAT", "规范性文件"),
    "国家税务总局公告2011年第25号": ("SAT-ANN-2011-25", "规范性文件"),
    "国家税务总局公告2014年第39号": ("SAT-ANN-2014-39", "规范性文件"),
    "国家税务总局公告2014年第67号": ("SAT-ANN-2014-67", "规范性文件"),
    "国家税务总局公告2019年第38号": ("SAT-ANN-2019-38", "规范性文件"),
    "国家税务总局关于办理增值税期末留抵退税有关征管事项的公告": ("SAT-RETENTION-REFUND", "规范性文件"),
    "国家税务总局关于工会经费企业所得税税前扣除凭据问题的公告": ("SAT-UNION-FEE-VOUCHER", "规范性文件"),
    "国家税务总局关于房地产开发企业土地增值税清算管理有关问题的通知": ("SAT-LVAT-CLEARING", "规范性文件"),
    "国家税务总局关于车辆购置税征收管理有关事项的公告": ("SAT-VPT-ADMIN", "规范性文件"),
    "财政部 税务总局公告2023年第7号": ("MOF-STA-ANN-2023-7", "规范性文件"),
    "财政部 税务总局关于个人所得税法修改后有关优惠政策衔接问题的通知": ("MOF-IIT-TRANSITION", "规范性文件"),
    "财政部 税务总局关于出口业务增值税和消费税政策的公告": ("MOF-EXPORT-VAT-CT", "规范性文件"),
    "财政部 税务总局关于完善增值税期末留抵退税政策的公告": ("MOF-RETENTION-REFUND", "规范性文件"),
    "财政部 税务总局关于简并增值税税率有关政策的通知": ("MOF-VAT-RATE-SIMPLIFY", "规范性文件"),
    "财政部 税务总局关于车辆购置税有关具体政策的公告": ("MOF-VPT-POLICY", "规范性文件"),
    "财政部 国家税务总局关于专项用途财政性资金企业所得税处理问题的通知": ("MOF-CIT-SPECIAL-FUND", "规范性文件"),
    "财政部 国家税务总局关于企业关联方利息支出税前扣除标准有关税收政策问题的通知": ("MOF-CIT-RELATED-INTEREST", "规范性文件"),
    "财政部 国家税务总局关于全面推开营业税改征增值税试点的通知": ("CS-2016-36", "规范性文件"),
    "财政部 国家税务总局关于在部分行业试行农产品增值税进项税额核定扣除办法的通知": ("MOF-AGRI-DEDUCT-PILOT", "规范性文件"),
    "财政部 国家税务总局关于研究开发费用税前加计扣除有关政策问题的通知": ("MOF-RD-SUPERDEDUCT", "规范性文件"),
    "财政部 国家税务总局关于营业税改征增值税试点有关文化事业建设费政策及征收管理问题的补充通知": ("MOF-CCF-SUPPLEMENT", "规范性文件"),
    "财政部 国家税务总局关于营业税改征增值税试点有关文化事业建设费政策及征收管理问题的通知": ("MOF-CCF", "规范性文件"),
    "财政部 国家税务总局关于规范个人投资者个人所得税征收管理的通知": ("MOF-IIT-INVESTOR", "规范性文件"),
    "财政部关于民航发展基金等3项政府性基金有关政策的通知": ("MOF-CIVIL-AVIATION-FUND", "规范性文件"),
    "财税〔2008〕121号": ("CS-2008-121", "规范性文件"),
    # ── TOPIC-001 定向目标（抓取待补 / 已知）──
    "全国税务行政处罚裁量基准": ("SAT-DISCRETION-BENCHMARK", "部门规章"),
    "纳税人合规开具发票正负面清单": ("SAT-INVOICE-POSNEG-LIST", "规范性文件"),
    "涉税专业服务监管办法": ("TAX-INTERMEDIARY-SUPERVISION", "规范性文件"),
    "关于走逃（失联）企业开具增值税专用发票认定处理有关问题的公告": ("SAT-RUNAWAY-INVOICE-ANN", "规范性文件"),
    "关于异常增值税扣税凭证管理等有关事项的公告": ("SAT-ABNORMAL-VOUCHER-ANN", "规范性文件"),
    "关于纳税人善意取得虚开的增值税专用发票处理问题的通知": ("SAT-GOODFAITH-INVOICE-NOTICE", "规范性文件"),
    "关于纳税人善意取得虚开增值税专用发票已抵扣税款加收滞纳金问题的批复": ("SAT-GOODFAITH-LATE-FEE-REPLY", "规范性文件"),
    "关于办理危害税收征管刑事案件适用法律若干问题的解释": ("SPC-SPP-TAX-CRIME-INTERP", "司法解释"),
    "重大税收违法失信主体信息公布管理办法": ("SAT-MAJOR-TAX-VIOLATION-DISCLOSURE", "部门规章"),
    "关于对重大税收违法案件当事人实施联合惩戒措施的合作备忘录": ("MOU-JOINT-PUNISHMENT", "联合发文"),
}

#: 别名（写进 aliases；键为规范名）
ALIASES: dict[str, list[str]] = {
    "个人所得税法": ["中华人民共和国个人所得税法"],
    "企业所得税法": ["中华人民共和国企业所得税法"],
    "税收征收管理法": ["中华人民共和国税收征收管理法"],
    "增值税法": ["中华人民共和国增值税法"],
    "发票管理办法": ["中华人民共和国发票管理办法"],
    "消费税暂行条例": ["中华人民共和国消费税暂行条例"],
    "契税法": ["中华人民共和国契税法"],
    "资源税法": ["中华人民共和国资源税法"],
    "环境保护税法": ["中华人民共和国环境保护税法"],
    "关税法": ["中华人民共和国关税法"],
    "企业所得税税前扣除凭证管理办法": [
        "企业所得税税前扣除凭证管理办法（国家税务总局公告2018年第28号）"],
    "关于异常增值税扣税凭证管理等有关事项的公告": [
        "国家税务总局关于异常增值税扣税凭证管理等有关事项的公告"],
    "关于纳税人善意取得虚开的增值税专用发票处理问题的通知": [
        "国家税务总局关于纳税人善意取得虚开的增值税专用发票处理问题的通知",
        "关于纳税人善意取得虚开的增值税专用发票处理问题的通知（国税发〔2000〕187号）"],
    "关于办理危害税收征管刑事案件适用法律若干问题的解释": [
        "最高人民法院 最高人民检察院关于办理危害税收征管刑事案件适用法律若干问题的解释",
        "关于办理危害税收征管刑事案件适用法律若干问题的解释（两高解释）",
        "两高解释"],
    # ★ 2026-10-15：抓取目标名带**括注文号/简称**后缀 ⇒ 归并到规范名
    #   （否则注册表出现「同一部法两个名字」⇒ flk 抓取会漏，条款 ID 会分叉）
    "全国税务行政处罚裁量基准": ["全国税务行政处罚裁量基准（2026年版）"],
    "关于纳税人善意取得虚开增值税专用发票已抵扣税款加收滞纳金问题的批复": [
        "关于纳税人善意取得虚开增值税专用发票已抵扣税款加收滞纳金问题的批复（国税函〔2007〕1240号）"],
}


def _canon(s: str) -> str:
    return re.sub(r"^中华人民共和国", "", str(s or "")).strip()


def collect_law_names() -> set:
    """并集：正文库法名 ∪ 红线 `legal_basis` 中的法名 ∪ 定向抓取目标名。

    ★ 2026-10-15 补第三源：`config/legal_crawl_targets.json` 里登记的目标法
      （如刑法/行政处罚法/税收征收管理法实施细则）此前**不在并集里** ⇒ 注册表缺它们
      ⇒ flk 抓取时「脚本按注册表遍历」直接跳过（静默漏）。并入后不再漏。
    """
    lib = {e["law"] for e in json.loads(
        (ROOT / "static" / "legal_library.json").read_text(encoding="utf-8"))}
    red = set()
    try:
        from engine import tax_redlines as TR
        for r in TR.all_redlines():
            for lb in (r.get("legal_basis") or []):
                m = re.match(r"《(.+?)》", str(lb))
                if m:
                    red.add(m.group(1))
    except Exception as exc:                                     # noqa: BLE001
        print("[WARN] 红线库读取失败（法名并集仅含正文库）：%s" % exc)
    tgt = set()
    tp = ROOT / "config" / "legal_crawl_targets.json"
    if tp.exists():
        try:
            tdata = json.loads(tp.read_text(encoding="utf-8"))
            for _t, tv in (tdata.get("topics") or {}).items():
                for x in (tv.get("targets") or []):
                    if x.get("name"):
                        tgt.add(x["name"])
        except Exception as exc:                                 # noqa: BLE001
            print("[WARN] 抓取目标读取失败：%s" % exc)
    cand = {_canon(x) for x in (lib | red | tgt)}
    # 别名归并到规范名
    alias2canon = {}
    for canon, als in ALIASES.items():
        for a in als:
            alias2canon[_canon(a)] = canon
    out = set()
    for c in cand:
        out.add(alias2canon.get(c, c))
    return out


def main() -> int:
    names = collect_law_names()
    old = {}
    if OUT.exists():
        try:
            for l in json.loads(OUT.read_text(encoding="utf-8")).get("laws", []):
                old[l["name"]] = l
        except Exception:                                        # noqa: BLE001
            pass

    laws, uncovered, used_codes = [], [], set()
    for name in sorted(names):
        if name in CURATED:
            code, level = CURATED[name]
        elif name in old:                                        # 已有登记沿用
            code, level = old[name]["code"], old[name].get("level", "")
        else:
            code, level = "", ""                                 # 未核定 ⇒ 留空，如实暴露
        if code:
            used_codes.add(code)
        laws.append({
            "code": code,
            "name": name,
            "aliases": sorted(set(ALIASES.get(name, []))),
            "level": level,
            "doc_num": (old.get(name) or {}).get("doc_num"),
            "provision_id_prefix": ("%s-" % code) if code else None,
        })
        if not code:
            uncovered.append(name)

    dup = [c for c in used_codes if sum(1 for l in laws if l["code"] == c) > 1]
    payload = {
        "schema": 1,
        "updated": "2026-10-15",
        "note": ("★ **法名规范表**（唯一权威）：一条法一行；`code` 是条款 ID 的短码前缀。"
                 "条款 ID = `{code}-{条号:03d}`（如 `INVOICE-MEASURE-022` = 发票管理办法第二十二条）。"
                 "★ 新增一部法**只加一行**；`code` 为空 ⇒ **该法尚未核定短码**（如实暴露，不猜）。"
                 "★ 法名变体（含/不含「中华人民共和国」前缀、括注文号）一律登记为 `aliases`，"
                 "使 `legal_basis_ref` 能稳定解析到同一条款。"),
        "law_count": len(laws),
        "coded_count": len(laws) - len(uncovered),
        "duplicate_codes": dup,
        "laws": laws,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print("法名 %d 部 | 已核定短码 %d | 未核定 %d" %
          (len(laws), payload["coded_count"], len(uncovered)))
    if dup:
        print("!! 短码重复：%s" % dup)
    if uncovered:
        print("未核定短码（如实列出，待补）：")
        for u in uncovered:
            print("  -", u)
    print("→ %s" % OUT)
    return 1 if dup else 0


if __name__ == "__main__":
    raise SystemExit(main())
