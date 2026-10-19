# -*- coding: utf-8 -*-
"""AI 辅助分析（P2-3）—— **唯一权威**「AI 辅助」层。

★★ 硬约束（任务书）：「**AI 辅助不替代规则，只做辅助**」。本模块用三道机制保证它：

  ① **角色声明**：每个产出都带 `role="advisory"` / `advisory_only=True` /
     `replaces_rules=False` / `disclaimer`（警示语唯一权威 = `DISCLAIMER`）；
  ② **不产出判定**：辅助输出**只允许**写"可解释性/线索/待核项/询问提纲"，
     `FORBIDDEN_CLAIM_TERMS` 里的"定性"用语（认定/已构成/应补缴…）会被**清洗拦截**——
     `sanitize()` 命中即改写为"待人工复核"，绝不把 AI 文本当成规则结论；
  ③ **可用性如实**：LLM 不可用（未配置云端 key 且本机无 Ollama）⇒ `available=false` +
     `reason`，此时**回落到"规则侧线索"**（`engine="rule_hint"`，`is_ai=false`），
     **绝不**把确定性拼接的内容冒充成 AI 输出。

数据来源（可溯源）：`engine.llm_client`（LLM 可用性与调用，唯一权威）、
`engine.legal_citation`（法条引用补全，唯一权威）、调用方传入的 payload。
本模块**不做**任何风险判定、不改等级/金额；只读 + 文本生成。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

ROLE = "advisory"

#: 警示语**唯一权威**（任何界面/接口展示 AI 辅助内容时必须带上它；不得另写一份）
DISCLAIMER = (
    "本内容由 AI 辅助生成，**仅供线索参考，不构成风险认定**；"
    "不得替代规则引擎的判定，一切结论以规则引擎结果与人工复核为准。"
)

#: 禁用"定性"用语（命中即清洗）—— AI 文本里出现这些词，等于把辅助当成判定
FORBIDDEN_CLAIM_TERMS: Tuple[str, ...] = (
    "已构成违规", "已构成违法", "已认定", "应当补缴", "应补缴", "必须补缴",
    "定性为", "确认为违规", "已定性", "结论为违规",
)
_SAFE_REPLACEMENT = "（待人工复核）"

#: ★ 辅助能力清单（**唯一权威**：新增一种辅助只加一行）
CAPABILITIES: Tuple[Dict[str, str], ...] = (
    {"code": "explain_finding", "label": "解释风险事项",
     "input": "finding: 风险事项对象（可选）",
     "desc": "用通俗语言解释该事项的判断口径与法律依据；不改等级、不改金额"},
    {"code": "suggest_materials", "label": "建议补充资料",
     "input": "findings: 风险事项列表（可选）",
     "desc": "提示为核实这些事项通常还需要哪些资料（线索，非要求）"},
    {"code": "draft_inquiry", "label": "生成询问提纲",
     "input": "findings: 风险事项列表（可选）",
     "desc": "按事项生成向企业询问的提纲草稿（供人工增删）"},
    {"code": "summarize_risks", "label": "归纳疑点清单",
     "input": "findings: 风险事项列表",
     "desc": "把风险事项归纳为清单摘要（不改口径、不新增事项）"},
)

_CAP_BY_CODE = {c["code"]: c for c in CAPABILITIES}


class AiAssistError(Exception):
    """AI 辅助层的业务异常（边界统一转 HTTP 状态码）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# ── 清洗：把"定性"用语改写为待核（AI 不得越权下结论）───────────────────────
def sanitize(text: str) -> Tuple[str, List[str]]:
    """清洗 AI 文本中的**定性用语**；返回 (清洗后文本, 命中词列表)。

    ★ 命中即改写为「（待人工复核）」——**只改措辞、不改事实**；命中词会被如实记录，
      供调用方展示"本文本曾被改写"，避免读者误以为 AI 下了结论。
    """
    s = str(text or "")
    hits: List[str] = []
    for term in FORBIDDEN_CLAIM_TERMS:
        if term in s:
            hits.append(term)
            s = s.replace(term, _SAFE_REPLACEMENT)
    return s, hits


