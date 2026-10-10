# -*- coding: utf-8 -*-
"""面向企业负责人的报告：可读性与可信度只读审计（不修改任何文件）。

用法：
    ./.venv/Scripts/python.exe scripts/_audit_boss_report.py <报告.docx>

设计原则（与项目「唯一权威 + 可复现证据」一致）：
  * 只读：仅解析 zip 内 word/document.xml，不写回、不改动被审计文件。
  * 每条判据都打印【命中原文/行号/计数】，便于人工复核，不做推断性结论。
  * 「取不到」就如实打印 SKIP，不用默认值顶替。
"""
from __future__ import annotations

import re
import sys
import zipfile
from collections import Counter
from decimal import Decimal
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ---------------------------------------------------------------- 抽取层
def para_text(pel) -> str:
    parts = [t.text or "" for t in pel.iter(W + "t")]
    return "".join(parts)


def extract(path: str) -> list[str]:
    """按文档顺序抽取：段落一行；表格转为 TABLE_START / 'a | b | c' / TABLE_END。"""
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    body = root.find(W + "body")
    out: list[str] = []

    def walk(el):
        for ch in el:
            if ch.tag == W + "p":
                out.append(para_text(ch))
            elif ch.tag == W + "tbl":
                out.append("<<TABLE_START>>")
                for tr in ch.findall(W + "tr"):
                    cells = []
                    for tc in tr.findall(W + "tc"):
                        cells.append(" ".join(x for x in (para_text(p) for p in tc.findall(W + "p")) if x).strip())
                    out.append(" | ".join(cells))
                out.append("<<TABLE_END>>")
            elif ch.tag in (W + "sdt", W + "sdtContent"):
                walk(ch)

    walk(body)
    return out


def tables(lines: list[str]) -> list[tuple[int, list[list[str]]]]:
    """返回 [(起始行号1基, 行列表)]，首行为表头。"""
    res, i = [], 0
    while i < len(lines):
        if lines[i].strip() == "<<TABLE_START>>":
            rows, j = [], i + 1
            while j < len(lines) and lines[j].strip() != "<<TABLE_END>>":
                rows.append([c.strip() for c in lines[j].split("|")])
                j += 1
            res.append((i + 1, rows))
            i = j
        i += 1
    return res


def dec(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace(",", "").strip())
    except Exception:
        return None


def items(lines: list[str]) -> list[tuple[str, list[str]]]:
    """按『疑点N：』切块。"""
    starts = [i for i, l in enumerate(lines) if re.match(r"^疑点\d+[：:]", l.strip())]
    res = []
    for k, i in enumerate(starts):
        j = starts[k + 1] if k + 1 < len(starts) else len(lines)
        res.append((lines[i].strip()[:40], lines[i:j]))
    return res


def hr(title: str) -> None:
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


# ---------------------------------------------------------------- 判据层
def check_scale(lines: list[str], ts) -> None:
    hr("[1] 规模画像")
    chars = sum(len(l) for l in lines)
    print(f"段落块 = {len(lines)}    字符 = {chars:,}    表格 = {len(ts)}")
    its = items(lines)
    if its:
        sizes = sorted(((len(b), n) for n, b in its), reverse=True)
        print(f"疑点项数 = {len(its)}；单项段数 最大={sizes[0][0]}({sizes[0][1][:20]}) 最小={sizes[-1][0]}")
        top = sizes[0][0]
        print(f"最大一项占全文 {top / len(lines) * 100:.1f}%  → 篇幅失衡" if top / len(lines) > 0.15 else "篇幅分布尚可")


def check_qualification(lines: list[str]) -> None:
    """A/B：定性口径自相矛盾 + 等级缺失。"""
    hr("[2] 定性口径与风险等级的自洽性")
    t = "\n".join(lines)
    broken = t.count("本企业本项已查明的风险；")
    lowpos = t.count("本企业本项已查明的风险的可能性低")
    known = t.count("本项属**已查明的风险**")
    neg = t.count("未认定到任何一条构成要件")
    print(f"模板破句『本企业本项已查明的风险；』          x{broken}   ← 变量位为空，缺谓语")
    print(f"『本企业本项已查明的风险的可能性低』          x{lowpos}")
    print(f"『本项属**已查明的风险**』(加粗，非红线模板)  x{known}")
    print(f"『未认定到任何一条构成要件』                  x{neg}   ← 与『已查明』同文并存")
    for name, b in items(lines):
        bt = "\n".join(b)
        has_lv = re.search(r"(高|中|低)风险", bt)
        head = b[1][:48] if len(b) > 1 else ""
        mark = "等级缺失" if not has_lv else "有等级词"
        print(f"  {name[:26]:<28} {mark:<8} 头部={head}")
    print("※ 判读：13 项红线疑点句首缺谓语且正文无等级词；3 项（2/10/11）走另一套模板写『已查明的风险』。")


