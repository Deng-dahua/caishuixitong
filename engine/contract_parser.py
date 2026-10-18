# -*- coding: utf-8 -*-
"""合同文本 → 结构化合同要素（GAP-07）。

为什么需要
--------
测评实证：上传 `建设工程施工合同.docx` 后解析结果 `row_count=0 / fields=[]`，
`read_failures` 明列该文件"未读取到任何数据"。而 `_parse_docx` 其实读到了 6 段文本，
只是**段落文本没有被结构化**，于是：
  · `contract_data` 拿不到合同金额 ⇒ 印花税只能拿发票反推、`contract vs 开票` 只能是"缺数据"；
  · 证据链因为文件名含"合同"被判"已有"（另一处缺陷，见 `_doc_covered_categories`）。

判据（纯正则、可复核、不猜）
------------------------
从合同正文里抓手写要素，**抓不到就留空**（缺失≠0）：
  · 合同名称：首段非空段落 / 含"合同""协议"的标题行
  · 合同金额：`人民币…元`、`￥/¥ 数字`、`金额为 数字元`、`合同价款…数字`
  · 甲方 / 乙方：`甲方（…）：XXX` / `乙方：XXX`（兼容"发包方/承包方""买方/卖方""委托方/受托方"）
  · 签订日期：`签订日期/签署日期：YYYY年M月D日` 或 `YYYY-MM-DD`
  · 合同编号：`合同编号：XXX` / `编号：XXX`

★ 金额解析统一走 `engine.numparse.to_number`（唯一权威），并处理"伍佰万元整"这类中文大写
  与"（￥5,000,000.00）"并存的情形 —— 优先取阿拉伯数字，取不到才尝试中文数字。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from engine.numparse import to_number

# ── 金额 ──────────────────────────────────────────────────────────────
_RE_MONEY_CN = re.compile(r"人民币\s*([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(?:元|圆)")
_RE_MONEY_SYM = re.compile(r"[￥¥]\s*([0-9][0-9,，]*(?:\.[0-9]+)?)")
_RE_MONEY_KW = re.compile(
    r"(?:合同(?:总)?(?:价款|金额|价)|总金额|金额|价款|总价)\s*(?:为|是|:|：)?\s*"
    r"([0-9][0-9,，]*(?:\.[0-9]+)?)\s*(?:元|圆)")
#: 中文大写金额（伍佰万元整 / 壹佰贰拾叁万肆仟伍佰陆拾柒元）
_RE_MONEY_CAP = re.compile(r"([零壹贰叁肆伍陆柒捌玖拾佰仟万亿元圆整角分]{4,})")

# ── 主体 ──────────────────────────────────────────────────────────────
_RE_PARTY_A = re.compile(
    r"(?:甲方|发包方|买方|采购方|委托方|出租方|转让方|出卖方)"
    r"(?:（[^）]*）|\([^)]*\))?\s*[:：]\s*([^\n，,；;]{2,40})")
_RE_PARTY_B = re.compile(
    r"(?:乙方|承包方|卖方|供应方|受托方|承租方|受让方|买受方)"
    r"(?:（[^）]*）|\([^)]*\))?\s*[:：]\s*([^\n，,；;]{2,40})")

# ── 日期 / 编号 / 名称 ────────────────────────────────────────────────
_RE_DATE = re.compile(
    r"(?:签订|签署|订立)(?:日期|时间)?\s*[:：]?\s*"
    r"(\d{4})\s*[年\-/.]\s*(\d{1,2})\s*[月\-/.]\s*(\d{1,2})")
_RE_NO = re.compile(r"(?:合同)?编号\s*[:：]\s*([A-Za-z0-9\-_/（）()]{2,40})")
_RE_TITLE = re.compile(r"^[^\n]{2,40}(?:合同|协议|订单|契约)$")


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", str(s or "")).strip("：:，,。；;")


def _pick_money(text: str) -> float:
    """按优先级取金额：人民币X元 > ￥X > 带关键词的 X元。取不到返回 0.0。"""
    for pat in (_RE_MONEY_CN, _RE_MONEY_SYM, _RE_MONEY_KW):
        m = pat.search(text)
        if m:
            v = to_number(m.group(1))
            if v:
                return float(v)
    # 中文大写（仅当无阿拉伯数字时；避免"伍佰万元"与"5,000,000.00"重复计数）
    m = _RE_MONEY_CAP.search(text)
    if m:
        v = _cap_to_number(m.group(1))
        if v:
            return float(v)
    return 0.0


_CAP_DIGIT = {"零": 0, "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5,
              "陆": 6, "柒": 7, "捌": 8, "玖": 9}
_CAP_UNIT = {"拾": 10, "佰": 100, "仟": 1000}


def _cap_to_number(s: str) -> float:
    """中文大写金额 → 数值（支持"伍佰万元整"「壹仟贰佰叁拾肆元」）。取不到返回 0。"""
    s = str(s or "")
    if not s:
        return 0.0
    total, section, num = 0.0, 0.0, 0
    for ch in s:
        if ch in _CAP_DIGIT:
            num = _CAP_DIGIT[ch]
        elif ch in _CAP_UNIT:
            section += (num or 1) * _CAP_UNIT[ch]
            num = 0
        elif ch in ("万", "萬"):
            section = (section + num) * 10000
            total += section
            section, num = 0, 0
        elif ch in ("亿",):
            total = (total + section + num) * 100000000
            section, num = 0, 0
        elif ch in ("元", "圆", "整", "角", "分"):
            continue
        else:
            continue
    return total + section + num


def parse_contract_text(paragraphs: List[str], filename: str = "") -> Dict[str, Any]:
    """把合同段落文本解析成一行结构化合同（字段名与 `_parse_contract_sheet` 对齐）。

    返回 `{type:"contract", rows:[{...}], source, _parse_note}`；
    **一个要素都没抓到时返回 `rows:[]`**（由调用方如实报"未识别到合同要素"）。
    """
    paras = [str(p).strip() for p in (paragraphs or []) if str(p).strip()]
    if not paras:
        return {"type": "contract", "rows": [], "source": filename,
                "_parse_note": "合同文本为空"}
    text = "\n".join(paras)

    title = ""
    for p in paras[:5]:
        t = _clean(p)
        if t and _RE_TITLE.match(t):
            title = t
            break
    if not title:
        for p in paras[:5]:
            if "合同" in p or "协议" in p:
                title = _clean(p)[:40]
                break
    if not title:
        title = _clean(paras[0])[:40]

    m = _RE_PARTY_A.search(text)
    party_a = _clean(m.group(1)) if m else ""
    m = _RE_PARTY_B.search(text)
    party_b = _clean(m.group(1)) if m else ""

    amount = _pick_money(text)

    sign_date = ""
    m = _RE_DATE.search(text)
    if m:
        sign_date = "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))

    contract_no = ""
    m = _RE_NO.search(text)
    if m:
        contract_no = _clean(m.group(1))

    row = {"name": title, "contract_no": contract_no, "party_a": party_a,
           "party_b": party_b, "amount": amount, "sign_date": sign_date,
           "contract_type": "", "content": "", "remark": "",
           "_source": filename, "_from": "docx_text"}
    got = [k for k in ("name", "party_a", "party_b", "amount", "sign_date", "contract_no")
           if row.get(k)]
    if not got:
        return {"type": "contract", "rows": [], "source": filename,
                "_parse_note": "合同文本已读取 %d 段，但未识别到任何合同要素" % len(paras)}
    note = "从合同正文提取要素：%s" % "、".join(
        {"name": "合同名称", "party_a": "甲方", "party_b": "乙方",
         "amount": "合同金额", "sign_date": "签订日期", "contract_no": "合同编号"}[k] for k in got)
    return {"type": "contract", "rows": [row], "source": filename, "_parse_note": note}
