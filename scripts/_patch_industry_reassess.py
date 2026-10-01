# -*- coding: utf-8 -*-
"""注入 engine/industry_resolver.py：行业「随资料再判读」（reassess_industry）

行尾纪律：读/写一律 newline=""（保 CRLF），注入内容统一 \r\n。
幂等：已含哨兵标记则跳过。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "engine", "industry_resolver.py")
SENTINEL = "# ── 行业「随资料再判读」（industry_reassess）────────────────────────────"

BLOCK = u'''
# ── 行业「随资料再判读」（industry_reassess）──────────────────────────────
#    观点来源（用户 2026-10-02）：「对行业的判断应该是随着系统接收到的资料和
#    信息后，经重新判读后再次确认或变更行业」。
#
#    现状（为什么需要）：行业过去只在 `_detect_target_entity` 里定一次，之后
#    合同、进项票、资料清单陆续到位也不再回头看——于是"经营范围只写销售/贸易"
#    的企业被购销兜底口径一次性钉死成「商贸」，全链（行业对标 / 成本费用口径 /
#    行业门控）都跟着错，且**错得很静默**。
#
#    设计铁律：
#      ★ 再判读**只能推翻、不能凭空定**：没有新证据一律 insufficient（不猜）。
#      ★ 新行业必须是**具体行业**（`service_industries` 映射），购销兜底口径
#        （商贸/商贸批发/商贸零售/外贸/电子商务）不算行业，不构成变更依据。
#      ★ 商品/物料名不算行业（沿用铁律 R1，只采纳 service 侧映射）。
#      ★ 决策三态 change / keep / insufficient，全部留痕进 pipeline_log。


def industry_hints_from_text(text: str) -> Dict[str, int]:
    """从任意一段文本抽「行业级线索」投票表（行业名 -> 命中次数）。

    判据与 `scope_industry_hint` 同源：只采纳 `industry_map` 中映射到
    `service_industries` 的关键词；排除购销兜底口径；归一化后同名合并。
    """
    text = str(text or "")
    if not text.strip():
        return {}
    im = load_industry_data().get("industry_map") or {}
    svc = set(load_industry_data().get("service_industries") or [])
    raw = {}
    for kw, ind in im.items():
        k = str(kw or "").strip()
        if not k or k not in text:
            continue
        v = str(ind or "")
        if not v or v not in svc or v in _TRADE_FALLBACK_INDUSTRIES:
            continue
        raw[v] = raw.get(v, 0) + 1
    if not raw:
        return {}
    merged = {}
    for v, n in raw.items():
        k = normalize_industry_name(v) or v
        merged[k] = merged.get(k, 0) + n
    if not merged:
        return {}
    # 票数降序、同票取名字更长的（更具体）——禁 hash 序，保证可复现
    return dict(sorted(merged.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0])))


def reassess_industry(current_industry: str = "", *,
                      purchase_goods=None,
                      material_hints=None,
                      contract_text: str = "",
                      current_source: str = "",
                      pipeline_log: Optional[List[str]] = None) -> Dict[str, Any]:
    """资料收齐后，用**新增**证据对行业做一次再判读（唯一权威）。

    证据三路，均为弱证据，不能单独定行业，只能推翻或确认：
      ① `purchase_goods` 进项发票品名（采购侧实际买的东西）
      ② `material_hints` 已上传资料的文件名 / 资料类型（如「广告设计合同.docx」）
      ③ `contract_text` 合同 / 协议文本

    决策规则（★ 只有「一致」才改，不一致一律 keep，绝不猜）：
      · 新行业 == current            → keep（已一致，无需变更）
      · current 是**购销兜底口径**
        （商贸/商贸批发/商贸零售/外贸/电子商务）→ 只要有 ≥1 路证据指向某个具体行业，
        就 change（兜底本就低置信，用户场景正是"先判商贸、后凭合同取证为广告传媒"）
      · current 是**高权威口径**（销项品名 / 外部工商 / 工商登记）
        → 须 ≥2 路证据**同时**指向同一个具体行业才 change，否则 keep
      · 无任何新证据                  → insufficient

    返回：{industry, decision, evidence, reason, from_fallback}
    """
    cur = normalize_industry_name(current_industry) or str(current_industry or "")
    goods = purchase_goods or []
    mats = material_hints or []

    routes = [
        ("进项票品名", " ".join(str(g or "") for g in goods)),
        ("资料与文件名", " ".join(str(m or "") for m in mats)),
        ("合同文本", str(contract_text or "")),
    ]
    evidence: Dict[str, Dict[str, int]] = {}
    by_route: Dict[str, str] = {}
    merged: Dict[str, int] = {}
    for name, text in routes:
        if not str(text or "").strip():
            continue
        hits = industry_hints_from_text(text)
        if not hits:
            continue
        top = sorted(hits.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[0][0]
        evidence[name] = hits
        by_route[name] = top
        merged[top] = merged.get(top, 0) + 1

    if not evidence:
        _log(pipeline_log, "[行业再判读] 未取得任何新证据（进项品名/资料/合同均无行业级线索），"
                          "保持原行业口径 '%s'" % cur)
        return {"industry": cur, "decision": "insufficient", "evidence": {},
                "from_fallback": cur in _TRADE_FALLBACK_INDUSTRIES,
                "reason": "无新证据，不做变更"}

    # ★ 只认「≥2 路证据同时指向同一行业」；单路证据不足以推翻高权威口径
    top_ind, top_routes = None, 0
    for ind in sorted(merged.keys()):
        n = merged[ind]
        if top_ind is None or n > top_routes or (n == top_routes and len(ind) > len(top_ind)):
            top_ind, top_routes = ind, n

    is_fallback = cur in _TRADE_FALLBACK_INDUSTRIES
    if top_ind == cur:
        _log(pipeline_log, "[行业再判读] 新证据仍指向 '%s'（%d 路），确认原口径不变更" % (cur, top_routes))
        return {"industry": cur, "decision": "keep", "evidence": evidence,
                "from_fallback": is_fallback, "reason": "新证据与原口径一致"}

    enough = (top_routes >= 2) or (is_fallback and top_routes >= 1)
    if not enough:
        _log(pipeline_log, "[行业再判读] 新证据仅 %d 路指向 '%s'（原口径 '%s' 非兜底），"
                          "证据不足以推翻，保持原口径" % (top_routes, top_ind, cur))
        return {"industry": cur, "decision": "keep", "evidence": evidence,
                "from_fallback": is_fallback,
                "reason": "仅单路弱证据，不得推翻高权威口径"}

    reason = ("原口径 '%s' 属购销兜底（低置信），新证据 %d 路一致指向 '%s'"
              % (cur, top_routes, top_ind)) if is_fallback else \
             ("新证据 %d 路一致指向 '%s'，超过原口径（来源 %s）" % (top_routes, top_ind, current_source))
    _log(pipeline_log, "[行业再判读] 行业口径变更：'%s' → '%s'；%s" % (cur, top_ind, reason))
    _industry_reassess_log(pipeline_log, "[行业再判读] 行业口径变更：'%s' → '%s'；%s"
                           % (cur, top_ind, reason))
    return {"industry": top_ind, "decision": "change", "evidence": evidence,
            "from_fallback": is_fallback, "reason": reason}


'''


def main():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if SENTINEL in src:
        print("SKIP: already injected")
        return 0
    if not src.endswith("\n"):
        src += "\r\n"
    block = BLOCK.replace("\n", "\r\n")
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(src + block)
    print("OK: injected into %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