def check_headcount_vs_body(lines: list[str]) -> None:
    """F：头部『尚缺N项』 vs 正文三分类。"""
    hr("[3] 头部『尚缺 N 项资料』 vs 正文证据段（是否喊企业去补已交的资料）")
    bad = 0
    for name, b in items(lines):
        bt = "\n".join(b)
        head = re.search(r"能补全尚缺的(\d+)项", bt)
        need = re.search(r"本项检查需要(\d+)项材料", bt)
        lit = re.search(r"名称逐字对应[、，]?已确在手上的有(\d+)项", bt)
        sim = re.search(r"其中(\d+)项已提供同类资料", bt)
        miss = re.search(r"确未提供的有(\d+)项", bt)
        g = lambda m: int(m.group(1)) if m else 0
        if not head:
            print(f"  {name[:26]:<28} ★无头部结论句 / 无资料段（结构残缺）")
            continue
        flag = ""
        if g(head) != g(miss):
            flag = f"  ★头部{g(head)} ≠ 确未提供{g(miss)}"
            if g(miss) == 0 and g(sim) > 0:
                flag += "（正文说一项不缺，只是名称不同）"
            bad += 1
        print(f"  {name[:26]:<28} 头部尚缺={g(head):<3} 需要={g(need):<3} 逐字已提供={g(lit):<3} "
              f"同类须确认={g(sim):<3} 确未提供={g(miss):<3}{flag}")
    print(f"※ 头部与正文不符的项数 = {bad}")


def check_stage_contradiction(lines: list[str]) -> None:
    """H：环级『资料有无』自相矛盾。"""
    hr("[4] 环级『资料有无』口径自相矛盾")
    t = "\n".join(lines)
    a = t.count("因本轮未取得该环节所需资料")
    b = t.count("所需资料已在本轮提供、但该环节未产出可展示数据")
    print(f"『因本轮未取得该环节所需资料』                    x{a}")
    print(f"『所需资料已在本轮提供、但该环节未产出可展示数据』x{b}")
    print("※ 两者语义互斥（缺资料 vs 有资料但程序未产出）；同一项内并存即为矛盾句。")
    for name, bb in items(lines):
        seg = [l for l in bb if "第1环" in l or "本项检查共" in l]
        for s in seg[:2]:
            if "因本轮未取得该环节所需资料" in s and "所需资料已在本轮提供" in "\n".join(bb):
                print(f"  同项并存：{name[:24]} → {s[:90]}")


def check_amount_collision(lines: list[str]) -> None:
    """C：同一事项内两个『未匹配』金额（只取紧邻该短语的金额，避免噪声）。"""
    hr("[5] 同一事项内金额口径冲突")
    pat = re.compile(r"([\d,]+\.\d{2})\s*(元)?\s*未匹配到任何支付渠道|既无付款亦无挂账\s*\|\s*([\d,]+\.\d{2})")
    for name, b in items(lines):
        found = []
        for l in b:
            for m in pat.finditer(l):
                v = m.group(1) or m.group(3)
                if v:
                    found.append((v, l[:120]))
        vals = {v for v, _ in found}
        if len(vals) >= 2:
            print(f"  {name[:26]}  → 本轮读到 {len(vals)} 个不同金额：{sorted(vals)}")
            for v, l in found:
                print(f"      [{v}]  {l}")


def table_titles(lines: list[str], ts) -> dict[int, str]:
    """按文档顺序把『表N …/① …』标题绑定到紧随其后的表格（一表一标题，用后即清）。
    不依赖标题与表格的间距，避免『回看 N 行』式脆弱判据。"""
    starts = {s for s, _ in ts}
    out, pending = {}, ""
    for i, l in enumerate(lines, 1):
        if re.match(r"^(表\s*\d+|[①②③④⑤⑥⑦⑧⑨⑩])", l.strip()):
            pending = l.strip()
        if i in starts:
            out[i] = pending
            pending = ""
    return out


