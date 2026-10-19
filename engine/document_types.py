# -*- coding: utf-8 -*-
"""资料（P0-2）**类型 / 分类 / 解析状态 / 脱敏**的唯一权威。

★★ 分类为什么不另建一套（关键）
  `static/filename_type_map.json` **已经**是「文件名 → 系统类型码」的单一权威，
  其自带 `_description` / `_methodology` / `_rules_log`，明确写着
  「**编辑此文件即可调整识别规则，无需改代码**」。

  ⇒ 本模块对分类做的是**两段薄转发**，不新增第二套识别逻辑：
     ① 文件名 → 系统类型码（如 `bank_statement`）… 由 `filename_type_map.json` 决定（**读盘**）
     ② 系统类型码 → 业务大类（如 银行流水）… 由 `config/document_categories.json` 决定（**读盘**）
  ⇒ 「新增一个可识别文件类型」＝**加一行数据**（两个 JSON 各一行），**不改代码分支**。

★ 扩展名白名单
  任务要求支持 PDF / Excel / CSV / Word / 图片 / XML / OFD / ZIP。
  既有白名单（`main.ALLOWED_EXTENSIONS`）**12 种**，**缺** `.xml` / `.ofd` / `.zip`。
  本模块是**并集**（既有 12 种 + 新增 3 种 = 15 种），并由 `main.py` 同行内引用，
  保证「存量格式一个不少、新增格式补齐」。
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional, Tuple

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILENAME_TYPE_MAP = os.path.join(_PROJECT_ROOT, "static", "filename_type_map.json")
_CATEGORY_MAP = os.path.join(_PROJECT_ROOT, "config", "document_categories.json")

# --------------------------------------------------------------------------
# ① 扩展名白名单（15 种：既有 12 + 新增 xml/ofd/zip）
# --------------------------------------------------------------------------
#: 既有 12 种（与 `main.ALLOWED_EXTENSIONS` 一致，**不得减**）
LEGACY_EXTENSIONS: Tuple[str, ...] = (
    ".xlsx", ".xls", ".csv", ".pdf", ".txt", ".docx", ".doc",
    ".jpg", ".jpeg", ".png", ".bmp", ".tiff",
)
#: 本轮新增（任务要求：XML / OFD / ZIP）
NEW_EXTENSIONS: Tuple[str, ...] = (".xml", ".ofd", ".zip")

ALLOWED_EXTENSIONS: frozenset = frozenset(LEGACY_EXTENSIONS) | frozenset(NEW_EXTENSIONS)

#: 上限（与既有 `main.MAX_UPLOAD_SIZE` 同值；本模块不改该口径）
MAX_UPLOAD_SIZE = 10 * 1024 * 1024

#: 断点续传路径的上限（★ 分片上传存在的意义就是支持大文件；单请求上限仍为 10MB）。
#: 该上限**只在分片路径生效**，且必须显式声明（**不静默放宽单请求上限**）。
RESUMABLE_MAX_SIZE = 200 * 1024 * 1024
#: 分片大小（5MB）
CHUNK_SIZE = 5 * 1024 * 1024

#: 扩展名 → 面向界面的中文名（枚举码不得入文）
EXT_CN: Dict[str, str] = {
    ".pdf": "PDF", ".xlsx": "Excel", ".xls": "Excel(旧)", ".csv": "CSV",
    ".docx": "Word", ".doc": "Word(旧)", ".txt": "文本",
    ".jpg": "图片(JPEG)", ".jpeg": "图片(JPEG)", ".png": "图片(PNG)",
    ".bmp": "图片(BMP)", ".tiff": "图片(TIFF)",
    ".xml": "XML", ".ofd": "OFD", ".zip": "压缩包",
}

#: 魔数签名（扩展名**永不单独可信**）。缺失 ⇒ 不做内容级校验（如 csv/txt/xml/zip 结构多样）。
#: ★ 与 `main._validate_upload_content` 的既有表**逐项一致**，并补 xml/ofd/zip。
SIGNATURES: Dict[str, Tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".xlsx": (b"PK\x03\x04",),
    ".docx": (b"PK\x03\x04",),
    ".xls": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".doc": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".bmp": (b"BM",),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    # 新增：OFD 是 ZIP 容器；ZIP 即 PK；XML 可有 BOM/声明/空白前缀
    ".ofd": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xml": (b"<?xml", b"\xef\xbb\xbf<?xml", b"\xff\xfe<\x00", b"<\x00?\x00"),
}

# --------------------------------------------------------------------------
# ② 解析状态（5 态，唯一权威）
# --------------------------------------------------------------------------
PARSE_STATUSES: Tuple[str, ...] = ("pending", "parsing", "success", "failed", "manual")

PARSE_STATUS_CN: Dict[str, str] = {
    "pending": "待解析",
    "parsing": "解析中",
    "success": "成功",
    "failed": "失败",
    "manual": "需人工校正",
}

#: 状态迁移（唯一权威）。`success` 可回 `pending`（重解析）；`failed` 可回 `pending`（重试）。
PARSE_STATUS_FLOW: Dict[str, Tuple[str, ...]] = {
    "pending": ("parsing", "manual", "failed"),
    "parsing": ("success", "failed", "manual"),
    "success": ("pending", "manual"),
    # ★ 2026-10-18（GAP-10）：`failed → success` 必须允许。
    #   原表只允许 failed→pending/manual：用户补好文件或修好解析器后**重新解析成功**时，
    #   状态机拒绝置 success 并抛 400，而该异常又把真正的失败原因覆盖成
    #   「解析状态非法迁移：失败 → 成功（允许：待解析、需人工校正）」——
    #   用户在界面上看到的是状态机术语，**看不到文件到底哪里坏了**（实测 5 份全中）。
    "failed": ("pending", "manual", "success"),
    "manual": ("pending", "success", "failed"),
}

# --------------------------------------------------------------------------
# ③ 业务大类（6 大类 + 薪酬/档案/其他）。**值本身由 config 文件声明**，此处只做兜底常量。
# --------------------------------------------------------------------------
# ★ 2026-10-19（统一分类代码）：`OTHER_CATEGORY` 是**存储代码**（`other`），
#   中文名固定走 `CATEGORY_CN`（`other → 其他`）。旧实现把中文名「其他」当代码
#   写进 `documents.category` ⇒ 同一个概念落库两种拼法（实测 `other` 102 行 +
#   `其他` 14 行），分类统计/过滤各认一半。⇒ 代码唯一 `other`；写入口
#   `validate_category` 把「其他」归一为 `other`（存量迁移见回填脚本）。
OTHER_CATEGORY = "other"
#: 旧数据里出现过的中文字面值（读侧兼容、写侧归一）
_OTHER_LEGACY = "其他"

#: 大类中文名（与 `config/document_categories.json` 的 `categories` 段对应）
CATEGORY_CN: Dict[str, str] = {
    "financial_statement": "财务报表",
    "ledger": "账簿",
    "invoice": "发票",
    "declaration": "申报表",
    "bank_statement": "银行流水",
    "contract": "合同",
    "payroll": "薪酬",
    "archive": "档案",
    "other": "其他",
}

#: 系统类型码 → 业务大类（兜底内置；**权威**在 `config/document_categories.json::type_to_category`）
_DEFAULT_TYPE_TO_CATEGORY: Dict[str, str] = {
    # 财务报表
    "financial_statement": "financial_statement",
    "balance_sheet": "financial_statement",
    "income_statement": "financial_statement",
    "cash_flow_statement": "financial_statement",
    # 账簿（凭证 / 序时 / 科目余额 / 总账 / 明细 / 进销存）
    "voucher": "ledger",
    "ledger": "ledger",
    "inventory": "ledger",
    # 发票（销售 / 采购 / 抵扣 / 通用）
    "sales_invoice": "invoice",
    "purchase_invoice": "invoice",
    "input_vat_deduction": "invoice",
    "invoice": "invoice",
    # 申报表
    "vat_declaration": "declaration",
    "cit_declaration": "declaration",
    "salary_tax": "declaration",
    "social_security": "declaration",
    "housing_fund": "declaration",
    "declaration": "declaration",
    # 银行流水
    "bank_statement": "bank_statement",
    # 合同
    "contract": "contract",
    # 薪酬
    "salary": "payroll",
    # 档案
    "archive": "archive",
}

#: 解析状态、分类修正来源（枚举码不得入文）
CLASSIFY_SOURCES: Tuple[str, ...] = ("auto", "manual")
CLASSIFY_SOURCE_CN: Dict[str, str] = {"auto": "自动识别", "manual": "人工修正"}


# --------------------------------------------------------------------------
# 读盘（带缓存；文件改动后 `reset_cache()`）
# --------------------------------------------------------------------------
_CACHE: Dict[str, object] = {}


def reset_cache() -> None:
    _CACHE.clear()


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                 # noqa: BLE001
        return default


def filename_rules() -> List[Tuple[List[str], str]]:
    """(关键词列表, 系统类型码) 的有序规则；**顺序即优先级**（第一个匹配生效）。"""
    if "rules" not in _CACHE:
        cfg = _load_json(_FILENAME_TYPE_MAP, {}) or {}
        rules: List[Tuple[List[str], str]] = []
        for m in (cfg.get("mappings") or []):
            kws = [str(k) for k in (m.get("keywords") or []) if k]
            typ = str(m.get("type") or "")
            if kws and typ:
                rules.append((kws, typ))
        _CACHE["rules"] = rules
    return _CACHE["rules"]                              # type: ignore[return-value]


def type_to_category() -> Dict[str, str]:
    if "t2c" not in _CACHE:
        cfg = _load_json(_CATEGORY_MAP, {}) or {}
        m = dict(_DEFAULT_TYPE_TO_CATEGORY)
        m.update({str(k): str(v) for k, v in (cfg.get("type_to_category") or {}).items()})
        _CACHE["t2c"] = m
    return _CACHE["t2c"]                                # type: ignore[return-value]


def category_cn(code: str) -> str:
    cfg = _load_json(_CATEGORY_MAP, {}) or {}
    cn = dict(CATEGORY_CN)
    cn.update({str(k): str(v) for k, v in (cfg.get("categories") or {}).items()})
    # 兜底给**中文显示名**（不是代码）：未知代码如实显示「其他」
    return cn.get(str(code), cn.get(OTHER_CATEGORY, "其他"))


def categories() -> List[Dict[str, str]]:
    """业务大类清单（供前端下拉；**唯一权威**在 config）。"""
    cfg = _load_json(_CATEGORY_MAP, {}) or {}
    names = dict(CATEGORY_CN)
    names.update({str(k): str(v) for k, v in (cfg.get("categories") or {}).items()})
    return [{"value": k, "label": v} for k, v in names.items()]


# --------------------------------------------------------------------------
# 识别
# --------------------------------------------------------------------------
def ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def is_allowed(filename: str) -> bool:
    return ext_of(filename) in ALLOWED_EXTENSIONS


def guess_type(filename: str) -> str:
    """文件名 → 系统类型码（按 `filename_type_map.json` 顺序，首个命中生效）。

    全部未命中 ⇒ `""`（**如实返回空**，由调用方落到"其他"，**不得猜测**）。
    """
    name = str(filename or "")
    for kws, typ in filename_rules():
        if any(k in name for k in kws):
            return typ
    return ""


def guess_category(filename: str) -> Tuple[str, str]:
    """文件名 → (业务大类码, 系统类型码)。未识别 ⇒ (`other`, `""`)。"""
    typ = guess_type(filename)
    if not typ:
        return OTHER_CATEGORY, ""
    return type_to_category().get(typ, OTHER_CATEGORY), typ


def validate_content(filename: str, content: bytes, *, max_size: int = MAX_UPLOAD_SIZE) -> None:
    """内容级校验（扩展名**永不单独可信**）。

    抛 `ValueError`（消息面向用户，中文）。
    """
    ext = ext_of(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("不支持的文件类型：%s（仅接受 %s）"
                         % (ext or "(无扩展名)", "/".join(sorted(ALLOWED_EXTENSIONS))))
    if len(content) > max_size:
        raise ValueError("文件过大（%.2fMB），上限 %dMB"
                         % (len(content) / 1024 / 1024, max_size // 1024 // 1024))
    expected = SIGNATURES.get(ext)
    if expected and not any(content.startswith(item) for item in expected):
        raise ValueError("文件内容与扩展名不匹配（%s）" % (EXT_CN.get(ext, ext)))
    if ext in {".txt", ".csv"} and b"\x00" in content[:4096]:
        raise ValueError("文本文件包含非法二进制内容")


def validate_parse_status(status: str) -> str:
    s = str(status or "").strip()
    if s not in PARSE_STATUSES:
        raise ValueError("解析状态非法：%s（合法值：%s）"
                         % (s or "(空)", "、".join(PARSE_STATUS_CN.values())))
    return s


def can_parse_transition(old: str, new: str) -> bool:
    if old == new:
        return True
    return new in PARSE_STATUS_FLOW.get(str(old), ())


def validate_category(code: str) -> str:
    allowed = {c["value"] for c in categories()}
    c = str(code or "").strip()
    if c == _OTHER_LEGACY:
        c = OTHER_CATEGORY                             # ★ 中文别名归一为代码（防二义落库）
    if c not in (allowed | {OTHER_CATEGORY}):
        raise ValueError("分类非法：%s" % (c or "(空)"))
    return c


# --------------------------------------------------------------------------
# ④ 敏感字段脱敏（★ 只作用于**展示**，不改存储、不改原件、不改可追溯信息）
# --------------------------------------------------------------------------
#: 脱敏规则：仅覆盖**个人敏感标识**。企业名称 / 纳税人识别号 / 金额 **不脱敏**
#: （与项目既有铁律一致：主体与金额必须可复核）。
_MASKS: Tuple[Tuple[re.Pattern, str], ...] = (
    # 身份证（18 位 / 15 位）
    (re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3})([\dXx])(?!\d)"), r"\1********\3\4"),
    # 手机号
    (re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)"), r"\1****\3"),
    # 银行卡（16~19 位连续数字）
    (re.compile(r"(?<!\d)(\d{4})(\d{8,11})(\d{4})(?!\d)"), r"\1********\3"),
    # 邮箱
    (re.compile(r"([A-Za-z0-9._%+-]{1,2})[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+)"), r"\1***\2"),
)


def mask_sensitive(text: str) -> str:
    """对**展示用**字符串做个人敏感信息掩码（幂等；非字符串原样返回）。"""
    s = str(text if text is not None else "")
    for pat, rep in _MASKS:
        s = pat.sub(rep, s)
    return s


def has_sensitive(text: str) -> bool:
    """是否含个人敏感标识（供测试/闸门断言脱敏确实生效）。"""
    s = str(text or "")
    return any(p.search(s) for p, _ in _MASKS)
