# -*- coding: utf-8 -*-
"""风险复核（人工处置）——**唯一权威**。

本模块回答一个问题：**某一条风险事项，人工处置到什么地步了**。

## 与既有 `finding.review` 的区别（★ 防「同一概念两处口径」）

| 名称 | 含义 | 权威 |
|---|---|---|
| `finding.review`（**既有，不动**） | **引擎数据一致性复核**：重解析源文件、与结论交叉比对，回答「结论可靠吗」 | `main._review_report` / `_review_finding` |
| `risk.review`（**本模块**） | **人工处置复核**：人对风险的处置意见（确认/排除/误报/整改/转人工），回答「这条风险**怎么处置**了」 | 本模块 |

两者**视角不同、产出不同、均不得互相顶替**：前者产出"错误/警告/通过"，后者产出 5 态处置状态。
故本模块用**独立的审计动作** `risk.review` / `risk.comment` / `risk.rectify`，
**不改写、不消费** `finding.review`。

## 铁律

1. **复核不改定性**：`risk_level` / `conclusion_grade` 的唯一权威是
   `engine/risk_levels.py` 与报告链；本模块**只写处置状态**，任何动作都**不修改等级字段**。
   （复核若能把高风险"改"成低风险，结论严重度就被人手悄悄改掉了。）
2. **不猜**：理由/说明为空的动作（排除、误报、已整改、重开）**拒绝执行并说明原因**，
   不生成"无理由的处置"。
3. **追加式**：处置历史 append-only 落 `data/risk_reviews.jsonl`，当前态由**折叠**得到
   （沿用 `engine/analysis_jobs` 的同一惯用法）；**不物理改写历史**。
4. **编号不自行拼接**：整改台账编号走唯一权威 `engine/numbering.NumberingService`。
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "REVIEW_STATES", "STATE_CN", "STATE_FLOW", "REVIEW_ACTIONS",
    "ACTION_CN", "ACTION_TO_STATE", "NOTE_REQUIRED", "TERMINAL_STATES",
    "RiskReviewError", "reviews_path", "last_errors",
    "get", "states_of", "review", "comment", "rectifications",
    "metadata", "reset_cache",
]

# ══════════════════════════════════════════════════════════════════════════
# 状态机（★ 唯一权威：新增一态只加这里一处）
# ══════════════════════════════════════════════════════════════════════════
#: 任务书要求的 5 态（**不加第 6 态**：'转人工' 是**动作**产生的标记，不是状态）
REVIEW_STATES: Tuple[str, ...] = (
    "pending", "confirmed", "excluded", "rectified", "false_positive",
)

STATE_CN: Dict[str, str] = {
    "pending": "待处理",
    "confirmed": "已确认",
    "excluded": "已排除",
    "rectified": "已整改",
    "false_positive": "误报",
}

#: 合法迁移（**唯一处**）。终态允许「重新打开」回到 `pending`（纠错的唯一出口）。
STATE_FLOW: Dict[str, Tuple[str, ...]] = {
    "pending": ("confirmed", "excluded", "false_positive"),
    "confirmed": ("rectified", "excluded", "pending"),
    "excluded": ("pending",),
    "rectified": ("pending",),
    "false_positive": ("pending",),
}

#: 终态（已处置完毕；仍需允许重开，故不叫"不可变"）
TERMINAL_STATES: Tuple[str, ...] = ("confirmed", "excluded", "rectified", "false_positive")

#: 复核动作（★ 唯一权威：新增一动作只加这里一处）
REVIEW_ACTIONS: Tuple[str, ...] = (
    "confirm",        # 确认（风险成立）
    "exclude",        # 排除（有合理解释，不认定为风险）
    "false_positive",  # 误报（引擎判断有误）
    "rectify",        # 标记已整改并登记整改台账（**必须**附整改说明）
    "to_manual",      # 转人工（不改状态，仅打"需人工深度介入"标记）
    "reopen",         # 重新打开（回到待处理；**必须**附原因）
)

ACTION_CN: Dict[str, str] = {
    "confirm": "确认成立",
    "exclude": "排除",
    "false_positive": "误报",
    "rectify": "标记已整改（登记整改台账）",
    "to_manual": "转人工",
    "reopen": "重新打开",
}

#: 动作 → 目标状态（`None` = 不改状态）
ACTION_TO_STATE: Dict[str, Optional[str]] = {
    "confirm": "confirmed",
    "exclude": "excluded",
    "false_positive": "false_positive",
    "rectify": "rectified",
    "to_manual": None,
    "reopen": "pending",
}

#: 必须附理由/说明的动作（**空则拒绝**，不生成无理由处置）
NOTE_REQUIRED: Tuple[str, ...] = ("exclude", "false_positive", "rectify", "reopen")

DEFAULT_STATE = "pending"

_LOCK = threading.RLock()
_LAST_ERROR = ""


def _log(msg: str) -> None:
    """留痕（绝不静默）。"""
    try:
        import sys as _sys
        print("[risk-review] %s" % msg, file=_sys.stderr, flush=True)
    except Exception:                                     # noqa: BLE001
        pass


def last_errors() -> str:
    """最近一次错误（供自检/接口如实暴露）。"""
    return _LAST_ERROR


class RiskReviewError(Exception):
    """复核层错误（`status` 为 HTTP 语义码，由 API 层转 `HTTPException`）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = int(status)


