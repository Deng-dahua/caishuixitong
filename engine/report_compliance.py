# -*- coding: utf-8 -*-
"""报告定位与合规装配（用户第 5 批 任务2「报告定位与合规」）。

## 任务要求 → 落点

| 要求 | 落点 |
|---|---|
| 报告名称改为「税务风险扫描工作底稿」/「风险提示函」，明确非执法文书 | `config/report_compliance.json.documents`（唯一权威）+ `document_meta()` |
| 编制人/复核人/审批人签名栏 + 日期 | `signature_block()`（`signatures` 表驱动） |
| 保密等级与用途限制 | `security_block()` |
| 数据获取授权说明（范围/存储/销毁） | `authorization_block()` |
| 系统生成标识（系统名/版本/生成时间/是否经人工复核） | `system_block()` |
| 企业申辩与反馈机制（期限/方式/复核流程） | `feedback_block()` |
| 版本控制与修改记录 | `record_version()` → `data/report_versions.jsonl`（append-only） |
| 对外版本与内部底稿分开 | `internal_edition()` / `external_edition()`（**两个对象**，后者调 `engine.redaction`） |
| 输出合规模板 | `compliance_block()`（一次性给出全部合规要素，可直接渲染） |

## 铁律

- 所有**面向企业/外部的文字**都在配置里，代码只装配（改文案不改代码）。
- **对外版本必须真脱敏**，且脱敏留痕（命中项与条数）；未命中也要如实说明"未命中"。
- 版本记录 append-only；**同一份报告重复生成也要留两条**（生成动作本身要可追溯）。
- 取不到编制人/复核人 ⇒ 写「待签署」并标注**未完成签署**，不得留空冒充已签署。
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: 报告名称唯一权威（Skill 5）：本模块只**薄转发**，不自持名称字面量
from engine.report_identity import canonical_name  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_COMPLIANCE = _ROOT / "config" / "report_compliance.json"
#: ★ 台账**路径**（`Path` 在调用时解析；见 `ledger_path()`）
_p_NAME = "report_versions.jsonl"


def ledger_path() -> Path:
    """版本台账路径（**唯一权威**）。

    ★★ 2026-10-13（P0-7 实测事故）：此前是模块级常量
      `_ROOT / "data" / "report_versions.jsonl"` —— **写死源码树路径、不随
      `APP_DATA_DIR`** ⇒ 隔离实例（测试子进程 / 冒烟脚本）会往**真实项目的台账**里
      追加行（实测：一次冒烟给真实台账写进 5 行 V136~V140，已备份后精确移除）。
      与 `runtime_storage.offline_reports_root()` 记录的 2026-10-06 事故**同一类**。

    规则（与 `offline_reports_root()` 一致）：
      · 设了 `APP_DATA_DIR` ⇒ `<APP_DATA_DIR>/report_versions.jsonl`（隔离实例，只写自己的）；
      · 未设（生产实例）⇒ `<project>/data/report_versions.jsonl`（现行位置，行为不变）。
    ★ 必须在**调用时**解析（模块 import 期 `APP_DATA_DIR` 可能尚未设置）。
    """
    app_data = os.environ.get("APP_DATA_DIR")
    if app_data:
        return Path(app_data) / _p_NAME
    return _ROOT / "data" / _p_NAME

#: 文稿类型（★ 唯一权威：与配置 documents 的键一一对应）
DOC_KINDS: Tuple[str, ...] = ("internal_working_paper", "external_notice")

_CACHE: Optional[Dict[str, Any]] = None


def load_config() -> Dict[str, Any]:
    """报告合规配置（config/report_compliance.json）**唯一读取入口**（★ 唯一权威）。

    ★ 2026-10-08 收敛：`engine/redaction.py` 曾自持一份 `_COMPLIANCE` 路径 + 解析
      逻辑读取**同一份文件**（两份实现，改路径即漂移）。现公开本入口，redaction
      只薄转发（`from engine.report_compliance import load_config`）。
    """
    global _CACHE
    if _CACHE is None:
        try:
            _CACHE = json.loads(_COMPLIANCE.read_text(encoding="utf-8"))
        except Exception:
            _CACHE = {}
    return _CACHE or {}


def _now() -> str:
    """★ 2026-10-08 收敛：北京时间戳统一到 runtime_storage.now_cst()（唯一权威）。"""
    from runtime_storage import now_cst
    return now_cst()


def doc_kind_of(edition_kind: str) -> str:
    """规范化文稿类型；未登记 ⇒ 按**内部底稿**处理（对外必须有明确授权，不得默认对外）。"""
    k = str(edition_kind or "")
    return k if k in DOC_KINDS else "internal_working_paper"


def document_meta(edition_kind: str = "internal_working_paper") -> Dict[str, Any]:
    """报告定位：名称 / 用途 / **是否执法文书** / 非执法声明。

    ★ 2026-10-07（Skill 5「报告性质一致性」）：**名称唯一权威** = `config/report_identity.json`
      的 `canonical`（薄转发；本函数不再自持名称字面量）。这样"标题 / 文末声明 / 报告定位"
      三处引用同一来源，不会各写一份而漂移。
    """
    k = doc_kind_of(edition_kind)
    d = dict((load_config().get("documents") or {}).get(k) or {})
    d["edition_kind"] = k
    d.setdefault("name", "税务风险扫描工作底稿")
    d["is_enforceable"] = False
    _cn = canonical_name() if k == "internal_working_paper" else ""
    if _cn:
        d["name"] = _cn               # 仅**内部底稿**的名称走唯一权威；对外文种（风险提示函）用自身配置
    return d


def security_block(edition_kind: str = "internal_working_paper") -> Dict[str, Any]:
    k = doc_kind_of(edition_kind)
    b = dict((load_config().get("security") or {}).get(k) or {})
    b["edition_kind"] = k
    return b


def authorization_block() -> Dict[str, Any]:
    return dict(load_config().get("authorization") or {})


def system_block(reviewed: Optional[bool] = None,
                 generated_at: Optional[str] = None) -> Dict[str, Any]:
    """系统生成标识。`reviewed=None` ⇒ 如实写「尚未人工复核」，**不得默认已复核**。"""
    s = dict(load_config().get("system") or {})
    s["generated_at"] = generated_at or _now()
    s["reviewed"] = bool(reviewed)
    s["review_status_text"] = "已经人工复核" if reviewed else "尚未人工复核（复核后另行出具复核版本）"
    return s


def signature_block(signers: Optional[Dict[str, str]] = None,
                    signed_at: Optional[str] = None) -> Dict[str, Any]:
    """签名栏：编制人/复核人/审批人 + 日期。缺签署人 ⇒ 「待签署」。"""
    signers = {str(k): str(v) for k, v in (signers or {}).items() if str(v).strip()}
    rows: List[Dict[str, Any]] = []
    for s in (load_config().get("signatures") or []):
        role = str(s.get("role") or "")
        rows.append({
            "role": role,
            "name": signers.get(role) or "待签署",
            "required": bool(s.get("required")),
            "note": s.get("note") or "",
            "date": signed_at if signers.get(role) else "",
        })
    missing = [r["role"] for r in rows if r["required"] and r["name"] == "待签署"]
    return {"rows": rows, "signed": not missing, "missing_roles": missing,
            "note": ("签署齐全。" if not missing
                     else "**尚未完成签署**：%s（未签署不得对外交付）。" % "、".join(missing))}


def feedback_block() -> Dict[str, Any]:
    b = dict(load_config().get("feedback") or {})
    return b


def compliance_block(edition_kind: str = "internal_working_paper",
                     signers: Optional[Dict[str, str]] = None,
                     reviewed: Optional[bool] = None,
                     generated_at: Optional[str] = None,
                     extra_note: str = "") -> Dict[str, Any]:
    """**合规模板**：一次性给出全部合规要素（报告头部直接消费）。"""
    return {
        "document": document_meta(edition_kind),
        "security": security_block(edition_kind),
        "authorization": authorization_block(),
        "system": system_block(reviewed, generated_at),
        "signatures": signature_block(signers, generated_at),
        "feedback": feedback_block(),
        "extra_note": str(extra_note or ""),
    }


def compliance_text(block: Dict[str, Any]) -> str:
    """合规要素的自然句汇总（供报告正文/页脚渲染，不用"字段：值"）。"""
    blk = block or {}
    doc = blk.get("document") or {}
    sec = blk.get("security") or {}
    sysb = blk.get("system") or {}
    fb = blk.get("feedback") or {}
    au = blk.get("authorization") or {}
    sg = blk.get("signatures") or {}
    parts = [
        "本文件为《%s》（%s），%s" % (doc.get("name") or "", doc.get("purpose") or "",
                                      doc.get("non_enforcement_note") or ""),
        "保密等级为%s：%s" % (sec.get("level") or "内部资料", sec.get("restriction") or ""),
        (au.get("statement") or ""),
        "本文件由「%s v%s」于 %s 生成，%s。" % (
            sysb.get("name") or "", sysb.get("version") or "",
            sysb.get("generated_at") or "", sysb.get("review_status_text") or ""),
        "企业可在收到后 %s 日内按以下方式提出申辩：%s；%s" % (
            fb.get("window_days") or "—", "、".join(fb.get("channels") or []),
            fb.get("process") or ""),
        sg.get("note") or "",
    ]
    return "".join([p for p in parts if p])


def _doc_no(company_id: Any, edition_kind: str, version: str) -> str:
    h = hashlib.sha1(("%s|%s|%s" % (company_id, edition_kind, version)).encode("utf-8")
                     ).hexdigest()[:6]
    return "RW-%s-%s" % (str(company_id or "0"), h)


def next_version(company_id: Any, edition_kind: str = "internal_working_paper") -> str:
    """下一个版本号（同企业同文稿类型递增）：V1、V2…；**以台账为准**，不猜。"""
    n = 0
    _p = ledger_path()
    if _p.exists():
        for line in _p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("company_id") == str(company_id) and \
                    o.get("edition_kind") == edition_kind:
                n += 1
    return "V%d" % (n + 1)


def record_version(company_id: Any, block: Dict[str, Any],
                   edition_kind: str = "internal_working_paper",
                   change_note: str = "", generated_at: Optional[str] = None,
                   role: str = "internal",
                   analysis_id: str = "") -> Dict[str, Any]:
    """登记一条**版本记录**（append-only 台账），返回该记录。

    `analysis_id`：产出这份报告的**分析作业 id**（`engine.analysis_jobs` 的 `job_id`），
    用于**报告 → 作业**的单向回指（作业行**不**重复记 `doc_no`，避免两个事实来源）。
    取不到作业 id 时（如单元测试、离线渲染）**留空**，**不伪造**。
    """
    ver = next_version(company_id, doc_kind_of(edition_kind))
    rec = {
        "doc_no": _doc_no(company_id, edition_kind, ver),
        "company_id": str(company_id or ""),
        "doc_name": (block.get("document") or {}).get("name") or "税务风险扫描工作底稿",
        "edition_kind": doc_kind_of(edition_kind),
        "version": ver,
        "generated_at": generated_at or _now(),
        "generator": (block.get("system") or {}).get("name") or "",
        "system_version": (block.get("system") or {}).get("version") or "",
        "reviewed": bool((block.get("system") or {}).get("reviewed")),
        "redaction_role": str(role or ""),
        "change_note": str(change_note or "首次生成。"),
        "analysis_id": str(analysis_id or ""),
    }
    _p = ledger_path()
    _p.parent.mkdir(parents=True, exist_ok=True)
    with open(_p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def change_log(company_id: Any = None, limit: int = 20) -> List[Dict[str, Any]]:
    """修改记录（按企业过滤；台账倒序）。"""
    _p = ledger_path()
    if not _p.exists():
        return []
    out: List[Dict[str, Any]] = []
    for line in _p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except Exception:
            continue
        if company_id is not None and o.get("company_id") != str(company_id):
            continue
        out.append(o)
    return out[-int(limit):][::-1]


def internal_edition(report: Dict[str, Any], company_id: Any = None,
                     signers: Optional[Dict[str, str]] = None,
                     reviewed: Optional[bool] = None,
                     generated_at: Optional[str] = None,
                     change_note: str = "",
                     analysis_id: str = "") -> Dict[str, Any]:
    """**内部底稿版**：不脱敏；附合规要素与版本记录。"""
    return _assemble(report, "internal_working_paper", company_id, signers,
                     reviewed, generated_at, change_note, role="internal",
                     analysis_id=analysis_id)


def external_edition(report: Dict[str, Any], company_id: Any = None,
                     signers: Optional[Dict[str, str]] = None,
                     reviewed: Optional[bool] = None,
                     generated_at: Optional[str] = None,
                     change_note: str = "", role: str = "external",
                     analysis_id: str = ""
                     ) -> Dict[str, Any]:
    """**对外版本**：先深拷贝再按角色脱敏（**绝不动内部底稿**），附合规要素与版本记录。"""
    from engine.redaction import copy_for_role
    clone, counter, note = copy_for_role(report, role)
    out = _assemble(clone, "external_notice", company_id, signers,
                    reviewed, generated_at, change_note, role=role,
                    analysis_id=analysis_id)
    out["redaction"] = {"role": role, "counter": counter, "note": note}
    return out


def _assemble(report: Dict[str, Any], edition_kind: str, company_id: Any,
              signers: Optional[Dict[str, str]], reviewed: Optional[bool],
              generated_at: Optional[str], change_note: str, role: str,
              analysis_id: str = "") -> Dict[str, Any]:
    base = dict(report or {})
    blk = compliance_block(edition_kind, signers, reviewed, generated_at)
    base["compliance"] = blk
    base["compliance_text"] = compliance_text(blk)
    base["document_meta"] = blk["document"]
    base["signature_block"] = blk["signatures"]
    rec = record_version(company_id, blk, edition_kind, change_note, generated_at, role,
                         analysis_id=analysis_id)
    base["version_record"] = rec
    base["change_log"] = change_log(company_id, limit=10)
    return base


def validate_compliance() -> List[str]:
    """配置自检（可机检）：文稿类型齐备、非执法声明非空、签名栏三角色、脱敏角色齐备、模板齐备。"""
    probs: List[str] = []
    cfg = load_config()
    docs = cfg.get("documents") or {}
    for k in DOC_KINDS:
        if k not in docs:
            probs.append("配置缺文稿类型 %s" % k)
            continue
        if not str(docs[k].get("non_enforcement_note") or "").strip():
            probs.append("%s 缺『非执法文书』声明" % k)
        if docs[k].get("is_enforceable") is not False:
            probs.append("%s 未声明 is_enforceable=false（不得被当作执法文书）" % k)
    roles = {str(s.get("role")) for s in (cfg.get("signatures") or [])}
    for want in ("编制人", "复核人", "审批人"):
        if want not in roles:
            probs.append("签名栏缺「%s」" % want)
    for k in ("internal", "external"):
        if k not in (cfg.get("redaction_roles") or {}):
            probs.append("脱敏角色表缺 %s" % k)
    if not (cfg.get("templates") or {}):
        probs.append("缺报告模板登记")
    for f in ("statement", "destruction_rule"):
        if not str((cfg.get("authorization") or {}).get(f) or "").strip():
            probs.append("数据授权说明缺 %s" % f)
    fb = cfg.get("feedback") or {}
    for f in ("window_days", "channels", "process"):
        if not fb.get(f):
            probs.append("企业申辩机制缺 %s" % f)
    return probs


__all__ = ["DOC_KINDS", "doc_kind_of", "document_meta", "security_block",
           "authorization_block", "system_block", "signature_block", "feedback_block",
           "compliance_block", "compliance_text", "next_version", "record_version",
           "change_log", "internal_edition", "external_edition", "validate_compliance"]
