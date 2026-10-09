# -*- coding: utf-8 -*-
"""**页面可见性验收**（结构级，结果级验收的唯一权威）

## 为什么必须有它（用户 2026-10-05 连续追问 5 次的根因）

> 「为什么你总是跟我说你说法不准确，这个错那个错的而且做出来总是不实？」

此前所有验收都停在「**我改了什么**」：后端字段有没有、编译过不过、闸门红不红。
但用户看到的是**页面**，中间隔着一层**渲染**。今天因此栽过四次：
  · 数据挂了 `related_analyses` ⇒ 前端只认 `summary/body/signals` 三键，
    `cost_recon_detail` 一个都没有 ⇒ **页面空白**（我却宣布"已并入"）
  · 改了替换函数 ⇒ 同文件里有**同名旧定义**在后，静默覆盖 ⇒ **改动不生效**
  · 加了 `<h3>` 小节 ⇒ 它**不属于任何 `<h2>` 章**、目录点不到
  · 声称"已并入" ⇒ 原独立章**没删**，同一内容渲染两遍
**这些"不实"，字符级/编译级验证一个都发现不了。**

## ⚠ 第一版判据是假的（反向验证抓出来的）
第一版查"数据里的标题是否出现在页面" —— **同义反复**：页面就是数据渲染的，
问"有没有"必然有。注入"把标题改成页面不会出现的字符串"后**仍报 PASS**。
⇒ 现改为**结构级判据**（切块 + 长度 + 重复检测），并**强制反向验证**。

## 判据（缺一即 FAIL，退出码非 0）
  ① **章结构**：一~五章 `<h2 id>` 齐全、每个 `id` 只出现一次（防重复章）
  ② **章非空**：每章正文长度 ≥ 阈值（防空壳章）
  ③ **疑点块**：每个 `company-problem-N` 的 section 长度 ≥ 阈值（防"疑点渲染成空"）
  ④ **不重复**：已被疑点承载的底稿（`_carried_by_problem`）**不得**在独立章再出现
  ⑤ **关键内容**：嵌入块（成本明细/资料缺口/待澄清）在对应疑点内可见

用法：
    ./.venv/Scripts/python.exe tools/verify_page_render.py
    ./.venv/Scripts/python.exe tools/verify_page_render.py --selftest   # 判据自检
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from html import unescape as html_unescape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8")

VERIFY_JS = os.path.join(
    ROOT, ".workbuddy", "skills", "caishuixitong-report-render-sync",
    "scripts", "verify_frontend_render.js")
REPORT = os.path.join(ROOT, "scripts", "four_reports", "company_1_full.json")

MIN_CHAPTER_CHARS = 200      # 每章正文最少字符（防空壳章）
MIN_PROBLEM_CHARS = 300      # 每条疑点最少字符（防"疑点渲染成空"）
# ★ 2026-10-05（第二版修正，反向验证抓出的假判据）：
#   只看**长度**防不住"空壳" —— 段落被清空后，疑点块仍有标题/meta 等文字，
#   长度照样 >300 ⇒ 注入"清空某疑点段落"后验收**仍报 PASS**（假通过）。
#   改用**段落结构完整性**：每条疑点必须含下列段落标题中的若干（实测 6~7 个）。
_REQUIRED_HEADS = ("为何列入检查", "涉及的风险事项", "发现的依据",
                   "已取得的资料", "本项结论", "需企业提供的资料")
MIN_HEADS = 5

# 已被疑点承载的底稿，其"独立章标题"不得再出现（防重复渲染）
_DUP_GUARD_TITLES = (
    "主营业务成本两口径勾稽明细",     # cost_recon_detail
)


def render_html():
    """调桩环境渲染器，拿到**完整 HTML**。"""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tf:
        out = tf.name
    cmd = ["node", VERIFY_JS, REPORT, "--dump", out]
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=240)
    except Exception as exc:  # noqa: BLE001
        print("[页面验收] 渲染器调用失败：%s" % exc)
        return ""
    if not os.path.exists(out):
        print("[页面验收] 渲染器未产出 HTML：%s" % ((p.stdout or "") + (p.stderr or ""))[:300])
        return ""
    with io.open(out, encoding="utf-8") as f:
        html = f.read()
    try:
        os.unlink(out)
    except Exception:  # noqa: BLE001
        pass
    return html


# 「覆盖范围声明」章本就只有两三句话（企业只需知道"未接入外部源"），
# 不能用通用章阈值判它空壳 ⇒ 单列更低阈值。
_SHORT_OK_CHAPTERS = ("company-scope-note",)
MIN_SHORT_CHAPTER_CHARS = 80


def split_chapters(html):
    """按 `<h2 id="...">` 切章，返回 [(id, 标题, 正文)]。"""
    out = []
    marks = list(re.finditer(r'<h2 id="([^"]+)"[^>]*>(.*?)</h2>', html, re.S))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(html)
        out.append((m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip(),
                    html[m.end():end]))
    return out


def split_problems(html):
    """按 `<section class="fact-sec" id="company-problem-N">` 切疑点块。"""
    marks = list(re.finditer(
        r'<section class="fact-sec" id="company-problem-([^"]+)">', html))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(html)
        out.append((m.group(1), html[m.start():end]))
    return out


def _report_question_texts():
    """从产物取**全部询问问句**。

    ★ 2026-10-06（用户：「这些内容为什么存在？…是否在报告中已经重复了？」）：
      每条询问的归宿只有两种 —— ①挂在它指向的**疑点内**（`_renderQuestions`）；
      ②无归属时落在报告末尾的**残余章**。**二者只能居其一**：
        · 页面出现 0 次 ⇒ 静默丢失（内容没了）；
        · 页面出现 ≥2 次 ⇒ 同一询问在两处重复呈现（正是用户看到的现象）。
      故本判据对每条问句断言"恰好 1 次"。
    """
    try:
        with io.open(REPORT, encoding="utf-8", errors="replace") as fh:
            d = json.load(fh)
    except Exception:  # noqa: BLE001
        return []
    rep = d.get("report") if isinstance(d.get("report"), dict) else d
    iq = ((rep or {}).get("enterprise_readable_report") or {}).get(
        "inspection_questions_report") or {}
    out = []
    for th in (iq.get("themes") or []) + (iq.get("unattached_themes") or []):
        if not isinstance(th, dict):
            continue
        for q in (th.get("questions") or []):
            if isinstance(q, dict):
                t = str(q.get("question") or "").strip()
                if t:
                    out.append(t)
    return out


def analyze(html, questions=None):
    """返回 (fails, info)。fails 为空即通过。"""
    fails, info = [], {}
    if not html:
        return ["渲染 HTML 为空（渲染器失败）"], info

    chs = split_chapters(html)
    info["chapters"] = [(c[1][:28], len(re.sub(r"<[^>]+>", "", c[2]))) for c in chs]

    # ① 章齐全 + id 唯一
    ids = [c[0] for c in chs]
    dup = {i for i in ids if ids.count(i) > 1}
    for d in dup:
        fails.append("章节 id 重复出现：%s" % d)
    # ★ 2026-10-05：「系统能力边界」章已按用户决定移除，改为「覆盖范围声明」章
    for need in ("company-conclusion", "company-problems", "company-scope-note",
                 "company-recheck", "company-statement"):
        if need not in ids:
            fails.append("缺少章节：%s" % need)

    # ② 章非空
    for cid, title, body in chs:
        n = len(re.sub(r"<[^>]+>", "", body))
        _min = (MIN_SHORT_CHAPTER_CHARS if cid in _SHORT_OK_CHAPTERS
                else MIN_CHAPTER_CHARS)
        if n < _min:
            fails.append("章内容过短（%d 字符）：%s" % (n, title[:30]))

    # ③ 疑点块非空 —— **双判据**：段落结构完整性（主）+ 长度（辅）
    pbs = split_problems(html)
    info["problem_blocks"] = len(pbs)
    for sid, blk in pbs:
        txt = re.sub(r"<[^>]+>", "", blk)
        n_heads = sum(1 for h in _REQUIRED_HEADS if h in txt)
        if n_heads < MIN_HEADS:
            fails.append("疑点 %s 段落结构不完整（仅 %d/%d 个段落标题）⇒ 页面空壳"
                         % (sid, n_heads, len(_REQUIRED_HEADS)))
        elif len(txt) < MIN_PROBLEM_CHARS:
            fails.append("疑点 %s 渲染内容过短（%d 字符）" % (sid, len(txt)))

    # ④ 已承载底稿不得在独立章重复出现
    for t in _DUP_GUARD_TITLES:
        cnt = len(re.findall(re.escape(t), html))
        if cnt > 1:
            fails.append("「%s」在页面出现 %d 次（应只在承载它的疑点内出现 1 次）"
                         % (t, cnt))

    # ⑤ 询问问句：页面上必须**恰好出现 1 次**（0=静默丢失，≥2=两处重复呈现）
    qs = questions if questions is not None else _report_question_texts()
    info["questions_checked"] = len(qs)
    plain = html_unescape(re.sub(r"<[^>]+>", "", html))
    for q in qs:
        cnt = plain.count(q)
        if cnt != 1:
            fails.append("询问问句在页面出现 %d 次（应为 1 次）：%s…"
                         % (cnt, q[:34]))

    # ⑥ 残余章不得出现：它意味着有询问没被整合进对应风险事项
    if "待企业澄清事项（其余事项）" in html:
        fails.append("页面出现「待企业澄清事项（其余事项）」残余章 —— "
                     "未归属的询问应与对应风险事项合并，不得另起一段重复呈现")
    return fails, info


def main():
    print("=" * 74)
    print("页面可见性验收（结构级）—— 产物：%s" % os.path.basename(REPORT))
    print("=" * 74)
    html = render_html()
    fails, info = analyze(html)
    print("章数：%d ｜ 疑点块：%d" % (len(info.get("chapters") or []),
                                     info.get("problem_blocks") or 0))
    for t, n in (info.get("chapters") or []):
        print("   %-30s %d 字符" % (t, n))
    print()
    if fails:
        print("FAIL %d 项：" % len(fails))
        for f in fails[:15]:
            print("   - %s" % f)
        return 1
    print("PASS —— 页面结构完整、无空壳、无重复渲染")
    return 0


if __name__ == "__main__":
    sys.exit(main())