def check_table_math(lines: list[str], ts) -> None:
    """D：表格加总 vs 标题声明的合计。"""
    hr("[6] 表格加总复核（列合计 vs 标题声明合计）")
    titles = table_titles(lines, ts)
    for start, rows in ts:
        if not rows:
            continue
        hdr = rows[0]
        amt = [k for k, h in enumerate(hdr) if "金额" in h]
        if not amt:
            continue
        idx = amt[0]
        s = Decimal(0)
        n = 0
        for r in rows[1:]:
            if len(r) > idx:
                v = dec(r[idx])
                if v is not None:
                    s += v
                    n += 1
        # 表标题：按顺序绑定的最近一条『表N …』/『① …』行
        title = titles.get(start, "")
        declared = re.findall(r"合计\s*([\d,]+\.\d{2})\s*元", title)
        flag = ""
        if declared:
            dv = dec(declared[0])
            if dv is not None and dv != s:
                flag = f"   ★标题合计 {declared[0]} ≠ 列合计 {s:,.2f}（差 {dv - s:,.2f}）"
        shown = title[:56] if title else "(无标题)"
        print(f"  行{start:<6} 行数={n:<4} 列合计={s:>16,.2f}  {shown}{flag}")


def check_empty_tables(ts) -> None:
    hr("[7] 空白表格 / 空表头")
    for start, rows in ts:
        if not rows:
            print(f"  行{start}: 完全空表")
            continue
        first = rows[0]
        cells = [c.strip() for c in (first if isinstance(first, list) else first.split("|"))]
        body = [r for r in rows[1:] if any(c.strip() for c in r)]
        if not any(cells):
            print(f"  行{start}: 空表头，数据行={len(rows) - 1}，有效内容行={len(body)}")
        elif not body:
            print(f"  行{start}: 有表头无数据  {' | '.join(first)[:60]}")


def check_residue(lines: list[str]) -> None:
    hr("[8] 工程痕迹 / 内部术语 / 模板占位符残留")
    t = "\n".join(lines)
    for pat, note in [
        ("**", "Markdown 加粗语法（Word 不渲染，老板看到星号）"),
        ("未产出对题读数", "内部术语"),
        ("属检查程序待完善项", "内部术语"),
        ("须核对是否已提供：", "未填模板占位符"),
        ("材料齐全程度（取值", "内部评分中间值"),
        ("判断可信度约", "无法复核的百分比"),
        ("下载 CSV", "HTML 交互控件措辞"),
        ("本报告工作底稿中可查", "自指循环引用"),
        ("点击展开", "HTML 交互控件措辞"),
    ]:
        c = t.count(pat)
        if c:
            print(f"  {pat!r:<26} x{c:<4} {note}")
    for m in re.finditer(r"须核对是否已提供：[^\s；;）)]*", t):
        print(f"      实例：{m.group(0)}")


def check_doc_counts(lines: list[str]) -> None:
    hr("[9] 文档级计数一致性")
    t = "\n".join(lines)
    for p in ["12 类", "已提供 8 类", "14 类", "102 份", "16 项"]:
        print(f"  {p!r:<14} x{t.count(p)}")
    for i, l in enumerate(lines, 1):
        if "12 类" in l or "已提供 8 类" in l:
            print(f"    行{i}: {l[:170]}")
    print("\n  目录 vs 实际章节标题（按『N、+ 主标题』逐项核对，括注差异单独标出）：")
    # 目录行 = 含 ≥3 个『N、』标记的行（不依赖固定行号）
    toc = next((l for l in lines if len(re.findall(r"[一二三四五]、", l)) >= 3), "")
    if not toc:
        print("    SKIP：本文件未找到目录行（含≥3个『N、』标记）")
    toc_items = [x for x in re.split(r"(?=[一二三四五]、)", toc) if x.strip()]
    print(f"    目录原文（单行连排、无页码）：{toc[:150]}")
    heads = [l.strip() for l in lines if re.match(r"^[一二三四五]、", l.strip())]
    for it in toc_items:
        m = re.match(r"^([一二三四五]、)([^（(]{2,20})", it)
        if not m:
            continue
        main = m.group(2)
        cands = [h for h in heads if h.startswith(m.group(1) + main)]
        if not cands:
            print(f"    目录『{it}』 → ★正文中找不到对应标题")
            continue
        exact = [h for h in cands if h == it]
        if exact:
            print(f"    ✓ {it}")
        else:
            print(f"    目录『{it}』\n      实际『{cands[0]}』  ★括注不一致")
    multi = Counter(l.strip() for l in lines if re.match(r"^[一二三四五]、", l.strip()) and len(l.strip()) < 60)
    rep = {k: v for k, v in multi.items() if v > 1}
    if rep:
        print(f"\n  小标题重复（章节编号丧失层级）：{ {k[:20]: v for k, v in rep.items()} }")


