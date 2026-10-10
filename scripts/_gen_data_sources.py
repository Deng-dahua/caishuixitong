# -*- coding: utf-8 -*-
"""数据源状态表生成器：从**真实产物**派生 `config/data_sources.json`（Skill 7）。

## 为什么从产物派生
「数据源」的名字来自**红线定义**（`engine/tax_redlines.py` 的 `constituent_sources`），
在本企业报告里以「独立数据源」列呈现。名字会随红线库扩充而增加 ⇒ 表格必须能**自动纳入新名字**
（用户规格：新增数据源时自动纳入一致性校验）。

## 哪些字段是"派生的"、哪些是"人工撰写的"
- **派生**（脚本每次重跑都会刷新）：`data_source_id`、`data_source_name`、`_seen`（出现次数）。
- **人工撰写**（脚本**原样保留**旧值，不被覆盖）：
  · `aliases`      —— 同一数据源的不同写法（归一用）
  · `provided_by`  —— **严格的数据包含关系**：该数据源是某份已取得资料的**字段/内容**
                      （如「红字发票信息确认单」的编号是数电红字发票的字段 ⇒ 由「销项发票/进项发票」提供）。
                      ⚠ 只写**能证实的**包含关系；"可能有关"一律不写（宁可判须核对，不得给假"已有"）。
  · `markers`      —— **硬证据特征**：该数据源在明细表里留下的**具体标识名**
                      （如「红字发票信息确认单编号」）。命中 ⇒ 该数据源本轮**已取得**。
                      ⚠ 只写**专有标识名**，不写"蓝字发票"这种泛词（否则满篇命中 ⇒ 假"已有"）。

新增数据源：脚本自动加行（`aliases/provided_by/markers` 留空）⇒ 门禁立刻能校验；
要把它判成"已有"再补 markers —— **改数据不改逻辑**。
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_CFG = ROOT / "config" / "data_sources.json"
_REPORT = ROOT / "scripts" / "four_reports" / "company_1_full.json"

#: 人工撰写字段（唯一出处；新增数据源 = 在这里加一行）
AUTHORED: Dict[str, Dict[str, Any]] = {
    # ── 数电发票的"票据级字段"：确认单编号/被冲减蓝票号码就写在发票数据里 ──────────
    "红字发票信息确认单": {
        "aliases": ["红字确认单", "红字发票信息确认单编号", "红字信息表"],
        "provided_by": ["销项发票", "进项发票"],
        "markers": ["红字发票信息确认单编号", "红字发票信息确认单", "红字确认单编号"],
    },
    "被冲减蓝字发票": {
        "aliases": ["被红冲蓝字发票", "蓝字发票"],
        "provided_by": ["销项发票", "进项发票"],
        "markers": ["被冲减蓝字数电发票号码", "被红冲蓝字数电发票号码",
                    "被冲减蓝字发票号码", "被红冲蓝字发票号码"],
    },
    "开票错误更正说明": {
        "aliases": ["更正说明"],
        "markers": ["开票错误更正说明"],
    },
    # ── 台账/计算底稿：**可能与已取得资料同源**，但需人工确认范围（不下"已有"结论）──
    "工资总额计算底稿": {"aliases": ["工资总额底稿"], "markers": ["工资总额计算底稿"]},
    "往来科目明细": {"aliases": ["往来明细", "往来款明细"], "markers": ["往来科目明细"]},
    "境外付款台账": {"aliases": ["境外付款清单"], "markers": ["境外付款台账"]},
    "对外付汇凭证": {"aliases": ["付汇凭证"], "markers": ["对外付汇凭证"]},
    "完税凭证": {"aliases": ["完税证明", "税收缴款书"], "markers": ["完税凭证", "完税证明"]},
    "折旧计算表": {"aliases": ["折旧表"], "markers": ["折旧计算表"]},
    "工资表": {"aliases": ["工资明细表", "工资发放表"]},
    "社保明细": {"aliases": ["社保参保明细", "社会保险缴费明细"]},
    "科目余额表": {"aliases": ["余额表"]},
    "记账凭证": {"aliases": ["凭证"]},
    "银行流水": {"aliases": ["银行对账单", "流水"]},
    "销项发票": {"aliases": ["销项发票明细"]},
    "进项发票": {"aliases": ["进项发票明细"]},
    "增值税申报表": {"aliases": ["增值税纳税申报表"]},
    "企业所得税申报表": {"aliases": ["企业所得税年度纳税申报表"]},
    "附加税费申报表": {"aliases": ["城建税及附加申报表", "附加税申报表"]},
    "印花税申报表": {"aliases": ["印花税纳税申报表"]},
    "文化事业建设费申报表": {"aliases": ["文化事业建设费申报"]},
    "合同文件": {"aliases": ["合同"]},
    "合同台账": {"aliases": ["合同清单"]},
    "采购合同": {}, "服务合同": {}, "借款合同": {}, "劳动合同": {}, "劳务派遣协议": {},
    "合同或协议": {},
    "退货单": {}, "折让协议": {}, "拒收证明": {}, "验收单": {},
    "资产财务报表": {},
    "资产负债表": {}, "利润表": {},
    "费用明细账": {}, "成本明细账": {}, "固定资产明细账": {}, "在建工程明细": {},
    "应付账款明细": {}, "汇算清缴纳税调整明细": {},
    "扣缴企业所得税报告表": {}, "评估报告": {}, "工商变更登记": {},
    "定价政策": {}, "娱乐服务收入台账": {}, "广告服务": {}, "收入": {},
}

#: 编号前缀（同类数据源共用前缀，便于人工辨认；`data_source_id` 是**稳定键**，
#: 一旦登记不得改名 —— 改名等于换了一个数据源）
_PREFIX = {
    "发票": "INV", "申报表": "TAX", "明细": "LED", "台账": "LGR", "凭证": "VCH",
    "流水": "BNK", "合同": "CTR", "协议": "CTR", "报表": "FIN", "计算表": "CAL",
    "报告表": "RPT", "报告": "RPT", "底稿": "WKP", "登记": "REG", "政策": "POL",
}


def _sid(name: str) -> str:
    for kw, pre in _PREFIX.items():
        if kw in name:
            return "DS_%s_%03d" % (pre, 0)      # 序号在下面按出现顺序补齐
    return "DS_OTH_%03d"


def _collect_names() -> List[str]:
    d = json.loads(_REPORT.read_text(encoding="utf-8", errors="replace"))
    er = d.get("enterprise_readable_report") or d
    seen: Dict[str, int] = {}
    for p in (er.get("confirmed_problems") or []):
        if not isinstance(p, dict):
            continue
        for np_ in (p.get("narrative_paragraphs") or []):
            for t in (np_.get("detail_tables") or []):
                if "构成要件" not in str((t or {}).get("title") or ""):
                    continue
                for r in (t.get("rows") or []):
                    if not isinstance(r, dict):
                        continue
                    for nm in re.split(r"[、,，/]", str(r.get("独立数据源") or "")):
                        nm = nm.strip()
                        if nm:
                            seen[nm] = seen.get(nm, 0) + 1
    return [k for k, _ in sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))], seen


def _existing() -> Dict[str, Any]:
    try:
        old = json.loads(_CFG.read_text(encoding="utf-8"))
        return {s.get("data_source_name"): s for s in (old.get("sources") or [])
                if isinstance(s, dict)}
    except Exception:                       # 首跑无旧文件，属正常路径
        return {}


def main() -> int:
    names, seen = _collect_names()
    old = _existing()
    out: List[Dict[str, Any]] = []
    for i, nm in enumerate(names, 1):
        prev = old.get(nm) or {}
        auth = AUTHORED.get(nm) or {}
        # 人工撰写字段优先级：**旧文件 > 生成器表**（用户在配置文件里改过的不得被覆盖）
        def _pick(key):
            v = prev.get(key)
            if v not in (None, "", []):
                return v
            return auth.get(key) or []
        out.append({
            "data_source_id": str(prev.get("data_source_id") or ("DS_%03d" % i)),
            "data_source_name": nm,
            "aliases": _pick("aliases"),
            "provided_by": _pick("provided_by"),
            "markers": _pick("markers"),
            "_seen": seen.get(nm, 0),
        })
    # 人工表里有、但本企业产物没出现的（保留，避免下次出现时丢配置）
    for nm, spec in AUTHORED.items():
        if nm in names:
            continue
        prev = old.get(nm) or {}
        out.append({"data_source_id": str(prev.get("data_source_id") or ("DS_X_%03d" % len(out))),
                    "data_source_name": nm,
                    "aliases": prev.get("aliases") or spec.get("aliases") or [],
                    "provided_by": prev.get("provided_by") or spec.get("provided_by") or [],
                    "markers": prev.get("markers") or spec.get("markers") or [],
                    "_seen": 0})
    cfg = {
        "schema": 1, "version": "1.0.0", "updated": "2026-10-07",
        "note": ("数据源状态表（唯一权威=本文件）。由 scripts/_gen_data_sources.py 从真实产物派生；"
                 "aliases/provided_by/markers 为**人工撰写字段**，重生成时原样保留（不会被覆盖）。"
                 "口径：provided_by 只写**能证实的包含关系**（如确认单编号是数电红字发票的字段）；"
                 "markers 只写**专有标识名**（如「红字发票信息确认单编号」），不写泛词。"
                 "新增数据源只加一行 ⇒ 自动纳入一致性校验（门禁 check_data_source_status_consistency）。"),
        "status_vocab": ["已有", "缺失", "须核对", "待企业提交"],
        "fields": ["data_source_id", "data_source_name", "aliases", "provided_by", "markers"],
        "sources": out,
    }
    _CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_done = sum(1 for s in out if s["provided_by"] or s["markers"])
    print("已生成 %s：数据源 %d 个（其中带硬证据/包含关系 %d 个）" % (_CFG.name, len(out), n_done))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
