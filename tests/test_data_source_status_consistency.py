# -*- coding: utf-8 -*-
"""数据源状态一致性 Skill（7）—— 单元 / 集成 / 反向验证（2026-10-07）。

## 用户点名的问题（实测取证）
明细表/正文里**已取得**的数据，核对表却写「未取得」：
  · 疑点1：明细表逐笔列着「红字发票信息确认单编号」（13 行），核对表第 4 条写
    「未单独核对（独立数据源本轮未取得）」。
  · 疑点7/8/13：正文用「销项发票金额」「实缴增值税 205,744.69 元」「命中技术服务费」
    得出前提条结论，同一行的「数据源状态」列却写「须核对」—— 同一行自相矛盾。

## 根因（实测量化）
要件声明的「独立数据源」是**多源组合串**，旧实现把它当**一份材料**整体匹配
⇒ 有一个源缺，**已取得的源被一起否定**。实测全量产物 **65 条要件行中 26 条**命中该形态。

## 修法（单一权威 + 逐源判定 + 同源落盘）
`engine/data_source_status.py`（唯一权威）：
`split_sources` → `status_of`（逐源）→ `combine`（合成）→ `source_status_map`（唯一取数）
→ `table_from`（规格【输出】字段）；要件核对表由 `constituent_checkpoint` **改薄转发**到它。
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REPORT = ROOT / "scripts" / "four_reports" / "company_1_full.json"
#: 本企业本轮已取得资料（取自产物 `comprehensive.data_overview.present`）
AVAIL = ["银行流水", "增值税申报表", "科目余额表", "记账凭证", "工资表",
         "销项发票", "进项发票", "社保明细", "进项抵扣", "公积金缴存"]
#: 用户点名疑点 → 红线编号（实测产物 seq 映射）
SAMPLES = {1: "RL-VAT-007", 7: "RL-OTH-001", 8: "RL-OTH-003", 13: "RL-SPT-006"}


class TestUnitPerSource:
    def test_detail_evidence_makes_source_available(self):
        """疑点1：明细表里有「红字发票信息确认单编号」⇒ 该数据源必须是「已有」。"""
        from engine.data_source_status import status_of, STATUS_HAVE
        detail = ("红冲/作废发票情形（共13笔） 发票号25952000000096267625 销项发票 "
                  "红冲 被红冲蓝字数电发票号码：25952000000096798612 "
                  "红字发票信息确认单编号：44030725051001117191")
        d = status_of("红字发票信息确认单", available=AVAIL, detail=detail)
        assert d["status"] == STATUS_HAVE, d
        assert "明细表" in d["reason"], d["reason"]

    def test_group_partial_names_what_is_missing(self):
        """疑点7：组内已取得「销项发票」⇒ 文案必须**逐源点名**，不得笼统说"未取得"。"""
        from engine.data_source_status import resolve_group, STATUS_NEED
        g = resolve_group("合同台账、销项发票", available=AVAIL)
        assert g["status"] == STATUS_NEED, g
        assert "已取得：销项发票" in g["reason"], g["reason"]
        assert "尚未取得：合同台账" in g["reason"], g["reason"]
        assert g["provided"] is False, "缺一项即不得判「已取得」（要件须全部数据源都取到）"

    def test_group_all_missing_says_all_missing(self):
        """全部源都是「本轮未提供」⇒ 组合状态=缺失，文案写"均未提供"。

        ★ 措辞口径（Skill 7 修订）：**「缺失」＝本轮未提供**；若缺的源属「须核对」
          （有关联类别、须人工确认），组合状态必须是**须核对**——把它们一并说成"缺失"
          等于说重了（企业会以为自己没交资料）。
        """
        from engine.data_source_status import resolve_group, STATUS_MISSING
        g = resolve_group("退货单、折让协议、拒收证明", available=AVAIL)
        assert g["status"] == STATUS_MISSING, g
        assert "均未提供" in g["reason"], g["reason"]

    def test_premise_conclusion_keeps_authority_status(self):
        """疑点8：前提条的**状态列必须取唯一权威** —— 不得因"现象已检出"就无据写成「已有」。

        ★★ 2026-10-09（根因修复）：旧断言是 `数据源状态 == "已有"`，即"前提条一律登记为已有"。
          该写法是**无据改写**，实测造成两类真实缺陷：
            ① 与本项「数据源状态表」（按同一权威 `resolve_group` 逐源判定）**打架**
               —— 表说「须核对/缺失」、核对表说「已有」；
            ② 该无据的「已有」令审计闸门把"补充提供「X」"误判成
               "X 已判已有却又要补"（seq=16 实测 ERROR）。
          现口径：结论仍是「符合情形」（现象/前提条，存在即成立），
          **状态列如实取 `resolve_group` 的合成结论**；声明源未取得时在**依据**里逐源点名。
        """
        from engine.constituent_checkpoint import build_constituent_checkpoints
        from engine.data_source_status import resolve_group
        s = {"redline_id": "RL-OTH-003",
             "constituents": ["附加税费计税依据与同期实际缴纳的增值税、消费税存在差异"],
             "constituent_sources": ["增值税申报表、附加税费申报表"],
             "evidence_chain": {"available_materials": AVAIL, "elements": []},
             "clue_chain": {"nodes": []}, "argumentation": {"constituent_hits": []}}
        cps = build_constituent_checkpoints(s)
        assert cps, "要件核对必须有结果"
        c = cps[0]
        assert "符合情形" in str(c.get("核对结论") or ""), c
        # 状态列 == 唯一权威对**声明源**的合成结论（不得凭空改写）
        exp = resolve_group("增值税申报表、附加税费申报表", available=AVAIL, detail="")["status"]
        assert str(c.get("数据源状态")) == exp, (c, exp)
        if exp != "已有":
            # 声明源未取得时，依据必须点名（不静默、不掩盖）
            assert "声明的独立数据源" in str(c.get("依据") or ""), c

    def test_rule_source_is_known_but_partial(self):
        """疑点13：声明源（境外付款台账/对外付汇凭证）本轮未取得 ⇒ 判「须核对」。

        为什么是「须核对」而不是「缺失」：`evidence_chain._match_material` 认定
        已提供的**银行流水**与本项属**类别相关**（境外付款会走银行），须人工确认是否含本项内容。
        口径：**不逐字覆盖但有相关类别 ⇒ 须核对**（禁止当作"已有"）。
        """
        from engine.data_source_status import status_of, resolve_group, STATUS_NEED, STATUS_HAVE
        d = status_of("境外付款台账", available=AVAIL)
        assert d["status"] != STATUS_HAVE, d
        assert d["status"] == STATUS_NEED, d
        g = resolve_group("境外付款台账、对外付汇凭证", available=AVAIL)
        assert g["status"] == STATUS_NEED and g["provided"] is False, g
        # 文案必须逐源点名（不得说"均未取得"——它们不是"未提供"，而是"须确认"）
        assert "尚未取得" in g["reason"] or "须" in g["reason"], g["reason"]


class TestRootCauseGuards:
    def test_split_does_not_break_source_name_with_separator(self):
        """「合同或协议」本身就是一个数据源名 ⇒ 不得按「或」切坏。

        实测：粗暴切分得到「合同」「协议」，前者还被别名归一到「合同文件」
        ⇒ 报告里凭空多出一个"未取得的数据源"。
        """
        from engine.data_source_status import split_sources
        assert split_sources("合同或协议、境外付款台账") == ["合同或协议", "境外付款台账"]
        assert split_sources("合同或协议") == ["合同或协议"]
        assert split_sources("销项发票、进项发票") == ["销项发票", "进项发票"]

    def test_detail_text_excludes_checklist_itself(self):
        """自引用屏障：要件核对表**不能**当"明细表证据"（否则数据源自己证明自己已取得）。

        实测首版：疑点1 第3条「退货单、折让协议、拒收证明」被判「已有」——
        因为核对表里就写着这几个名字，而它们本轮**根本没提供**。
        """
        from engine.data_source_status import detail_text
        prob = {"narrative_paragraphs": [
            {"detail_tables": [
                {"title": "构成要件独立核对表（每要件独立数据源与独立结论）",
                 "columns": ["要件序号", "独立数据源"],
                 "rows": [{"独立数据源": "退货单、折让协议、拒收证明"}]},
                {"title": "红冲/作废发票情形（共13笔）", "columns": ["说明"],
                 "rows": [{"说明": "红字发票信息确认单编号：44030725051001117191"}]},
            ]}]}
        dt = detail_text(prob)
        assert "红字发票信息确认单编号" in dt
        assert "退货单" not in dt, "核对表被当成了明细表证据（自引用）"

    def test_spreadsheet_placeholder_is_not_marker(self):
        """反向护栏：别名/专有标识必须是**能证实**的，不得用泛词（否则满篇假"已有"）。"""
        from engine.data_source_status import entry_of
        e = entry_of("红字发票信息确认单") or {}
        assert "红字发票信息确认单编号" in (e.get("markers") or [])
        for loose in ("发票", "蓝字发票", "合同"):
            assert loose not in (e.get("markers") or []), loose


class TestIntegrationUserSamples:
    @staticmethod
    def _problems():
        rep = json.loads(REPORT.read_text(encoding="utf-8"))
        er = rep.get("enterprise_readable_report") or rep
        return [p for p in (er.get("confirmed_problems") or []) if isinstance(p, dict)]

    def test_every_problem_with_checklist_has_status_table(self):
        """集成：有要件核对表的疑点必须落「数据源状态表」（规格【输出】字段齐全）。"""
        need = ("data_source_id", "data_source_name", "status_in_detail",
                "status_in_checklist", "consistency", "conflict_reason")
        n = 0
        for p in self._problems():
            rows = [r for np_ in (p.get("narrative_paragraphs") or []) if isinstance(np_, dict)
                    for t in (np_.get("detail_tables") or [])
                    if "构成要件独立核对表" in str((t or {}).get("title") or "")
                    for r in (t.get("rows") or []) if isinstance(r, dict)]
            if not rows:
                continue
            n += 1
            tbl = p.get("data_source_status")
            assert isinstance(tbl, list) and tbl, (p.get("seq"), "缺数据源状态表")
            for row in tbl:
                for f in need:
                    assert f in row, (p.get("seq"), f)
                assert row.get("consistency") is not False or not str(
                    row.get("conflict_reason") or "").strip(), (p.get("seq"), row)
        assert n >= 6, "用例失效：产物里带要件核对表的疑点太少（%d）" % n

    def test_no_flat_denial_when_source_available(self):
        """全文核心断言：**明细表已列示的数据源，不得被整体否定**。"""
        bad = []
        for p in self._problems():
            tbl = [r for r in (p.get("data_source_status") or []) if isinstance(r, dict)]
            have = {str(r.get("data_source_name")) for r in tbl
                    if r.get("status_in_detail") == "已有"}
            if not have:
                continue
            for np_ in (p.get("narrative_paragraphs") or []):
                for t in (np_.get("detail_tables") or []):
                    if "构成要件独立核对表" not in str((t or {}).get("title") or ""):
                        continue
                    for r in (t.get("rows") or []):
                        if not isinstance(r, dict):
                            continue
                        src = str(r.get("独立数据源") or "")
                        cc = str(r.get("核对结论") or "")
                        if not src:
                            continue
                        from engine.data_source_status import split_sources, canonical_name
                        hit = {canonical_name(x) for x in split_sources(src)} & have
                        if hit and any(k in cc for k in ("独立数据源本轮未取得", "均未取得")):
                            bad.append((p.get("seq"), r.get("要件序号"),
                                        "、".join(sorted(hit)), cc[:30]))
        assert bad == [], "仍存在「数据已取得却写未取得」：%s" % bad[:5]

    def test_sample_problems_status_matches_checklist(self):
        """四个样例：要件行的「数据源状态」必须等于**该组各源状态合成**的结果（同源）。

        ★ 口径（重要）：`data_source_status` 表记的是**逐源**状态；要件核对表记的是
          **该要件整组**的合成状态 ⇒ 二者用 `combine()` 对齐，而非逐个相等。

        ★★ 2026-10-09（根因）：**删除了原「前提条行除外」的豁免**。该豁免写的是
          "前提条的状态按显式口径登记为「已有」，属有意覆盖，不得用合成规则去比" ——
          正是这条豁免**掩盖了真实缺陷**：前提条被无据改写成「已有」，而"现象由触发信号检出"
          与"本要件声明的独立数据源已取得"是两件事。实测全量产物 12 条前提条中 6 条如此，
          造成同页矛盾（状态表说缺失、核对表说已有），并使审计闸门误报"已有又要补"。
          现前提条也**必须**等于 `combine()` ⇒ 本用例成为该缺陷的**行为级回归锁**。
        """
        from engine.data_source_status import split_sources, canonical_name, combine
        want = set(SAMPLES.values())
        seen = set()
        for p in self._problems():
            rid = str(p.get("redline_id") or "")
            if rid not in want:
                continue
            seen.add(rid)
            per = {str(r.get("data_source_name")): r
                   for r in (p.get("data_source_status") or []) if isinstance(r, dict)}
            for np_ in (p.get("narrative_paragraphs") or []):
                for t in (np_.get("detail_tables") or []):
                    if "构成要件独立核对表" not in str((t or {}).get("title") or ""):
                        continue
                    for r in (t.get("rows") or []):
                        if not isinstance(r, dict):
                            continue
                        items = []
                        for nm in split_sources(r.get("独立数据源")):
                            nm = canonical_name(nm)
                            row = per.get(nm)
                            if row is None:
                                continue
                            items.append({"name": nm,
                                          "status": str(row.get("status_in_checklist") or "")})
                        if not items:
                            continue
                        exp = combine(items)["status"]
                        assert exp == str(r.get("数据源状态")), \
                            (rid, r.get("要件序号"), exp, r.get("数据源状态"))
        assert seen == want, "样例疑点未在产物中出现：%s" % sorted(want - seen)

    def test_sample1_confirmation_note_is_available(self):
        """疑点1（用户第 1 条验收）：确认单编号已取得 ⇒ 状态表里该源必须是「已有」。"""
        p = [x for x in self._problems() if x.get("redline_id") == "RL-VAT-007"][0]
        tbl = {str(r.get("data_source_name")): r for r in (p.get("data_source_status") or [])}
        row = tbl.get("红字发票信息确认单")
        assert row, "状态表里找不到「红字发票信息确认单」"
        assert row["status_in_detail"] == "已有", row
        assert row["status_in_checklist"] == "已有", row


class TestGateReverseValidation:
    def test_gate_flags_conflict(self, monkeypatch):
        """反向验证：明细表已列示却判「缺失」⇒ 门禁必须报红（否则判据是假的）。"""
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {"confirmed_problems": [{
            "redline_id": "RL-ZZZ-999", "title": "反向验证用疑点",
            "narrative_paragraphs": [{"detail_tables": [
                {"title": "构成要件独立核对表（每要件独立数据源与独立结论）",
                 "rows": [{"要件序号": "第1条", "独立数据源": "红字发票信息确认单、销项发票",
                           "数据源状态": "缺失", "核对结论": "未单独核对（独立数据源本轮未取得）"}]}]}],
            "data_source_status": [{
                "data_source_id": "DS_1", "data_source_name": "红字发票信息确认单",
                "status_in_detail": "已有", "status_in_checklist": "缺失",
                "consistency": True, "conflict_reason": ""}]}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_data_source_status_consistency() if i[0] == "ERROR"]
        assert errs, "门禁未报红：反向验证失败"
        assert any("已取得却写未取得" in i[2] or "组内已取得" in i[2] for i in errs), errs[:3]

    def test_gate_flags_missing_table(self, monkeypatch):
        import tools.audit_consistency as A
        fake = {"enterprise_readable_report": {"confirmed_problems": [{
            "redline_id": "RL-ZZZ-999", "title": "反向验证用疑点",
            "narrative_paragraphs": [{"detail_tables": [
                {"title": "构成要件独立核对表（每要件独立数据源与独立结论）",
                 "rows": [{"要件序号": "第1条", "独立数据源": "销项发票"}]}]}]}]}}
        monkeypatch.setattr(A, "_canonical_report", lambda: fake)
        errs = [i for i in A.check_data_source_status_consistency() if i[0] == "ERROR"]
        assert any("数据源状态表" in i[2] for i in errs), errs[:3]

    def test_gate_passes_on_real_product(self):
        from tools.audit_consistency import check_data_source_status_consistency
        errs = [i for i in check_data_source_status_consistency() if i[0] == "ERROR"]
        assert errs == [], errs[:5]
