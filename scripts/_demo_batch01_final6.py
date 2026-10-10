# -*- coding: utf-8 -*-
"""第1批「6 处新不一致」的**可复现抓捕/放行**脚本（用户《终极修正指令》第三/第四步）。

对每一处做**双向**验证：
  ① 置为「不一致状态」→ 跑**同一个**门禁（D1）→ 必须报 ERROR
  ② 置为「一致状态」→ 跑同一门禁 → **本处消费点**不得再报错
  ③ 无论如何都**还原**并复核
  ④ 聚合：6 处**同时**置为一致 ⇒ 这些主题上必须 0 ERROR

★ 复用上一轮的三条锁：变异无效⇒报"用例无效"；断言目标取两向并集（防空集假通过）；"本来就是旧态"不算错。

```bash
./.venv/Scripts/python.exe scripts/_demo_batch01_final6.py
./.venv/Scripts/python.exe scripts/_demo_batch01_final6.py 5
```
退出码 0 = 6 处全部「抓得住 + 放得过」。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOCDIR = ROOT / "docs" / "第01批_触发条件与认定要件分离"
FMIN = "最小检查集.md"
FFIN = "最终判断.md"
FD = "5个Skill设计文档.md"
FC = "5个Skill配置JSON.md"
FT = "5个Skill测试用例.md"
FR = "5个Skill回归测试报告.md"
FV = "5个Skill验收自证.md"
FGR = "5个Skill门禁规则.md"

def _cn(n):
    """1..20 → 中文数字（门禁规则表的 D1 条数用中文表达）。"""
    d = "零一二三四五六七八九十"
    return d[n] if n <= 10 else ("十" + d[n - 10] if n < 20 else "二十")


def _grp(prefix):
    """数门禁规则表里某一组（D0/D1/D2/D3/D4/D5）的判据行数 —— **现算**，不硬编码。"""
    txt = (DOCDIR / "5个Skill门禁规则.md").read_text(encoding="utf-8")
    return len([l for l in txt.split("\n") if re.match(r"^\\| \\*\\*%s-R\\d+\\*\\*" % prefix, l)])


def A(number_id):
    """**现算**权威值（不硬编码）—— 上一轮的教训：锚点写死会随权威变动而静默失效。"""
    from engine import doc_consistency_core as core
    core.reload_config()
    for n in core.config()["numbers"]:
        if n["id"] == number_id:
            v, why = core.authority_value(n["authority"])
            assert v is not None, (number_id, why)
            return v
    raise KeyError(number_id)


ITEMS = [
    dict(no=1, gate="D1", subject="本批交付物文件数",
         desc="最小检查集 §〇「22 份」+ 文末「26 份」 vs 实际现算值",
         targets=[(FMIN, "| ⑩ | 本批目录交付物文件数 | **%d** |" % A("batch_doc_count"),
                          "| ⑩ | 本批目录交付物文件数 | **22** |"),
                  (FMIN, "本批目录内 `*.md` 共 = **%d 份**）" % A("batch_doc_count"),
                          "本批目录内 `*.md` 共 = **26 份**）")],
         why="**加宽 `batch_doc_count.claims`**：原正则只认「= N 份）」一种写法，"
             "§〇 表格的「| **N** |」写法从未被校验（缺口 R1）"),
    dict(no=2, gate="D1", subject="门禁判据条数",
         desc="5个Skill验收自证 §2「11 条判据」等 7 个消费点 vs 门禁规则表现算值",
         targets=[(FV,  "（**%d 条判据**）" % A("judgement_count"), "（11 条判据）"),
                  # 分项 clause 用**正则 + 现算**（含中文数字）：判据数一变，子串锚点必然失效

                  (FMIN, "门禁（%d 条判据）" % A("judgement_count"), "门禁（22 条判据）"),
                  (FMIN, "门禁 %d 条判据" % A("judgement_count"), "门禁 22 条判据"),
                  (FFIN, "**%d 条判据**（编号/描述/触发条件/阻断行为）" % A("judgement_count"),
                         "**22 条判据**（编号/描述/触发条件/阻断行为）"),
                  (FFIN, "新增 5 个 `check_doc_*`（**%d 条判据**）" % A("judgement_count"),
                         "新增 5 个 `check_doc_*`（**22 条判据**）"),
                  (FFIN, "门禁 %d 条判据" % A("judgement_count"), "门禁 22 条判据")],
         regex_targets=[
             (FMIN, r"（\*\*\d+ 条判据\*\*：D0 健康闸门 2 \+ D1 \*\*[^）]*?\*\* \+ D2 二 \+ D3 三 \+ D4 五 \+ D5 二）",
              lambda: ("（**%d 条判据**：D0 健康闸门 2 + D1 **%s** + D2 二 + D3 三 + D4 五 + D5 二）"
                       % (A("judgement_count"), _cn(A("judgement_count") - 14))),
              lambda: "（**22 条判据**：D0 健康闸门 2 + D1 八 + D2 二 + D3 三 + D4 五 + D5 二）"),
             # ★ 整行锚点（`[^\n]*` 吞到行尾）+ **全部字段现算** —— 上一版正则只吃到「条」为止，
             #   把 D2/D3 两项**吃掉了**（实测事故：合计行少了 D2 2 条 + D3 3 条）
             (FGR, r"判据合计 \*\*\d+ 条\*\*（[^\n]*",
              lambda: ("判据合计 **%d 条**（D0 共用 %d 条 + D1 **%s**条 + D2 %d 条 + D3 **%s**条 + D4 **%s**条 + D5 %d 条）"
                       % (A("judgement_count"), _grp("D0"), _cn(_grp("D1")), _grp("D2"),
                          _cn(_grp("D3")), _cn(_grp("D4")), _grp("D5"))),
              lambda: "判据合计 **23 条**（D0 共用 2 条 + D1 **九**条 + D2 2 条 + D3 **3** 条 + D4 **五**条 + D5 2 条）"),
         ],
         why="**新增权威 `judgement_count`**（`kind=regex_count`，数 `5个Skill门禁规则.md` 的判据行）；"
             "claims 覆盖 **7 个消费点**（原只覆盖 1 处）"),
    dict(no=3, gate="D1", subject="已登记的数字权威条数",
         desc="5个Skill设计文档 §1「7 个数字权威」+ 5个Skill配置JSON「13」 vs `numbers` 现算值",
         targets=[(FD, "**已登记的数字权威（%d 个）**" % A("authority_count"), "**已登记的数字权威（7 个）**"),
                  (FC, "must_state_in/**enforce**） | **%d** |" % A("authority_count"), "must_state_in/**enforce**） | **13** |")],
         why="**新增权威 `authority_count`**（`kind=json_len`, `len:numbers`）—— 元事实（关于事实的事实）"),
    dict(no=4, gate="D1", subject="权威 kind 种类数",
         desc="5个Skill设计文档 §1「5 种 kind」+ 5个Skill配置JSON 缺声明 vs 现算值",
         targets=[(FD, "取权威值（%d 种 kind）" % A("authority_kind_count"), "取权威值（5 种 kind）"),
                  (FC, "pytest_receipt`、`regex_count`，共 **%d** 种 kind）**：" % A("authority_kind_count"),
                       "pytest_receipt`）**：")],
         why="**新增权威 `authority_kind_count`**（`kind=json_len`, `distinct:numbers.authority.kind`）；"
             "并补齐 5个Skill配置JSON 的 kind 总数声明"),
    dict(no=5, gate="D1", subject="验证类用例口径",
         desc="「反向验证」15/20/25 三种说法 + 破坏性/验证类**缺声明** vs marker 现算值",
         regex_targets=[
             (FFIN,
              r"\*\*反向验证 \d+ 例\*\* \+ 破坏性用例 \*\*\d+ 例\*\* \+ 口径锁 \*\*\d+ 例\*\*（验证类 \*\*\d+ 例\*\*）成立",
              lambda: ("**反向验证 %d 例** + 破坏性用例 **%d 例** + 口径锁 **%d 例**（验证类 **%d 例**）成立"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("validation_case_total"))),
              lambda: "**反向验证 20 例**成立（另 5 例口径锁）"),
             (FV,
              r"反向验证 \*\*\d+ 例\*\*；破坏性用例 \*\*\d+ 例\*\*；口径锁 \*\*\d+ 例\*\*（验证类 \*\*\d+ 例\*\*）成立",
              lambda: ("反向验证 **%d 例**；破坏性用例 **%d 例**；口径锁 **%d 例**（验证类 **%d 例**）成立"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("validation_case_total"))),
              lambda: "反向验证 **15 例**成立（含 2 例口径锁）"),
             (FMIN,
              r"④ \*\*反向验证 \d+ 例\*\* \+ 破坏性用例 \*\*\d+ 例\*\* \+ 口径锁 \*\*\d+ 例\*\*（验证类 \*\*\d+ 例\*\*）成立",
              lambda: ("④ **反向验证 %d 例** + 破坏性用例 **%d 例** + 口径锁 **%d 例**（验证类 **%d 例**）成立"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("validation_case_total"))),
              lambda: "④ **文档一致性 15 例成立**（含 2 例口径锁）"),
             (FR, r"## 4\. 用例分类[^\n]*",
              lambda: ("## 4. 用例分类（`@pytest.mark` **现算**）：反向验证（`test_reverse_*`）**%d 例** + "
                       "破坏性用例（`test_break_*`）**%d 例** + 口径锁（`test_lock_*`）**%d 例** = 验证类 **%d 例**"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("validation_case_total"))),
              lambda: '## 4. 反向验证（`test_reverse_*` **15 例**，另加「改真文件并断言报错」5 例；口径锁 5 例）'),
             (FGR, r"④ 反向验证 \*\*\d+ 例\*\*全报红[^\n]*",
              lambda: ("④ 反向验证 **%d 例**全报红；破坏性用例 **%d 例**；口径锁 **%d 例**；全量用例 **%d 例**"
                       "（四类由 `@pytest.mark` 现算）；⑤ 失败项与修法见 `5个Skill回归测试报告.md`。"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("doc_test_total"))),
              lambda: '④ 反向验证 **15 例**全报红（另有口径锁 5 例，"不得报错"口径：散文≠声明、围栏内=引用区、'
                      '耗时不做数值权威、转义竖线不算列、D5 只管跨文件）；全量用例 **42 例**。'),
             (FMIN, r"- \*\*反向验证 \d+ 例成立\*\*[^\n]*",
              lambda: ("- **反向验证 %d 例成立**；破坏性用例 **%d 例**；口径锁 **%d 例**（验证类 **%d 例**）；"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("validation_case_total"))),
              lambda: '- **反向验证 15 例成立**（其中 2 例是"**不报错**"口径锁：散文≠声明、围栏内=引用区）；'),
             (FFIN, r"\*\*反向验证 \d+ 例\*\*[^\n]*?、失败项",
              lambda: ("**反向验证 %d 例**（另破坏性 **%d 例**、口径锁 **%d 例**）、失败项"
                       % (A("reverse_test_count"), A("break_test_count"), A("lock_test_count"))),
              lambda: "**反向验证 15 例**、失败项"),
             (FR, r"④ 用例分类（现算）：[^\n]*",
              lambda: ("④ 用例分类（现算）：反向验证 **%d 例** + 破坏性用例（`test_break_*`）**%d 例** + "
                       "口径锁（`test_lock_*`）**%d 例** = 验证类 **%d 例**；正例/自证 **%d 例**；全量用例 **%d 例**"
                       % (A("reverse_test_count"), A("break_test_count"), A("lock_test_count"),
                          A("validation_case_total"), A("plain_test_count"), A("doc_test_total"))),
              lambda: ('④ 反向验证成立：`test_reverse_*` **15 例** + 其它「改真文件 ⇒ 必须报红」 **5 例**；'
                       "另有**口径锁 5 例**（不得报错/口径自证）；全量用例 **42 例**")),
         ],
         why="**新增 4 条权威**：`reverse_test_count` / `break_test_count` / `lock_test_count` / `validation_case_total`，"
             "条数由 **pytest marker 现算**（口径不再靠人分）；官方口径：反向验证 = `test_reverse_*`"),
    dict(no=6, gate="D1", subject="正例/自证用例数",
         desc="5个Skill测试用例 §2「口径锁/正例/自证 22 例」（兜底残差）等 vs 四分类现算值",
         targets=[(FT, "（反向验证 **%d 例** + 破坏性用例 **%d 例** + 口径锁 **%d 例**"
                       % (A("reverse_test_count"), A("break_test_count"), A("lock_test_count")),
                       "（含 `test_reverse_*` 15 例 + 其它「改真文件 ⇒ 必须报红」 5 例 + "
                       "口径锁/正例/自证 22 例）")],
         regex_targets=[
             (FT, r"（反向验证 \*\*\d+ 例\*\* \+ 破坏性用例 \*\*\d+ 例\*\* \+ 口径锁 \*\*\d+ 例\*\* \+ 正例/自证 \*\*\d+ 例\*\*）",
              lambda: ("（反向验证 **%d 例** + 破坏性用例 **%d 例** + 口径锁 **%d 例** + 正例/自证 **%d 例**）"
                       % (A("reverse_test_count"), A("break_test_count"),
                          A("lock_test_count"), A("plain_test_count"))),
              lambda: ("（含 `test_reverse_*` 15 例 + 其它「改真文件 ⇒ 必须报红」 5 例 + "
                       "口径锁/正例/自证 22 例）")),
             (FMIN, r"用例分类：反向验证 \*\*\d+ 例\*\* \+ 破坏性用例 \*\*\d+ 例\*\* \+ 口径锁 \*\*\d+ 例\*\* \+ 正例/自证 \*\*\d+ 例\*\*（验证类 \*\*\d+ 例\*\*）",
              lambda: ("用例分类：反向验证 **%d 例** + 破坏性用例 **%d 例** + 口径锁 **%d 例** + "
                       "正例/自证 **%d 例**（验证类 **%d 例**）"
                       % (A("reverse_test_count"), A("break_test_count"), A("lock_test_count"),
                          A("plain_test_count"), A("validation_case_total"))),
              lambda: ""),
         ],
         why="**新增权威 `plain_test_count`**；**禁用兜底残差表达** —— 四类各自登记、各有权威、合计可对齐 42"),
    dict(no=7, gate="D1", subject="文档一致性测试用例总数",
         desc="【附条】用例总数 42 → **52**（本轮新增 10 例）的 6 个消费点",
         regex_targets=[
             (FT, r"用例数（`--collect-only` 实测）：\*\*\d+\*\*",
              lambda: "用例数（`--collect-only` 实测）：**%d**" % A("doc_test_total"),
              lambda: "用例数（`--collect-only` 实测）：**42**"),
             (FT, r"① 用例清单 \*\*\d+\*\* 条",
              lambda: "① 用例清单 **%d** 条" % A("doc_test_total"),
              lambda: "① 用例清单 **42** 条"),
             (FD, r"（\*\*\d+ 例\*\*：22 例基础[^）]*）",
              lambda: ("（**%d 例**：22 例基础 + D0 健康闸门 4 例 + 判据扩充 6 例 + "
                       "最终修正轮 10 例 + **终极修正轮 10 例**）" % A("doc_test_total")),
              lambda: "（**42 例**：22 例基础 + D0 健康闸门 4 例 + 判据扩充 6 例 + 最终修正轮 10 例）"),
             (FR, r"文档一致性 \d+ 例",
              lambda: "文档一致性 %d 例" % A("doc_test_total"),
              lambda: "文档一致性 42 例"),
             (FMIN, r"测试（\d+ 例）",
              lambda: "测试（%d 例）" % A("doc_test_total"),
              lambda: "测试（42 例）"),
             (FMIN, r"测试 \d+ 例",
              lambda: "测试 %d 例" % A("doc_test_total"),
              lambda: "测试 42 例"),
             (FFIN, r"测试 \d+ 例",
              lambda: "测试 %d 例" % A("doc_test_total"),
              lambda: "测试 42 例"),
         ],
         why="【附条】新增 10 个用例 ⇒ **权威值现算从 42 变 52** ⇒ 6 个消费点必须同步"
             "（这正是「权威必须现算」的代价与价值：数字漂了就会红）"),

]


def _errs():
    from engine import doc_number_authority as D1
    from engine import doc_consistency_core as core
    core.reload_config()
    out = [i for i in D1.audit() if i["level"] == "ERROR"]
    core.reload_config()
    return out


def _read(files):
    return {f: (DOCDIR / f).read_text(encoding="utf-8") for f in files}


def _apply(it, texts, direction):
    out = dict(texts)
    # ★ 多值短语用**正则锚点 + 现算构造器**：短语里嵌着多个会各自变动的权威值，
    #   子串锚点会在"测试数一变"时全部失效（本轮实测：加 10 个用例后 42→52）。
    for fname, pat, fix_b, brk_b in it.get("regex_targets", []):
        t = out[fname]
        if not re.search(pat, t):
            return None, "正则锚点未命中 ⇒ 用例无效：%s" % pat[:70]
        # ★ 替换**全部**匹配（同一指标在同一文件可能出现多次，只替第一处会留残）
        out[fname] = re.sub(pat, (brk_b() if direction == "broken" else fix_b()).replace("\\", "\\\\"), t)
        _ = fix_b
    for fname, f_sub, b_sub in it.get("targets", []):
        want, other = (b_sub, f_sub) if direction == "broken" else (f_sub, b_sub)
        t = out[fname]
        if want in t:
            continue
        if other in t:
            out[fname] = t.replace(other, want, 1)
        else:
            return None, "锚点未命中（一致/不一致两种形态都找不到）⇒ 用例无效：%s" % other[:70]
    return out, ""


def _changed_map(a, b):
    out = {}
    for f in a:
        la, lb = a[f].split("\n"), b[f].split("\n")
        ch = {i + 1 for i in range(max(len(la), len(lb)))
              if (la[i] if i < len(la) else None) != (lb[i] if i < len(lb) else None)}
        if ch:
            out[f] = ch
    return out


def _files_of(it):
    fs = {t[0] for t in it.get("targets", [])}
    fs |= {t[0] for t in it.get("regex_targets", [])}
    return sorted(fs)


def _run(it):
    files = _files_of(it)
    snap = _read(files)
    res = dict(it)
    res.update({"ok": False, "changed": [], "broken_hits": [], "fixed_hits": [],
                "broken_changed": [], "files": files})
    try:
        broken, err = _apply(it, snap, "broken")
        if err:
            res["error"] = err
            return res
        for f, t in broken.items():
            (DOCDIR / f).write_text(t, encoding="utf-8")
        bad = _errs()
        res["broken_hits"] = ["%s ｜ %s" % (e.get("where"), str(e.get("detail"))[:150])
                              for e in bad if it["subject"] in str(e.get("detail"))
                              or "元判据" in str(e.get("detail"))]
        res["caught"] = bool(res["broken_hits"])
        res["broken_changed"] = sorted("%s:%d" % (f, n) for f, s in _changed_map(snap, broken).items()
                                       for n in s)

        fixed, err = _apply(it, snap, "fixed")
        if err:
            res["error"] = err
            return res
        cm = _changed_map(snap, fixed)
        res["changed"] = sorted("%s:%d" % (f, n) for f, s in cm.items() for n in s)
        if not cm and not res["broken_changed"]:
            res["error"] = "**变异未生效**（两个方向都改不动 ⇒ 用例无效，不得当作通过）"
            return res
        for f, t in fixed.items():
            (DOCDIR / f).write_text(t, encoding="utf-8")
        targets = set(res["changed"]) | set(res["broken_changed"])
        bad = _errs()
        # ★ 逐处断言只看"**本处主题**"的错误：同一行可能同时被另一处改（那样它的报错不归本处）
        res["fixed_hits"] = ["%s ｜ %s" % (e.get("where"), str(e.get("detail"))[:130])
                             for e in bad
                             if str(e.get("where", "")) in targets
                             and (it["subject"] in str(e.get("detail")) or "元判据" in str(e.get("detail")))]
        res["passes"] = not res["fixed_hits"]
    finally:
        for f, t in snap.items():
            (DOCDIR / f).write_text(t, encoding="utf-8")
    res["restored"] = all((DOCDIR / f).read_text(encoding="utf-8") == snap[f] for f in snap)
    res["ok"] = bool(res.get("caught") and res.get("passes") and res.get("restored"))
    return res


SUBJECTS = ("本批交付物文件数", "门禁判据条数", "已登记的数字权威条数", "权威 kind 种类数",
            "反向验证用例数", "破坏性用例数", "口径锁用例数", "验证类用例合计", "正例/自证用例数")


def _subjects_error():
    return ["%s ｜ %s" % (e.get("where"), str(e.get("detail"))[:110])
            for e in _errs() if any(s in str(e.get("detail")) for s in SUBJECTS)
            or "元判据" in str(e.get("detail"))]


def _all_at_once():
    files = sorted({f for it in ITEMS for f in _files_of(it)})
    snap = _read(files)
    cur = dict(snap)
    try:
        for it in ITEMS:
            cur, err = _apply(it, cur, "fixed")
            if err:
                return {"error": "%s（第 %d 处）" % (err, it["no"]), "before": []}
        for f, t in cur.items():
            (DOCDIR / f).write_text(t, encoding="utf-8")
        return {"before": _subjects_error(), "error": ""}
    finally:
        for f, t in snap.items():
            (DOCDIR / f).write_text(t, encoding="utf-8")


def main() -> int:
    only = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    print("=" * 80)
    print("第1批 6 处新不一致 —— 抓捕/放行**双向**可复现（置为不一致 → 跑同一门禁 → 置为一致 → 再跑 → 还原）")
    print("=" * 80)
    bad = 0
    for it in ITEMS:
        if only and it["no"] != only:
            continue
        r = _run(it)
        print("\n【%02d】%s" % (r["no"], r["desc"]))
        print("     涉及文件：%s ｜ 门禁：%s ｜ 判据：%s" % ("、".join(r["files"]), r["gate"], r["why"]))
        if r.get("error"):
            print("     ⚠ %s" % r["error"])
            bad += 1
            continue
        print("     ① 置为不一致（%s）⇒ 报 ERROR %d 条：%s"
              % ("、".join(r["broken_changed"] or ["本就为不一致态"]), len(r["broken_hits"]),
                 "✅ 抓住" if r["caught"] else "❌ 未抓住"))
        for h in r["broken_hits"][:3]:
            print("        %s" % h)
        _pts = sorted(set(r["changed"]) | set(r["broken_changed"]))
        print("     ② 置为一致（%s）⇒ 该处 ERROR %d 条：%s"
              % ("、".join(_pts) if _pts else "（快照本就是一致态）", len(r["fixed_hits"]),
                 "✅ 放行" if r["passes"] else "❌ 仍报错"))
        for h in r["fixed_hits"][:2]:
            print("        %s" % h)
        print("     ③ 已还原：%s ｜ 判定：%s" % ("✅" if r["restored"] else "❌",
                                                "✅ 抓得住 + 放得过" if r["ok"] else "❌ 不成立"))
        if not r["ok"]:
            bad += 1

    if not only:
        agg = _all_at_once()
        print("\n" + "-" * 80)
        if agg.get("error"):
            print("【聚合】⚠ %s" % agg["error"])
            bad += 1
        else:
            print("【聚合】6 处**同时**置为一致 ⇒ 这些主题上 ERROR %d 条：%s"
                  % (len(agg["before"]), "✅ 全部放行" if not agg["before"] else "❌ 仍有残留"))
            for h in agg["before"][:6]:
                print("        %s" % h)
            if agg["before"]:
                bad += 1

    print("\n" + "=" * 80)
    print("合计：%d 处不成立" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
