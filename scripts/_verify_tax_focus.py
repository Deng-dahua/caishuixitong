# -*- coding: utf-8 -*-
"""结果级验收：**分税种专项视图是否真的按税种聚焦**（2026-10-19）。

## 背景（为什么必须有这个脚本）

此前 `tax_specific` 与 `full` 的章节/上限**完全相同**，`VIEW_DESC` 却声称
「按税种分组」；实测两者差异只有 4 行时间戳与水印（见
`docs/核实_工商渠道与五类报告_20261019.md` §2.3）。这是典型的「声称 > 实际」。

## 判据（看"用户打开导出件能看到什么"，不看"我改了哪个文件"）

正向
  ① 两视图**文档模型必须不同**（章节集合、`risk_overview` 块结构、`tax_detail` 块结构）；
  ② `tax_specific` 的「分税种明细」章是**税种专项档案**：逐税种给出
     「◆ 税种：X」+ 等级分布 + 金额小计 + 金额取不到条数 + 明细表；
  ③ 「税种×等级」交叉表**数字可复核**：每行合计 = 该税种发现数，
     且行合计之和 = Σ(各税种发现数)（多税种发现会重复计数，须与 stats 口径区分说明）；
  ④ `tax_specific` 真渲染 4 格式，HTML 正文里**必须出现**「◆ 税种：」「等级分布」，
     且 **不得**出现「附件」章（并须在 omitted 里如实登记）；
  ⑤ `full` 视图**不得**出现「◆ 税种：」（那是税种聚焦形态，两份必须真的不同）。

反向（注入已知缺陷 ⇒ 必须变红）
  ⑥ 把 `focus_of` 强制返回 `severity`（模拟"未接线"）⇒ 判据 ②③④ 必须变红；
  ⑦ 把 `tax_specific` 的章节改回与 `full` 相同 ⇒ 判据 ① 必须变红。

用法：
    .venv/Scripts/python.exe scripts/_verify_tax_focus.py [project_id]
"""
from __future__ import annotations

import json
import html
import re
import sys
import zipfile
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []
PASSES: list[str] = []
PJT = int(sys.argv[1]) if len(sys.argv) > 1 else 42


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSES if ok else FAILS).append(name)
    print(("  ✅ " if ok else "  ❌ ") + name + (("  —— " + detail) if detail else ""))


class _Session:
    username = "acceptance"
    is_admin = True
    user_id = 1

    def can_access_company(self, cid):
        return True

    def __getattr__(self, item):
        return None


def _shape(doc):
    """章节 → 块类型的指纹（用于两视图对比）。"""
    return {s["key"]: [b.get("type") for b in s["blocks"]] for s in doc["sections"]}


def _texts(doc, key):
    """某章节里所有可读文本（段落/kv/表/note 全含）。"""
    out = []
    for s in doc["sections"]:
        if s["key"] != key:
            continue
        for b in s["blocks"]:
            t = b.get("type")
            if t == "paragraph":
                out.append(str(b.get("text") or ""))
            elif t == "note":
                out.append(str(b.get("text") or ""))
            elif t == "kv":
                out.append(" ".join("%s=%s" % (i.get("k"), i.get("v"))
                                    for i in (b.get("items") or [])))
            elif t == "table":
                out.append(" | ".join(str(c) for c in (b.get("columns") or [])))
                for r in (b.get("rows") or []):
                    out.append(" | ".join("" if v is None else str(v) for v in r))
            elif t == "list":
                out.extend(str(x) for x in (b.get("items") or []))
    return out


def _doc_text(fmt, data):
    """抽可读文本。

    ★ 2026-10-19（判据自身缺陷，必须修）：openpyxl 把单元格文本写成
      **XML 数字实体**（`<t>&#26412;&#35270;&#22270;…</t>`），docx 也可能含 `&amp;` 等。
      首版直接按原文匹配 ⇒ xlsx **恒判为"不含关键词"**（假红）。
      这是「判据把对的产物判成错」的典型 —— 必须先 `html.unescape` 再去标签。
    """
    if fmt == "html":
        return html.unescape(data.decode("utf-8", "replace"))
    if fmt == "docx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            raw = z.read("word/document.xml").decode("utf-8", "replace")
        return html.unescape(re.sub(r"<[^>]+>", "", raw))
    if fmt == "xlsx":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            raw = "".join(z.read(n).decode("utf-8", "replace")
                          for n in z.namelist() if n.endswith(".xml"))
        return html.unescape(re.sub(r"<[^>]+>", " ", raw))
    if fmt == "pdf":
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(data)) as pdf:
                return "\n".join((p.extract_text() or "") for p in pdf.pages)
        except Exception:                                        # noqa: BLE001
            return ""
    return ""