# ══════════════════════════════════════════════════════════════════════════
# 存储（append-only + 折叠，沿用 analysis_jobs 惯用法）
# ══════════════════════════════════════════════════════════════════════════
def reviews_path() -> Path:
    """复核事件流水路径。

    ★ 延迟导入 `runtime_storage`：`DATA_DIR` 在**该模块 import 时**由 `APP_DATA_DIR`
      固化，故必须在使用时取，不能在本模块顶层固化（否则隔离实例越界写生产数据）。
    """
    from runtime_storage import DATA_DIR                     # noqa: PLC0415
    return Path(DATA_DIR) / "risk_reviews.jsonl"


def _append_event(row: Dict[str, Any]) -> None:
    """追加一条复核事件。

    ★ **薄转发** `runtime_storage.append_jsonl`（"JSONL 落盘"的唯一权威）。
      收敛理由（2026-10-13）：原 `_append_row` 与 `engine/analysis_jobs._append_row`
      **字节级相同**（仅文件路径不同）⇒ 属"同一概念两处实现"，已收敛到落盘权威。
    """
    from runtime_storage import append_jsonl                 # noqa: PLC0415
    append_jsonl(reviews_path(), row)


def _load_events() -> List[Dict[str, Any]]:
    """读出全部复核事件；坏行**计数留痕**（不静默丢弃）。

    ★ **薄转发** `runtime_storage.read_jsonl`（唯一实现）；**留痕文案属本模块**，故在此处写。
    """
    global _LAST_ERROR
    from runtime_storage import read_jsonl                   # noqa: PLC0415
    try:
        rows, bad = read_jsonl(reviews_path())
    except Exception as exc:                                 # noqa: BLE001
        _LAST_ERROR = "读取复核流水失败：%s" % exc
        _log(_LAST_ERROR)
        return []
    if bad:
        _LAST_ERROR = "复核流水有 %d 行无法解析（已跳过，未静默）" % bad
        _log(_LAST_ERROR)
    return rows


def reset_cache() -> None:
    """本模块无进程内缓存（每次读盘）⇒ 保留同名函数仅为闸门一致性（见 _DIVERGENCE_OK）。"""
    global _LAST_ERROR
    _LAST_ERROR = ""


# --------------------------------------------------------------------------
# 折叠：事件流 → 当前态
# --------------------------------------------------------------------------
def _blank(risk_no: str, company_id: Any = 0) -> Dict[str, Any]:
    return {
        "risk_no": str(risk_no or ""),
        "company_id": int(company_id or 0),
        "state": DEFAULT_STATE,
        "state_cn": STATE_CN[DEFAULT_STATE],
        "manual_required": False,
        "rectification_no": "",
        "rectification_note": "",
        "updated_at": "",
        "updated_by": "",
        "comments": [],
        "history": [],
        "reviewed": False,       # 是否已有人工处置过（含批注/转人工）
    }


