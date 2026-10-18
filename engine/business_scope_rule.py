# -*- coding: utf-8 -*-
"""规则：**超经营范围开票预警**（RL-INV-005，2026-10-18 新增）。

问题
----
工商登记的经营范围，是"这家企业**依法可以从事什么**"的登记口径；销项发票的
「货物或应税劳务名称」是"它**实际申报卖了什么**"。两者对不上，是金税风险指标里
最经典的一类（开票品目与经营范围不符）——背后可能是：
  ① 超范围经营（本身不当然违法，除专营专卖/许可经营）；
  ② 开票内容与实际经营业务不符（这才是**虚开**指向，见《发票管理办法》第二十一条）；
  ③ 经营范围登记过时（企业已变更但未更新工商登记）。

口径（**只出预警，不作定性**）
------------------------------
· 输入：`companies.business_scope`（缺失则回退 `projects.business_scope`）+ 销项发票品名；
· 比对：品名 × 经营范围分段，**字符级相似度（字面包含 / 二元组 Jaccard / 字符重合率）**
  + **同义词组**（`config/business_info.json::scope_rule.synonym_groups`，加一行即扩一类）；
· 判级三档（阈值是配置，不写死在代码）：
    `score >= matched_at`      ⇒ 匹配（不报警）
    `score <  unmatched_below` ⇒ **不匹配**（进预警）
    其余                       ⇒ 不确定（**不报警**，只在回执里留痕）
  ⇒ 宁缺勿错：只有"明显对不上"才报，模糊一律不报（避免把"热轧钢板 vs 钢材"
    这种正常业务误报成虚开）。
· 缺失如实：拿不到经营范围 ⇒ **不产发现**，回执写"未取得经营范围，本项未参与"；
  拿不到销项发票 ⇒ 同上。绝不因为"没数据"就判定"没问题"或"有问题"。
· 等级：`scope_rule.level`（用户裁定「高风险」），`_level_locked=True`；
  文案里**必须**保留反证条（真实交易且不属专营专卖的，不构成本项）——不得删。

★ 与红线的接线：本模块只**算事实**，归属由 `config/redline_detector_attribution.json`
  声明（`mode="declared"`）；红线本体与法规依据在 `engine/tax_redlines.py::_BATCH_REDLINES`
  （RL-INV-005），条款映射由 `scripts/_gen_legal_mappings.py` 生成。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

RULE_ID = "RL-INV-005"

#: 依据（与红线 `legal_basis` 同源；此处只用于发现的 `law_ref` 展示）
LAW_REF = "《中华人民共和国发票管理办法》第二十一条"

_PUNCT = re.compile(r"[\s\u3000（）()\[\]【】、，,；;。：:·\-—_/\\|“”\"'‘’]+")


def goods_parts(text: Any) -> Tuple[str, str]:
    """拆分发票品名为 `(税收分类, 具体名称)`；无 `*类别*` 前缀时 `( "", 原文 )`。

    ★ 中国发票票面惯例是 `*税收分类*具体名称`：前半段是**税收分类编码名**（粗类目）、
      后半段是具体货物品名。两者都参与比对，任一命中即视为在范围内 ——
      否则「毛巾 × 日用百货」「口红 × 化妆品」这类**同义不同字**会全被判超范围
      （实测：纯按具体名称比对时，合规品名也报，规则会被用户直接关掉）。
    """
    s = str(text or "").strip()
    m = re.match(r"^\*([^*]*)\*\s*(.+)$", s)
    if m:
        cat, name = m.group(1).strip(), m.group(2).strip()
        return cat, (name or cat)
    m = re.match(r"^\*([^*]+)\*?\s*(.*)$", s)
    if m:
        cat, name = m.group(1).strip(), (m.group(2) or "").strip()
        return cat, (name or cat)
    return "", s


def goods_core(text: Any) -> str:
    """发票品名的**具体名称**部分（`*设计服务*设计服务费` → `设计服务费`）。"""
    return goods_parts(text)[1]


def _cfg() -> Dict[str, Any]:
    from engine.business_info.service import config      # noqa: PLC0415
    return dict((config().get("scope_rule") or {}))


# ─────────────────────── 取数（只读，不改任何表） ───────────────────────
def _engine_or_default(engine: Any = None) -> Any:
    if engine is not None:
        return engine
    from database import engine as _e                       # noqa: PLC0415
    return _e


def scope_of(company_id: Any, engine: Any = None) -> Tuple[Optional[str], str]:
    """该账套的**工商登记经营范围**。返回 `(scope, origin)`；取不到 ⇒ `(None, 原因)`。"""
    eng = _engine_or_default(engine)
    try:
        cid = int(company_id)
    except Exception:                                       # noqa: BLE001
        return None, "账套 ID 非法"
    try:
        from sqlalchemy import text as _text                 # noqa: PLC0415
        with eng.connect() as conn:
            row = conn.execute(_text(
                "SELECT business_scope FROM companies WHERE id=:c"), {"c": cid}).first()
            if row and str(row[0] or "").strip():
                return str(row[0]).strip(), "工商登记（companies.business_scope）"
            row = conn.execute(_text(
                "SELECT business_scope FROM projects WHERE company_id=:c "
                "AND business_scope IS NOT NULL AND business_scope<>'' "
                "ORDER BY id DESC LIMIT 1"), {"c": cid}).first()
            if row and str(row[0] or "").strip():
                return str(row[0]).strip(), "稽查项目（projects.business_scope）"
    except Exception as exc:                                # noqa: BLE001
        return None, "读取经营范围失败：%s" % type(exc).__name__
    return None, "未取得经营范围（工商登记与项目均无该字段）"


def _is_sales(inv: Dict[str, Any]) -> bool:
    d = str(inv.get("direction") or inv.get("kind") or "")
    if d in ("销项", "销售", "销项发票", "sales"):
        return True
    if d in ("进项", "采购", "进项发票", "purchase", "存疑"):
        return False
    return False          # 方向不明 ⇒ 不认定为销项（宁缺勿错）


def sales_goods(invoices: Optional[Iterable[Any]]) -> Tuple[List[str], int]:
    """销项发票的品名（去重、保序）。返回 `(goods_names, 销项发票张数)`。

    ★ 一张发票的 `goods` 可能是「A；B」聚合串 ⇒ 按分隔符再拆开（否则整串没法比）。
    """
    names: List[str] = []
    seen = set()
    n_inv = 0
    for inv in (invoices or []):
        if not isinstance(inv, dict) or not _is_sales(inv):
            continue
        n_inv += 1
        raw = inv.get("goods") or inv.get("货物或应税劳务名称") or ""
        for part in re.split(r"[；;、,，/\n]", str(raw)):
            g = part.strip()
            if not g or g in seen:
                continue
            seen.add(g)
            names.append(g)
    return names, n_inv


# ─────────────────────────── 相似度 ───────────────────────────
def _norm(s: Any) -> str:
    t = unicodedata.normalize("NFKC", str(s or ""))
    return _PUNCT.sub("", t).upper()


def _bigrams(s: str) -> set:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _strip_verbs(s: str, verbs: Sequence[str]) -> str:
    out = s
    for v in sorted([x for x in verbs if x], key=len, reverse=True):
        out = out.replace(v, "")
    return out or s


def _strip_suffix(s: str, suffixes: Sequence[str]) -> str:
    out = s
    for suf in sorted([x for x in suffixes if x], key=len, reverse=True):
        if len(out) > len(suf) + 1 and out.endswith(suf):
            out = out[:-len(suf)]
    return out or s


def _syn_groups(cfg: Dict[str, Any]) -> List[List[str]]:
    return [[_norm(x) for x in (g or []) if _norm(x)]
            for g in (cfg.get("synonym_groups") or [])]


def _expand(term: str, groups: List[List[str]]) -> List[str]:
    out = [term]
    for g in groups:
        if any(m and (m in term or term in m) for m in g):
            out.extend(m for m in g if m not in out)
    return out


def segments(scope: str, cfg: Optional[Dict[str, Any]] = None) -> List[str]:
    """把经营范围切成可比单元。

    ★ 顺序很重要（实测踩过）：
      ① **先整段剔除括号内容**——否则「金属材料加工（依法须经批准的项目…）」
         会被逗号切成两半，含套话那半被丢弃时把「金属材料加工」一起带走；
      ② 再按顿号/逗号/分号切；
      ③ 剔除登记机关套话（`scope_stop_words`）→ 剥动词 → 剥通用后缀；长度 < 2 丢弃。
    """
    cfg = cfg or _cfg()
    verbs = list(cfg.get("scope_verbs") or [])
    suffixes = list(cfg.get("generic_suffixes") or [])
    stops = [_norm(x) for x in (cfg.get("scope_stop_words") or []) if _norm(x)]
    # ★ 切句用唯一权威 `engine.sentencekit.split_sentences`（括号感知）：
    #   自写 `re.split` 会在括号内切错，切出「依法须经批准的项目」这类残句
    #   （实测踩过：残句参与相似度比对会把分数抬高，制造假匹配）。
    from engine.sentencekit import split_sentences        # noqa: PLC0415
    base = str(scope or "")
    out: List[str] = []
    for part in split_sentences(base, delims="、，,；;。\n"):
        part = re.sub(r"[（(][^）)]*[）)]", "", part)
        t = _norm(part)
        if not t:
            continue
        for sp in stops:
            t = t.replace(sp, "")
        t = _strip_verbs(t, verbs)
        t = _strip_suffix(t, suffixes)
        t = t.replace("的", "").strip()
        if len(t) >= 2 and t not in out:
            out.append(t)
    return out


def similarity(goods: str, seg: str, groups: List[List[str]]) -> float:
    """单个品名 vs 单个经营范围的相似度（0~1）。"""
    if not goods or not seg:
        return 0.0
    if goods == seg:
        return 1.0
    if len(goods) >= 2 and len(seg) >= 2 and (goods in seg or seg in goods):
        return 0.95
    for a in _expand(goods, groups):
        for b in _expand(seg, groups):
            if a == b:
                return 0.9
            if len(a) >= 2 and len(b) >= 2 and (a in b or b in a):
                return 0.88
    bg, bs = _bigrams(goods), _bigrams(seg)
    jac = len(bg & bs) / len(bg | bs) if (bg | bs) else 0.0
    cg, cs = set(goods), set(seg)
    common = len(cg & cs)
    # ★ 单个汉字重合**不是**相似证据：分母原用 `min()`，会把「设计服务费 × 服装」
    #   因共用「服」算成 0.33 ⇒ 全落「不确定」档（实测：9 项真实超范围品名零报警）。
    #   改为「分母取最长串 + 长词单字重合判 0」。
    if common <= 1 and min(len(cg), len(cs)) >= 3:
        ovl = 0.0
    else:
        ovl = common / max(len(cg), len(cs)) if (cg and cs) else 0.0
    return max(jac, ovl * 0.75)


def classify(goods_list: Sequence[str], scope: str,
             cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把品名逐条归类。返回 `{matched, unmatched, uncertain}`（每条含最佳分数与命中段）。"""
    cfg = cfg or _cfg()
    groups = _syn_groups(cfg)
    segs = segments(scope, cfg)
    matched_at = float(cfg.get("matched_at") or 0.5)
    low = float(cfg.get("unmatched_below") or 0.18)
    min_len = int(cfg.get("min_goods_len") or 2)
    ignore = {_norm(x) for x in (cfg.get("ignore_goods") or [])}

    out: Dict[str, List[Dict[str, Any]]] = {"matched": [], "unmatched": [], "uncertain": []}
    for g in goods_list:
        cat, name = goods_parts(g)
        ng = _norm(name)
        ncat = _norm(cat)
        if not ng or ng in ignore or len(ng) < min_len:
            continue
        best, best_seg = 0.0, ""
        for s in segs:
            sc = similarity(ng, s, groups)
            if ncat:
                sc = max(sc, similarity(ncat, s, groups))
            if sc > best:
                best, best_seg = sc, s
        item = {"goods": str(g).strip(), "score": round(best, 4), "segment": best_seg}
        if not segs:
            item["reason"] = "经营范围为空，无法比对"
            out["uncertain"].append(item)
        elif best >= matched_at:
            out["matched"].append(item)
        elif best < low:
            out["unmatched"].append(item)
        else:
            out["uncertain"].append(item)
    return out