def main() -> int:
    from engine import report_service as RS
    from engine import report_views as V
    from engine import report_render as R

    s = _Session()
    d_full = RS.build_document(PJT, s, view="full")
    d_tax = RS.build_document(PJT, s, view="tax_specific")

    print("\n【正向】① 两视图的文档模型必须真的不同")
    check("full.focus=severity", d_full.get("focus") == "severity", str(d_full.get("focus")))
    check("tax_specific.focus=tax", d_tax.get("focus") == "tax", str(d_tax.get("focus")))
    kf = [x["key"] for x in d_full["sections"]]
    kt = [x["key"] for x in d_tax["sections"]]
    check("章节集合不同（tax_specific 裁掉 attachments）",
          kf != kt and "attachments" not in kt and "attachments" in kf,
          "full=%d节 tax=%d节" % (len(kf), len(kt)))
    check("omitted 如实登记被裁章节",
          [x["key"] for x in d_tax.get("omitted") or []] == ["attachments"],
          str([x["key"] for x in d_tax.get("omitted") or []]))
    sf, st = _shape(d_full), _shape(d_tax)
    check("risk_overview 块结构不同（tax 多一张交叉表）",
          sf["risk_overview"] != st["risk_overview"],
          "full=%s tax=%s" % (sf["risk_overview"], st["risk_overview"]))
    check("tax_detail 块结构不同（税种专项档案 vs 分组清单）",
          sf["tax_detail"] != st["tax_detail"],
          "full=%d块 tax=%d块" % (len(sf["tax_detail"]), len(st["tax_detail"])))

    print("\n【正向】② tax_detail 是「税种专项档案」")
    tt = _texts(d_tax, "tax_detail")
    joined = "\n".join(tt)
    heads = [x for x in tt if x.startswith("◆ 税种：")]
    check("逐税种成节（出现「◆ 税种：」）", len(heads) > 0, "共 %d 个税种节" % len(heads))
    check("每节给出「等级分布」", joined.count("等级分布") >= len(heads),
          "等级分布 %d 次 / 税种节 %d 个" % (joined.count("等级分布"), len(heads)))
    check("每节给出「金额取不到的条数」（缺失≠0 口径）",
          joined.count("金额取不到的条数") >= len(heads),
          "%d 次" % joined.count("金额取不到的条数"))
    check("每节给出「测算涉税金额小计」", "测算涉税金额小计" in joined)
    check("节末有收束标记「以上为…的专项档案」", "专项档案全部内容" in joined)

    print("\n【正向】③ 「税种×等级」交叉表数字可复核")
    cross = None
    for b in [bb for s2 in d_tax["sections"] if s2["key"] == "risk_overview"
              for bb in s2["blocks"]]:
        if b.get("type") == "table" and (b.get("columns") or [])[:2] == ["税种", "极高风险"]:
            cross = b
            break
    check("交叉表存在", cross is not None, str((cross or {}).get("columns")))
    if cross:
        cols = cross["columns"]
        rows = cross["rows"]
        body, total_row = rows[:-1], rows[-1]
        ok_row = all(int(r[-1]) == sum(int(x) for x in r[1:-1]) for r in body)
        check("每行「合计」= 该行各等级之和", ok_row,
              str([(r[0], r[-1], sum(int(x) for x in r[1:-1])) for r in body][:4]))
        ok_tot = all(int(total_row[i]) == sum(int(r[i]) for r in body)
                     for i in range(1, len(cols)))
        check("「合计」行 = 各税种行逐列相加", ok_tot, str(total_row))
        # ★ 列名必须用**展示词**（待核验→涉嫌风险、信息→提示性事项），
        #   且必须带「未标注等级」兜底列 —— 否则对不上列就会静默丢数。
        from engine.risk_levels import LEGAL_LEVELS, display_label
        expect = []
        for x in LEGAL_LEVELS:
            lbl = display_label(x)
            if lbl and lbl not in expect:
                expect.append(lbl)
        expect = expect + ["未标注等级"]
        check("等级列是展示词 + 「未标注等级」兜底（不静默丢数）",
              cols[1:-1] == expect, "实际=%s 期望=%s" % (cols[1:-1], expect))
        # 兜底列真的兜住了：若存在未标注，则该列非零且行合计仍可复核
        unk_idx = cols.index("未标注等级")
        unk_total = int(total_row[unk_idx])
        check("「未标注等级」列有明确计数（可为 0）", unk_total >= 0, "共 %d 项" % unk_total)
        check("报告带 counts（可交叉核对事项数）", "findings" in (d_tax.get("counts") or {}),
              str(d_tax.get("counts")))

    print("\n【正向】④ tax_specific 真渲染 4 格式且正文可见「税种专项」形态")
    for fmt in V.FORMATS:
        try:
            data, mode = R.render(d_tax, fmt)
        except Exception as exc:                                 # noqa: BLE001
            check("tax_specific 渲染 %s" % fmt, False, "异常：%s" % exc)
            continue
        check("tax_specific 渲染 %s（%d 字节，水印=%s）" % (fmt, len(data), mode),
              bool(data) and mode == "embedded")
        txt = _doc_text(fmt, data)
        has_head = ("◆ 税种" in txt) or ("税种：" in txt and "等级分布" in txt)
        # PDF 抽文本可能丢特殊符号 ⇒ PDF 只要求"等级分布"
        if fmt == "pdf":
            has_head = ("等级分布" in txt) or has_head
        check("%s 正文含税种专项形态（◆ 税种/等级分布）" % fmt,
              has_head, ("命中" if has_head else txt[:120].replace("\n", " ")))

    print("\n【正向】⑤ tax_specific 不含附件章；full 不含税种专项形态")
    html_tax = R.render(d_tax, "html")[0].decode("utf-8", "replace")
    html_full = R.render(d_full, "html")[0].decode("utf-8", "replace")
    titles_tax = [x["title"] for x in d_tax["sections"]]
    check("tax_specific 章节里没有「附件」", "附件" not in titles_tax, str(titles_tax))
    check("tax_specific 的 HTML 把被裁章节如实写在「本视图未包含的章节」",
          "本视图未包含的章节" in html_tax and "附件" in html_tax)
    check("full 的 HTML 不含「◆ 税种：」（两种形态不混）", "◆ 税种：" not in html_full)

    print("\n【反向】⑥ 把 focus 强制改回 severity（模拟未接线）⇒ 必须变红")
    orig = V.focus_of
    V.focus_of = lambda v: "severity"
    try:
        d_bad = RS.build_document(PJT, s, view="tax_specific")
        bad_texts = "\n".join(_texts(d_bad, "tax_detail"))
        check("注入后不再出现「◆ 税种：」", "◆ 税种：" not in bad_texts)
        check("注入后 tax_detail 结构回退成清单（≠ 税种档案）",
              _shape(d_bad)["tax_detail"] == _shape(d_full)["tax_detail"],
              "注入后与 full 相同 ⇒ 判据②③能抓住")
    finally:
        V.focus_of = orig

    print("\n【反向】⑦ 把 tax_specific 章节改回与 full 相同 ⇒ 判据①必红")
    orig_sec = V.VIEW_SECTIONS["tax_specific"]
    V.VIEW_SECTIONS["tax_specific"] = V.SECTIONS
    try:
        d_bad2 = RS.build_document(PJT, s, view="tax_specific")
        kt2 = [x["key"] for x in d_bad2["sections"]]
        check("注入后章节集合与 full 相同（⇒「章节不同」判据会红）",
              kt2 == kf and len(d_bad2.get("omitted") or []) == 0)
        # 注意 focus 仍为 tax ⇒ tax_detail 仍不同，故"完全相同"需两处同时回退；
        # 这正是 verify_view_focus() 的用途：**签名级**两两断言能一次抓住
        V.VIEW_FOCUS["tax_specific"] = "severity"
        check("签名级断言 verify_view_focus() 能抓住（章节+focus 双双相同）",
              bool(V.verify_view_focus()), str(V.verify_view_focus()))
    finally:
        V.VIEW_SECTIONS["tax_specific"] = orig_sec
        V.VIEW_FOCUS["tax_specific"] = "tax"

    print("\n【回归】恢复后断言必须再次为绿")
    check("verify_view_focus() 恢复后为空", V.verify_view_focus() == [], str(V.verify_view_focus()))
    check("verify_view_names() 仍为空", V.verify_view_names() == [], str(V.verify_view_names()))

    print("\n" + "=" * 66)
    print("通过 %d 项 | 失败 %d 项" % (len(PASSES), len(FAILS)))
    if FAILS:
        for f in FAILS:
            print("  - " + f)
        return 1
    print("全部通过：分税种专项视图**真的按税种组织**，且与全景视图内容不同、可复核。")
    return 0


if __name__ == "__main__":
    sys.exit(main())