def _collapse(rows: List[Dict[str, Any]],
              company_id: Any = None) -> Dict[str, Dict[str, Any]]:
    """按 `risk_no` 折叠出当前态（**同 id 去重，最后一次胜出**）。"""
    want = None
    if company_id is not None and str(company_id).strip() != "":
        try:
            want = int(company_id)
        except Exception:                                 # noqa: BLE001
            want = None
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        rn = str(r.get("risk_no") or "").strip()
        if not rn:
            continue
        if want is not None:
            try:
                rc = int(r.get("company_id") or 0)
            except Exception:                             # noqa: BLE001
                rc = 0
            if rc != want and rc != 0:
                continue
        rec = out.setdefault(rn, _blank(rn, r.get("company_id")))
        ev = str(r.get("event") or "")
        at = str(r.get("at") or "")
        actor = str(r.get("actor") or "")
        if ev == "comment":
            rec["comments"].append({
                "seq": len(rec["comments"]) + 1,
                "at": at, "author": actor,
                "author_id": str(r.get("actor_id") or ""),
                "text": str(r.get("note") or ""),
            })
            rec["reviewed"] = True
            if at:
                rec["updated_at"] = at
                rec["updated_by"] = actor
            continue
        if ev == "to_manual":
            rec["manual_required"] = True
            rec["reviewed"] = True
        if ev == "review":
            to = str(r.get("to_state") or "")
            # ★ 标记位**以事件行为准**（`to_manual` 也走 `event=review`，只是 `action=to_manual`）
            if "manual_required" in r:
                rec["manual_required"] = bool(r.get("manual_required"))
            if to and to != "pending":
                rec["state"] = to
                rec["state_cn"] = STATE_CN.get(to, to)
            elif to == "pending":
                rec["state"] = "pending"
                rec["state_cn"] = STATE_CN["pending"]
            if r.get("rectification_no"):
                rec["rectification_no"] = str(r["rectification_no"])
            if r.get("rectification_note"):
                rec["rectification_note"] = str(r["rectification_note"])
            rec["reviewed"] = True
        rec["history"].append({
            "at": at, "event": ev,
            "action_cn": ACTION_CN.get(str(r.get("action") or ""), str(r.get("action") or "")),
            "from": str(r.get("from_state") or ""),
            "to": str(r.get("to_state") or ""),
            "to_cn": STATE_CN.get(str(r.get("to_state") or ""), ""),
            "actor": actor,
            "note": str(r.get("note") or ""),
            "rectification_no": str(r.get("rectification_no") or ""),
        })
        if at:
            rec["updated_at"] = at
            rec["updated_by"] = actor
    for rec in out.values():
        rec["state_cn"] = STATE_CN.get(rec["state"], rec["state"])
        rec["is_terminal"] = rec["state"] in TERMINAL_STATES
    return out


def states_of(company_id: Any = None) -> Dict[str, Dict[str, Any]]:
    """某账套（或全量）当前复核态：`{risk_no: 当前态}`。"""
    return _collapse(_load_events(), company_id)


def get(risk_no: Any, company_id: Any = None) -> Dict[str, Any]:
    """单条当前态；**无记录也返回 pending 空态**（不是 404 —— 未复核是正常状态）。"""
    rn = str(risk_no or "").strip()
    if not rn:
        raise RiskReviewError("风险编号（risk_no）不能为空", 400)
    return states_of(company_id).get(rn) or _blank(rn, company_id or 0)


def rectifications(company_id: Any = None) -> List[Dict[str, Any]]:
    """整改台账（已生成整改编号的条目，按时间倒序）。"""
    out: List[Dict[str, Any]] = []
    for r in _load_events():
        if not r.get("rectification_no"):
            continue
        if company_id is not None and str(company_id).strip() != "":
            try:
                if int(r.get("company_id") or 0) not in (int(company_id), 0):
                    continue
            except Exception:                                 # noqa: BLE001
                pass
        out.append({
            "rectification_no": str(r["rectification_no"]),
            "risk_no": str(r.get("risk_no") or ""),
            "company_id": int(r.get("company_id") or 0),
            "at": str(r.get("at") or ""),
            "author": str(r.get("actor") or ""),
            "measure": str(r.get("rectification_note") or ""),
            "state": "rectified",
            "state_cn": STATE_CN["rectified"],
        })
    out.sort(key=lambda x: (x["at"], x["rectification_no"]), reverse=True)
    return out


# ══════════════════════════════════════════════════════════════════════════
# 复核执行
# ══════════════════════════════════════════════════════════════════════════
def _now() -> str:
    try:
        from runtime_storage import now_cst                  # noqa: PLC0415
        return str(now_cst())
    except Exception:                                        # noqa: BLE001
        import datetime                                       # noqa: PLC0415
        return datetime.datetime.now().isoformat(timespec="seconds")


def _actor(session: Any) -> Tuple[str, str]:
    return (str(getattr(session, "username", "") or ""),
            str(getattr(session, "user_id", "") or ""))