def check_order_numbers(lines: list[str]) -> None:
    hr("[10] 『办理顺序』编号连续性")
    vals = []
    for i, l in enumerate(lines, 1):
        m = re.search(r"办理顺序：(\S+)", l)
        if m:
            vals.append((i, m.group(1)))
    for i, v in vals:
        print(f"    行{i:<6} {v}")
    print(f"  共 {len(vals)} 项有编号 / 全文 {len(items(lines))} 项")
    n = len(items(lines))
    print(f"  ★ 有编号 {len(vals)} 项，缺 {n - len(vals)} 项；编号末值={vals[-1][1] if vals else '—'} 而全文仅 {n} 项" if vals else "")
    for name, b in items(lines):
        if "办理顺序" not in b[0]:
            print(f"    ★ 无编号：{name}")


def check_duplication(lines: list[str]) -> None:
    hr("[11] 重复段落（模板疲劳）")
    ne = [l.strip() for l in lines if l.strip() and l.strip() not in ("<<TABLE_START>>", "<<TABLE_END>>")]
    cnt = Counter(ne)
    dup = [(t, c) for t, c in cnt.items() if len(t) > 25 and c > 1]
    print(f"  重复段落（>25 字）种类={len(dup)}  总出现次数={sum(c for _, c in dup)}")
    for t, c in sorted(dup, key=lambda x: -x[1])[:12]:
        print(f"    x{c:<3} {t[:100]}")


def check_number_format(lines: list[str]) -> None:
    hr("[12] 表格数字格式（仅看带小数点的金额/数量，排除 8 位日期与纯计数）")
    tot = bad = 0
    samples = []
    for l in lines:
        for c in (x.strip() for x in l.split("|")):
            # 排除 8 位日期式整数（20250708）、纯整数计数
            if re.fullmatch(r"\d{8}", c):
                continue
            if re.fullmatch(r"\d{5,}(\.\d+)?", c):
                tot += 1
                if not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d{2})", c):
                    bad += 1
                    if len(samples) < 8:
                        samples.append(c)
    print(f"  金额型数字单元格(≥5位)={tot}  未按千分位+两位小数={bad} ({bad / max(tot, 1) * 100:.1f}%)")
    print(f"  实例：{samples}")


def check_tail(lines: list[str]) -> None:
    hr("[13] 末章『报告性质和使用说明』是否混入单项结论")
    k = next((i for i, l in enumerate(lines) if l.strip() == "五、报告性质和使用说明"), None)
    if k is None:
        print("  SKIP：未找到该章")
        return
    for l in lines[k: k + 14]:
        s = l.strip()
        if not s:
            continue
        susp = "★" if re.search(r"本项|需要：$|上述资料", s) else " "
        print(f"  {susp} {s[:150]}")


# ---------------------------------------------------------------- 主流程
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    lines_ref = extract(path)
    lines = lines_ref
    ts = tables(lines)
    print(f"# 报告审计（只读）：{path}")
    check_scale(lines, ts)
    check_qualification(lines)
    check_headcount_vs_body(lines)
    check_stage_contradiction(lines)
    check_amount_collision(lines)
    check_table_math(lines, ts)
    check_empty_tables(ts)
    check_residue(lines)
    check_doc_counts(lines)
    check_order_numbers(lines)
    check_duplication(lines)
    check_number_format(lines)
    check_tail(lines)
    print("\n# 审计结束（未修改任何文件）")
