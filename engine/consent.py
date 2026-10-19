# -*- coding: utf-8 -*-
"""知情同意与免责声明（E-01 / E-04，2026-10-17）。

评估结论
--------
阶段 12 伦理合规：「**无知情同意** —— 账号开通即用，未告知数据处理范围」，
这也是阶段 7 安全合规里「合规」只判"部分符合"的直接原因。
免责声明此前只写在报告正文里，登录页与首页都没有。

做法
----
① **条款集中在本文件**（唯一权威，不在前端硬编码）：数据范围、目的、留存、用户权利、免责。
② 接受记录落在 `security.db` 的 `user_consents` 表（用户 + 版本 + 时间 + IP + UA），
   **可审计**；条款改版（`CONSENT_VERSION` 变更）⇒ 所有人需重新确认。
③ `/api/auth/me` 下发 `consent_required`，前端据此跳转；**服务端不阻断业务**
   （只做告知，不做强制同意才可使用 —— 那会影响既有用户，属于产品决策）。

★ 不记录任何"同意"以外的推断；未同意就是未同意，不默认视为同意。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime_storage import now_cst
from security import _connect, get_session   # noqa: PLC0415 - 复用唯一安全库连接口径

#: 条款版本。**改条款必须改这里**（改后所有人需重新确认，历史记录保留）
CONSENT_VERSION = "2026-10-v1"

TITLE = "数据处理告知与免责声明"

#: 条款正文（结构化：标题 + 段落）。前端按此渲染，不在页面里另写一份。
ITEMS: List[Dict[str, str]] = [
    {
        "title": "一、我们处理哪些数据",
        "body": ("本系统处理贵单位为完成财税风险自查而主动上传的资料：财务报表、账簿与凭证、"
                 "申报表、发票明细、工资与社保数据、合同等；以及由此解析出的结构化数据与风险结论。"
                 "系统不会主动从外部抓取贵单位数据，也不会处理与财税风险分析无关的个人信息。"),
    },
    {
        "title": "二、处理目的与法律依据",
        "body": ("处理目的仅限于：①识别财税风险疑点并给出法规依据；②生成分析报告与整改建议；"
                 "③留存审计轨迹以备复核。依据为《个人信息保护法》第十三条第（一）项（取得个人同意）"
                 "与第（二）项（履行合同所必需），以及《数据安全法》关于数据处理者义务的规定。"),
    },
    {
        "title": "三、数据存放与留存",
        "body": ("数据存放在部署本系统的服务器（默认 `data/` 目录），不上传至第三方；"
                 "调用大模型能力时仅发送必要的文本片段（可在系统设置中关闭该能力）。"
                 "数据保留期由部署单位在内部制度中确定；删除资料时文件进入回收站，"
                 "由管理员按流程清理。每日自动备份默认保留 14 份。"),
    },
    {
        "title": "四、您（数据主体）的权利",
        "body": ("您有权查询、更正、删除自己的个人信息，有权撤回同意。"
                 "行使方式：联系本单位系统管理员；涉及员工个人信息的，由单位按内部流程处理。"
                 "撤回同意不影响撤回前已进行的处理。"),
    },
    {
        "title": "五、免责声明",
        "body": ("本系统输出的是风险线索与法规依据，不构成税务鉴证意见、税务筹划建议或法律意见，"
                 "不能直接作为申报、抗辩或对外披露的依据。最终判断与责任由使用人及其所属专业机构承担。"
                 "法规具有时效性，系统内条文版本状态以「法规库」标注为准；"
                 "标为「已失效/被取代」的条文不得作为现行依据引用。"),
    },
    {
        "title": "六、安全措施",
        "body": ("系统采用最小权限（角色-权限点）、操作审计留痕、会话有效期控制、"
                 "上传类型与路径校验等措施；管理动作仅管理员可执行。"
                 "发现疑似数据泄露，请立即联系管理员并按内部应急预案处置。"),
    },
]


def payload() -> Dict[str, Any]:
    """条款全文 + 版本（前端渲染的唯一来源）。"""
    return {
        "version": CONSENT_VERSION,
        "title": TITLE,
        "items": ITEMS,
        "short_notice": ("本系统仅将您上传的资料用于财税风险识别，结论不构成税务鉴证意见。"),
    }


def _ensure_table() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_consents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                version TEXT NOT NULL,
                accepted_at TEXT NOT NULL,
                client_ip TEXT,
                user_agent TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_consent_user "
                     "ON user_consents(username, version)")


def is_accepted(username: str, version: Optional[str] = None) -> bool:
    """该用户是否已确认**当前版本**条款（查不到即未确认，不默认同意）。"""
    name = (username or "").strip()
    if not name:
        return False
    want = version or CONSENT_VERSION
    try:
        _ensure_table()
        with _connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM user_consents WHERE username=? AND version=? LIMIT 1",
                (name, want)).fetchone()
        return bool(row)
    except Exception:                                  # noqa: BLE001
        # 读不到就当作"未确认"（从严），但**不阻断**登录 —— 告知不该变成可用性故障
        return False


def record(username: str, *, client_ip: str = "", user_agent: str = "",
           version: Optional[str] = None) -> Dict[str, Any]:
    """记录一次确认（幂等：同用户同版本重复提交只留一条）。"""
    name = (username or "").strip()
    if not name:
        raise ValueError("username required")
    want = version or CONSENT_VERSION
    _ensure_table()
    with _connect() as conn:
        exists = conn.execute(
            "SELECT accepted_at FROM user_consents WHERE username=? AND version=? "
            "ORDER BY id DESC LIMIT 1", (name, want)).fetchone()
        if exists:
            return {"ok": True, "already": True, "accepted_at": exists["accepted_at"],
                    "version": want}
        conn.execute(
            "INSERT INTO user_consents (username, version, accepted_at, client_ip, user_agent)"
            " VALUES (?,?,?,?,?)",
            (name, want, now_cst(), (client_ip or "")[:64], (user_agent or "")[:255]))
    return {"ok": True, "already": False, "accepted_at": now_cst(), "version": want}


def status(username: str) -> Dict[str, Any]:
    return {"version": CONSENT_VERSION,
            "accepted": is_accepted(username),
            "required": not is_accepted(username)}


__all__ = ["CONSENT_VERSION", "TITLE", "ITEMS", "payload", "is_accepted", "record", "status"]