def _next_rectification_no(company_id: Any, risk_no: str) -> str:
    """生成整改台账编号 —— 走**唯一权威** `engine/numbering.NumberingService`。

    ★ 禁止自行拼接 `WB-RC-...`：编号格式、宽度、连接符都在 `config/numbering.json`，
      本模块只负责"给第几个序号"。序号 = 本账套已登记整改数 + 1（确定性、可复现）。
    """
    from engine.numbering import NumberingService             # noqa: PLC0415
    company_code = ""
    period = ""
    try:
        from engine.numbering import load_rules as _lr        # noqa: PLC0415
        ns = NumberingService("", "", rules=_lr())
        parsed = ns.parse(risk_no) or {}
        body = str(parsed.get("body") or "")
        if body:
            parts = body.split(ns.connector)
            # body = "{company_code}-{period}" ⇒ 末段为期间，其余为统一社会信用代码
            period = parts[-1] if len(parts) >= 2 else ""
            company_code = ns.connector.join(parts[:-1]) if len(parts) >= 2 else body
    except Exception:                                        # noqa: BLE001
        pass
    seq = len(rectifications(company_id)) + 1
    ns2 = NumberingService(company_code, period)
    no = ns2.make("rectify", seq)
    if not no:
        _log("整改编号生成失败：company_code=%r period=%r seq=%d（见 numbering errors）"
             % (company_code, period, seq))
    return no


def review(risk_no: Any, action: Any, session: Any, *,
           company_id: Any = None, note: str = "",
           request: Any = None, engine: Any = None) -> Dict[str, Any]:
    """执行一次复核动作，返回**动作后**的当前态。

    ★ 校验顺序：动作合法 → 理由齐备 → **状态迁移合法** → 落盘 → 审计。
      「相同动作重复执行」按**幂等**处理（不重复追问、不重复写历史，如实告知 `noop`）。
    """
    rn = str(risk_no or "").strip()
    if not rn:
        raise RiskReviewError("风险编号（risk_no）不能为空", 400)
    act = str(action or "").strip()
    if act not in REVIEW_ACTIONS:
        raise RiskReviewError(
            "未知复核动作：%r（合法值：%s）"
            % (act, "、".join(REVIEW_ACTIONS)), 400)
    txt = str(note or "").strip()
    if act in NOTE_REQUIRED and not txt:
        raise RiskReviewError(
            "「%s」必须填写理由/说明（不生成无理由的处置）" % ACTION_CN.get(act, act), 400)

    cid = 0
    try:
        cid = int(company_id or 0)
    except Exception:                                        # noqa: BLE001
        cid = 0

    cur = get(rn, cid or None)
    now_state = str(cur.get("state") or DEFAULT_STATE)
    target = ACTION_TO_STATE.get(act)

    # 幂等：同一动作、同一目标状态，且已有记录 ⇒ 不重复写
    if target is not None and target == now_state and cur.get("reviewed"):
        out = dict(cur)
        out["noop"] = True
        out["message"] = "该风险已处于「%s」，本次未产生变更" % STATE_CN.get(target, target)
        return out
    # 幂等：转人工已标记
    if act == "to_manual" and cur.get("manual_required"):
        out = dict(cur)
        out["noop"] = True
        out["message"] = "该风险已标记为「转人工」，本次未产生变更"
        return out

    if target is not None and target != now_state:
        allowed = STATE_FLOW.get(now_state, ())
        if target not in allowed:
            raise RiskReviewError(
                "状态非法迁移：%s → %s（当前状态「%s」允许迁移到：%s）"
                % (STATE_CN.get(now_state, now_state), STATE_CN.get(target, target),
                   STATE_CN.get(now_state, now_state),
                   "、".join(STATE_CN.get(s, s) for s in allowed) or "无"),
                400)

    rect_no = ""
    rect_note = ""
    if act == "rectify":
        rect_no = _next_rectification_no(cid, rn)
        rect_note = txt

    actor, actor_id = _actor(session)
    row: Dict[str, Any] = {
        "at": _now(), "event": "review", "action": act,
        "risk_no": rn, "company_id": cid,
        "from_state": now_state, "to_state": (target if target is not None else now_state),
        "note": txt, "actor": actor, "actor_id": actor_id,
        "manual_required": True if act == "to_manual" else bool(cur.get("manual_required")),
    }
    if rect_no:
        row["rectification_no"] = rect_no
        row["rectification_note"] = rect_note
    _append_event(row)

    # ── 审计（唯一权威 audit_trail；本模块只做薄转发，**不吞异常**）──
    _audit_action = "risk.rectify" if act == "rectify" else "risk.review"
    _detail = "「%s」%s" % (STATE_CN.get(now_state, now_state),
                            ACTION_CN.get(act, act))
    if target is not None and target != now_state:
        _detail += " → 「%s」" % STATE_CN.get(target, target)
    if rect_no:
        _detail += "；整改台账 %s" % rect_no
    if txt:
        _detail += "；说明：%s" % (txt[:200] if len(txt) > 200 else txt)
    _record(_audit_action, rn, cid, _detail, request, session)

    out = get(rn, cid or None)
    out["noop"] = False
    out["action"] = act
    out["action_cn"] = ACTION_CN.get(act, act)
    out["message"] = "已完成「%s」：%s → %s" % (
        ACTION_CN.get(act, act), STATE_CN.get(now_state, now_state),
        STATE_CN.get(str(out.get("state")), str(out.get("state"))))
    return out