# ───────────────────────── 发现构造 ─────────────────────────
def build_finding(cls: Dict[str, Any], scope: str, origin: str,
                  cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """把归类结果转成**报告可用**的发现（已打封印标）。"""
    cfg = cfg or _cfg()
    level = str(cfg.get("level") or "高风险")
    limit = int(cfg.get("max_goods_per_finding") or 8)
    unmatched = list(cls.get("unmatched") or [])[:limit]
    names = "、".join(i["goods"] for i in unmatched)
    tail = "" if len(cls.get("unmatched") or []) <= limit else \
        "等 %d 项" % len(cls.get("unmatched") or [])
    uncertain_n = len(cls.get("uncertain") or [])
    matched_n = len(cls.get("matched") or [])
    scope_short = scope if len(scope) <= 60 else scope[:60] + "…"

    body = ("销项发票开具「%s」%s，与工商登记经营范围（%s）无对应类目"
            "（字符相似度均低于 %s）。经营范围来源：%s。"
            "本轮已比对 %d 项销项品名：匹配 %d 项、不匹配 %d 项、不确定 %d 项（不确定不计入预警）。"
            % (names, tail,
               scope_short, cfg.get("unmatched_below") or 0.18, origin,
               matched_n + len(cls.get("unmatched") or []) + uncertain_n,
               matched_n, len(cls.get("unmatched") or []), uncertain_n))

    return {
        "type": "超经营范围开票预警",
        "fact_id": "BIZ-SCOPE-OVER-1",
        "scene_fact_id": "BIZ-SCOPE-OVER-1",
        "redline_id": "RL-INV-005",
        "rule_id": "RL-INV-005",
        "level": level,
        "score": float(cfg.get("score") or 6),
        "detail": body,
        "description": body,
        "source": "销项发票品名 × 工商登记经营范围（相似度比对）",
        "law_ref": LAW_REF,
        "legal_basis": [LAW_REF],
        "legal_basis_status": "grounded（据实开具义务；是否构成虚开须另行取证）",
        "tax_impact": "未量化（本条为预警线索，不能据此直接计算少缴税额）；"
                      "若查实属开票内容与实际经营业务不符，按虚开处理："
                      "补缴增值税及附加、企业所得税，并可能触发滞纳金与罚款。",
        "suggestion": "① 调取所涉品名的销售合同、出库单、运输单据与收款记录，"
                      "核实是否确有真实交易；② 核对营业执照经营范围是否已变更而未更新登记；"
                      "③ 属专营专卖/许可经营而无许可的，立即停止并补办；"
                      "④ 确认属真实交易且已依法登记的，保留证据并在复核中排除本项。",
        "conclusion_scope_note": "预警范围限于「开票品名与登记经营范围的字面可比性」，"
                                 "不构成虚开或超范围经营的定性；须由人工核实交易真实性与许可资质。",
        "final_answer": "预警：本账套存在销项开票品名与本企业登记经营范围无对应类目的情形，"
                        "须核实交易真实性与经营资质。",
        "category": "发票",
        "domain": "经营范围与开票品名",
        "independent_sources": ["销项发票明细", origin],
        "evidence": [{
            "type": "相似度比对表",
            "ref": "engine/business_scope_rule.py",
            "detail": "；".join("%s（相似度 %.2f，最近类目「%s」）"
                               % (i["goods"], i["score"], i["segment"] or "—")
                               for i in (cls.get("unmatched") or [])[:limit]),
        }],
        "policy_ref": LAW_REF,
        "_scenario_governed": True,
        "_level_locked": True,
    }


def collect_findings(company_id: Any, invoices: Optional[Iterable[Any]],
                     engine: Any = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """分析链入口：返回 `(findings, 回执)`。**任何异常都不外抛**（回执写明原因）。"""
    cfg = _cfg()
    receipt: Dict[str, Any] = {"enabled": bool(cfg.get("enabled", True)), "participated": False,
                               "scope_origin": "", "goods_total": 0, "sales_invoices": 0,
                               "matched": 0, "unmatched": 0, "uncertain": 0, "note": ""}
    if not receipt["enabled"]:
        receipt["note"] = "规则已关闭（config.business_info.scope_rule.enabled=false）"
        return [], receipt
    try:
        scope, origin = scope_of(company_id, engine)
        receipt["scope_origin"] = origin
        if not scope:
            receipt["note"] = "未取得经营范围 ⇒ 本项**未参与**（不据此判「无风险」）"
            return [], receipt
        goods, n_inv = sales_goods(invoices)
        receipt["goods_total"] = len(goods)
        receipt["sales_invoices"] = n_inv
        if not goods:
            receipt["note"] = "未取得销项发票品名 ⇒ 本项**未参与**"
            return [], receipt
        cls = classify(goods, scope, cfg)
        receipt.update({"matched": len(cls["matched"]),
                        "unmatched": len(cls["unmatched"]),
                        "uncertain": len(cls["uncertain"]),
                        "participated": True})
        if not cls["unmatched"]:
            receipt["note"] = "已比对 %d 项销项品名，未发现与经营范围无对应者" % len(goods)
            return [], receipt
        receipt["note"] = "命中 %d 项品名与经营范围无对应类目" % len(cls["unmatched"])
        return [build_finding(cls, scope, origin, cfg)], receipt
    except Exception as exc:                                  # noqa: BLE001
        receipt["note"] = "规则执行异常（%s）：本项未参与" % type(exc).__name__
        return [], receipt


__all__ = ["RULE_ID", "LAW_REF", "scope_of", "sales_goods", "segments",
           "similarity", "classify", "build_finding", "collect_findings"]