def _pick_findings(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    items = (payload or {}).get("findings")
    if items is None:
        items = (payload or {}).get("items")
    if isinstance(items, dict):
        items = [items]
    return [x for x in (items or []) if isinstance(x, dict)]


def _f_title(x: Dict[str, Any]) -> str:
    return str(x.get("title") or x.get("finding") or x.get("name")
               or x.get("risk_no") or x.get("事项") or "").strip()


def _f_level(x: Dict[str, Any]) -> str:
    return str(x.get("level") or x.get("risk_level") or x.get("等级") or "").strip()


def _legal_basis(x: Dict[str, Any]) -> str:
    """取一条发现的可呈现法律依据（转发 legal_citation，不另写字段优先级）。"""
    try:
        from engine.legal_citation import legal_reference_of, format_legal_basis  # noqa: PLC0415
    except Exception:                                          # noqa: BLE001
        return ""
    ref = ""
    for f in ("policy_ref", "law_ref", "legal_ref"):
        v = str(x.get(f) or "").strip()
        if v:
            ref = v
            break
    if not ref:
        return ""
    try:
        return format_legal_basis([ref])
    except Exception:                                          # noqa: BLE001
        return ref


# ── 规则侧线索（**确定性**拼接；`is_ai=false`，绝不冒充 AI）───────────────
def rule_hint(code: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """不依赖 LLM 的确定性线索（输入不足 ⇒ 返回 None，**不编造**）。"""
    payload = payload or {}
    if code == "explain_finding":
        one = payload.get("finding")
        if not isinstance(one, dict):
            fs = _pick_findings(payload)
            one = fs[0] if fs else None
        if not isinstance(one, dict):
            return None
        basis = _legal_basis(one)
        return {"title": _f_title(one), "level": _f_level(one),
                "legal_basis": basis,
                "points": [p for p in [
                    "等级与金额以规则引擎结果为唯一口径，本线索不改动。",
                    ("该事项引用的法律依据：" + basis) if basis else "本条未登记可呈现的法律依据。",
                    "如需进一步核实，请补充与该事项直接相关的原始凭证与账簿记录。",
                ] if p]}
    if code == "summarize_risks":
        fs = _pick_findings(payload)
        if not fs:
            return None
        return {"count": len(fs),
                "items": [{"title": _f_title(x), "level": _f_level(x)} for x in fs]}
    if code in ("suggest_materials", "draft_inquiry"):
        fs = _pick_findings(payload)
        if not fs:
            return None
        if code == "suggest_materials":
            return {"items": ["针对「%s」请提供：合同/协议、发票、资金流水、出入库单据（择其相关者）"
                              % (_f_title(x) or "该事项") for x in fs]}
        return {"items": ["请说明「%s」的业务实质、定价依据与资金流向。" % (_f_title(x) or "该事项")
                          for x in fs]}
    return None


# ── LLM 侧（可用时才调用；产出仍带 advisory 声明 + 清洗）────────────────────
_SYSTEM_PROMPT = (
    "你是税务风险分析的**辅助**助手。请严格按以下要求回答：\n"
    "1) 只提供**线索、待核项、询问提纲、通俗解释**；\n"
    "2) **不得**给出风险是否成立的定性结论，不得使用「已构成/已认定/应补缴」等措辞；\n"
    "3) 不得修改等级、金额、条文号；引用法规须与给定材料一致，缺材料就明说「需补充资料」；\n"
    "4) 用简体中文，简明分点。"
)


def _llm_advice(code: str, payload: Dict[str, Any]) -> Tuple[Optional[str], str, List[str]]:
    """调用 LLM（唯一权威 `llm_client`）。返回 (文本或 None, 后端, 被清洗词)。"""
    try:
        from engine.llm_client import get_llm                          # noqa: PLC0415
    except Exception as exc:                                           # noqa: BLE001
        return None, "unavailable", []
    client = get_llm()
    if not getattr(client, "available", False):
        return None, "unavailable", []
    cap = _CAP_BY_CODE.get(code) or {"label": code}
    user = ("辅助类型：%s\n可用材料（JSON）：\n%s"
            % (cap.get("label", code),
               json.dumps(payload or {}, ensure_ascii=False, default=str)[:6000]))
    try:
        resp = client.chat([{"role": "user", "content": user}],
                           system=_SYSTEM_PROMPT, temperature=0.2, max_tokens=1200)
        text = str(getattr(resp, "content", "") or "").strip()
    except Exception:                                                  # noqa: BLE001
        return None, "failed", []
    if not text:
        return None, str(getattr(client, "active_backend", "none")), []
    clean, hits = sanitize(text)
    return clean, str(getattr(client, "active_backend", "none")), hits


# ── 对外接口 ────────────────────────────────────────────────────────────────
def status() -> Dict[str, Any]:
    """AI 辅助可用性（**如实**）。转发布局唯一权威 `llm_client`。"""
    try:
        from engine.llm_client import get_llm                          # noqa: PLC0415
        client = get_llm()
        available = bool(getattr(client, "available", False))
        backend = str(getattr(client, "active_backend", "none"))
    except Exception as exc:                                           # noqa: BLE001
        return {"available": False, "backend": "unavailable",
                "reason": "LLM 客户端不可用：%s" % exc,
                "disclaimer": DISCLAIMER}
    return {
        "available": available,
        "backend": backend,
        "reason": "" if available else "未配置云端大模型且本机无可用本地模型（Ollama）",
        "disclaimer": DISCLAIMER,
        "note": ("AI 不可用时，`/ai-assist` 回落为规则侧线索（engine=rule_hint, is_ai=false），"
                 "不会假装成 AI 输出。"),
    }


def capabilities() -> Dict[str, Any]:
    return {
        "total": len(CAPABILITIES),
        "items": [dict(c) for c in CAPABILITIES],
        "role": ROLE,
        "replaces_rules": False,
        "disclaimer": DISCLAIMER,
        "forbidden_terms_note": ("AI 文本若出现「%s」等定性用语，将被改写为「%s」并如实记录"
                                 "（见 `sanitize`）。" % ("、".join(FORBIDDEN_CLAIM_TERMS[:3]),
                                                        _SAFE_REPLACEMENT.strip("（）"))),
    }


def assist(code: str, payload: Dict[str, Any], *, allow_llm: bool = True) -> Dict[str, Any]:
    """生成辅助内容（**永不**替代规则判定）。

    返回字段固定含：`role` / `advisory_only` / `replaces_rules` / `disclaimer`，
    调用方**必须**把它们一并展示（接口层照原样透出，不做裁剪）。
    """
    c = str(code or "").strip()
    if not c:
        raise AiAssistError("缺少辅助类型 code", 400)
    if c not in _CAP_BY_CODE:
        raise AiAssistError("未知的辅助类型：%s（可用：%s）"
                            % (c, "、".join(x["code"] for x in CAPABILITIES)), 400)

    payload = payload if isinstance(payload, dict) else {}
    out: Dict[str, Any] = {
        "code": c,
        "label": _CAP_BY_CODE[c]["label"],
        "role": ROLE,
        "advisory_only": True,
        "replaces_rules": False,
        "disclaimer": DISCLAIMER,
        "engine": "unavailable",
        "is_ai": False,
        "output": None,
        "sanitized_terms": [],
        "reason": "",
    }

    advice, backend, hits = (None, "unavailable", [])
    if allow_llm:
        advice, backend, hits = _llm_advice(c, payload)

    if advice:
        out.update({"engine": "llm", "is_ai": True, "is_backend": backend,
                    "sanitized_terms": hits,
                    "output": {"text": advice},
                    "reason": "" if not hits else "AI 文本中的定性用语已被改写为待核表述"})
        return out

    hint = rule_hint(c, payload)
    if hint is None:
        out["reason"] = ("AI 不可用，且输入不足（缺少 findings/finding）⇒ 未产出内容；"
                         "请提供风险事项后重试。")
        return out
    out.update({"engine": "rule_hint", "is_ai": False, "is_backend": backend,
                "output": hint,
                "reason": ("AI 辅助当前不可用，以下为**规则侧线索**（确定性拼接，非 AI 生成）。"
                           if backend == "unavailable"
                           else "AI 调用未产出内容，以下为规则侧线索。")})
    return out


__all__ = ["ROLE", "DISCLAIMER", "FORBIDDEN_CLAIM_TERMS", "CAPABILITIES",
           "AiAssistError", "sanitize", "status", "capabilities", "assist", "rule_hint"]
