# -*- coding: utf-8 -*-
"""法条引用切分（`engine/legal_citation.split_citation`）的回归锁。

**为什么要有这组测试**（T-5 根因，2026-10-12 实测）：
`split_citation` 是"法名 / 条文 / 括注 / 内容"分离的**唯一权威**，
被 4 处内部函数 + 法条版本闸门 + 报告呈现共用，**此前零专门测试**。
实测发现它把**条文残段**拼回法名（3 类写法），导致：
  · 法条版本闸门把 `企业所得税法实施条例第四十条至` 当成一个"不存在的法名"⇒ **假缺口**；
  · 「引用 204 处、未登记 47 个」中的一部分是**切分噪声**而非真实未登记。

本组锁住五件事：
  ① **核心不变量**：全库引用切出的**法名不得含条文号**（`第X条`）；
  ② 范围条文「第X条**至**第Y条」整体识别（不得只取后半）；
  ③ **无书名号**写法（`财税〔2003〕158号第二条`）也要剥离条文；
  ④ 既有形态不得破坏（点号并列 / 冒号内容 / 括注 / 《》归一）；
  ⑤ 切不出法名时不得返回空（空法名会让下游静默失配）。

★ 隔离原则：纯函数 + 只读红线库，不落盘、不碰真实库。
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from engine.legal_citation import split_citation      # noqa: E402
from engine.tax_redlines import REDLINES              # noqa: E402

_ART_IN_LAW = re.compile(r"第[一二三四五六七八九十百零〇\d]+条")


def _all_citations() -> list:
    out = []
    for r in (REDLINES or []):
        lb = (r or {}).get("legal_basis")
        if isinstance(lb, str):
            lb = [lb]
        for it in (lb or []):
            if isinstance(it, str) and it.strip():
                out.append(it)
    return out


class TestLawNameHasNoArticleNumber:
    """① 核心不变量：法名不得含条文号（全库 204 处）。"""

    def test_no_article_in_law_name(self):
        bad = []
        for c in _all_citations():
            law = split_citation(c)[0]
            if _ART_IN_LAW.search(law):
                bad.append((law, c[:50]))
        assert not bad, "法名残留条文号：\n" + "\n".join(
            "%s  <=  %s" % (b[0], b[1]) for b in bad)

    def test_law_name_never_empty(self):
        bad = [c[:50] for c in _all_citations() if not split_citation(c)[0]]
        assert not bad, "切不出法名：\n" + "\n".join(bad)


class TestRangeArticle:
    """② 范围条文「第X条至第Y条」整体识别。"""

    def test_range_kept_whole(self):
        law, art, _, _ = split_citation("《企业所得税法实施条例》第四十条至第四十五条（各费用扣除限额）")
        assert law == "企业所得税法实施条例"
        assert art == "第四十条至第四十五条"

    def test_range_without_note(self):
        law, art, _, _ = split_citation("《某法》第三条至第七条")
        assert law == "某法" and art == "第三条至第七条"

    def test_article_after_other_text_not_merged_into_law(self):
        """条文后还有内容（如「及其实施细则」）时，法名仍须干净。"""
        law, art, _, _ = split_citation("《增值税暂行条例》第六条及其实施细则第十二条（价外费用并入销售额）")
        assert law == "增值税暂行条例"
        assert "第六条" not in law


class TestNoBookQuote:
    """③ 无书名号写法也要剥离条文。"""

    def test_plain_wenhao_form(self):
        law, art, _, content = split_citation("财税〔2003〕158号第二条：视为红利分配")
        assert law == "财税〔2003〕158号"
        assert art == "第二条"
        assert "红利" in content

    def test_plain_wenhao_multi_article(self):
        law, art, _, _ = split_citation("国家税务总局公告2011年第25号第四条、第五条")
        assert law == "国家税务总局公告2011年第25号"
        assert art == "第四条、第五条"


class TestExistingFormsNotBroken:
    """④ 既有形态回归。"""

    def test_single_article_with_book_quote(self):
        assert split_citation("《发票管理办法》第二十七条")[:2] == ("发票管理办法", "第二十七条")

    def test_multi_article_with_comma(self):
        assert split_citation("《发票管理办法》第二十七条、第二十八条")[:2] == (
            "发票管理办法", "第二十七条、第二十八条")

    def test_full_name_normalized(self):
        """《中华人民共和国税收征收管理法》→ 去掉「中华人民共和国」。"""
        assert split_citation("《中华人民共和国税收征收管理法》第六十三条")[0] == "税收征收管理法"

    def test_content_after_colon_split(self):
        law, art, _, content = split_citation("《某法》第五条：这是内容")
        assert (law, art, content) == ("某法", "第五条", "这是内容")

    def test_trailing_note_extracted(self):
        law, art, note, _ = split_citation("《某法》第五条（说明文字）")
        assert law == "某法" and note == "（说明文字）"

    def test_empty_input(self):
        assert split_citation("") == ("", "", "", "")
        assert split_citation(None) == ("", "", "", "")


class TestReverseGuard:
    """⑤ 反向验证：**两道防线同时失效**时，核心不变量必须变红。

    两道防线 = ① `_ART_RE` 认范围条文 + ② `strip_article_from_law` 兜底。
    只破坏其一不足以暴露（实测：仅还原 `_ART_RE` 时兜底仍会切干净）——
    故本测试**两道一起破坏**，证明「法名不含条文号」这条判据不是同义反复。
    """

    def test_invariant_catches_regression_when_both_defenses_broken(self, monkeypatch):
        import engine.legal_citation as lc
        # 破坏 ①：还原为"未修"的 `_ART_RE`（不认范围）
        monkeypatch.setattr(lc, "_ART_RE", re.compile(
            r"(第[一二三四五六七八九十百零〇\d]+条"
            r"(?:\s*[、,，]\s*第[一二三四五六七八九十百零〇\d]+条)*"
            r"(?:第[一二三四五六七八九十]+款)?)\s*$"))
        # 破坏 ②：兜底变恒等
        monkeypatch.setattr(lc, "strip_article_from_law", lambda s: str(s or ""))
        law = lc.split_citation("《某法》第三条至第七条")[0]
        assert _ART_IN_LAW.search(law), "判据失真：两道防线都破坏后法名竟仍无条文号"

    def test_invariant_green_after_restore(self):
        assert split_citation("《某法》第三条至第七条")[0] == "某法"