def comment(risk_no: Any, text: Any, session: Any, *,
            company_id: Any = None, request: Any = None) -> Dict[str, Any]:
    """追加一条批注（不改状态）。"""
    rn = str(risk_no or "").strip()
    if not rn:
        raise RiskReviewError("风险编号（risk_no）不能为空", 400)
    body = str(text or "").strip()
    if not body:
        raise RiskReviewError("批注内容不能为空", 400)
    cid = 0
    try:
        cid = int(company_id or 0)
    except Exception:                                        # noqa: BLE001
        cid = 0
    actor, actor_id = _actor(session)
    _append_event({"at": _now(), "event": "comment", "risk_no": rn,
                 "company_id": cid, "note": body,
                 "actor": actor, "actor_id": actor_id})
    _record("risk.comment", rn, cid,
            "批注：%s" % (body[:200] if len(body) > 200 else body), request, session)
    out = get(rn, cid or None)
    out["comment_count"] = len(out.get("comments") or [])
    out["message"] = "批注已登记"
    return out


def _record(action: str, target: str, company_id: Any, detail: str,
            request: Any, session: Any = None) -> None:
    """薄转发 `audit_trail.record`（**不放进 try/except:pass** —— 留痕失败必须可见）。

    ★ 操作人**在调用点显式给出**（`session` 就在手上），不依赖请求上下文：
      实测缺陷（2026-10-13）—— 只传 `request` 时，直接调 Service（无请求对象）的场景
      `audit_logs.user_name` 落成空串 ⇒ "谁复核的"追不到。显式传 `user_id`/`user_name`
      后，HTTP 与直调两条路径**都能追溯到人**。
    """
    from engine.audit_trail import record as _rec              # noqa: PLC0415
    uid = getattr(session, "user_id", None) if session is not None else None
    uname = str(getattr(session, "username", "") or "") if session is not None else ""
    _rec(action, target=target, company_id=(int(company_id) or None),
         detail=detail, request=request,
         user_id=(int(uid) if uid not in (None, "") else None),
         user_name=(uname or None))


# ══════════════════════════════════════════════════════════════════════════
# 字典
# ══════════════════════════════════════════════════════════════════════════
def metadata() -> Dict[str, Any]:
    """状态机与动作的字典（前端不硬编码中文名）。"""
    return {
        "states": [{"value": s, "label": STATE_CN[s]} for s in REVIEW_STATES],
        "actions": [{"value": a, "label": ACTION_CN[a],
                     "to_state": ACTION_TO_STATE[a],
                     "to_state_cn": STATE_CN.get(ACTION_TO_STATE[a] or "", ""),
                     "note_required": a in NOTE_REQUIRED}
                    for a in REVIEW_ACTIONS],
        "flow": {s: [{"to": t, "to_cn": STATE_CN[t]} for t in STATE_FLOW.get(s, ())]
                 for s in REVIEW_STATES},
        "terminal_states": list(TERMINAL_STATES),
        "default_state": DEFAULT_STATE,
        "note": ("处置状态唯一权威为本模块；★ 复核**不改动** `risk_level` / `conclusion_grade`"
                 "（等级唯一权威 engine/risk_levels.py）。与既有 `finding.review`（引擎数据"
                 "一致性复核）是**两个概念**，互不顶替。"),
        "storage": "data/risk_reviews.jsonl（append-only，当前态由折叠得到）",
    }
