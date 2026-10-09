# -*- coding: utf-8 -*-
"""文档一致性 5 个 Skill（D1~D5）—— 单元 / 失败样例 / 通过样例 / 反向验证。

用户要求：每个 Skill 必须 **用本次 11 处问题做失败样例** + 修复后做通过样例 + 反向验证
（构造不一致 ⇒ 必须报错）。

11 处问题的归属：
  · 5 处数字错（25 例 / 25 passed、1421、55.94s、445 条、前提条数遗漏）→ **D1**（并由 **D3** 查残留）
  · 1 处规则未同步（TDS-⑨ 未进 02 规则清单 + "8 条规则"）→ **D2**
  · 1 处旧 grep 漏写法（只搜"25 例"，漏"25 passed"）→ **D3**
  · 1 处状态未同步（U1 挂"未完成"而补做已记"已修复"）→ **D4**
  · 1 处跨文件不一致（最小检查集 28 例 vs 01 写 25）→ **D5**
  · 2 处系统 bug（综合疑点要件数=0、门禁缺"配置有产物必须有"判据）→ 已在 Skill-1 主体修复，见 `第1批诊断报告.md`
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DOCDIR = ROOT / "docs" / "第01批_触发条件与认定要件分离"


def _gate_call_line_authority() -> int:
    """**动态**取「门禁调用行号」权威值。

    ★ 2026-10-08（本项目铁律「闸门不得硬编码某一条具体对象做样检」）：
      反向验证用例原先把「第 **11200** 行」写死成变异锚点 ⇒ 只要闸门文件新增/删改一行，
      锚点就失配、用例自己报「变异锚点未命中」（本次即因此失败 2 例）。
      改为**现算**：与 D1 登记的权威口径同源（`+ check_trigger_determination_separation()`）。
    """
    src = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
    for i, line in enumerate(src.splitlines(), 1):
        if "+ check_trigger_determination_separation()" in line:
            return i
    raise AssertionError("未在 tools/audit_consistency.py 找到门禁调用行")



def _backup() -> dict:
    """备份将被反向验证修改的文件（测后必须还原，否则污染交付物）。"""
    return {p.name: p.read_text(encoding="utf-8") for p in DOCDIR.glob("*.md")}


def _restore(snap: dict) -> None:
    for name, text in snap.items():
        (DOCDIR / name).write_text(text, encoding="utf-8")


class TestD1NumberAuthority:
    """D1 文档数字一致性。"""

    @pytest.mark.plain
    def test_pass_real_docs(self):
        from engine.doc_number_authority import audit
        errs = [i for i in audit() if i["level"] == "ERROR"]
        assert errs == [], errs[:3]

    @pytest.mark.plain
    def test_authority_values_are_computed(self):
        """权威值必须**现算**（不是缓存/手抄）：与直接读配置的结果一致。"""
        import engine.doc_consistency_core as C
        cfg = json.loads((ROOT / "config" / "risk_conditions.json").read_text(encoding="utf-8"))
        v, why = C.authority_value({"kind": "config_count",
                                    "path": "config/risk_conditions.json",
                                    "expr": "len:risks"})
        assert v == len(cfg["risks"]), (v, why)

    @pytest.mark.reverse
    def test_reverse_wrong_number_is_detected(self):
        """反向验证：把文档里的数字改错 ⇒ 门禁必须变红（否则判据是假的）。"""
        snap = _backup()
        try:
            f = DOCDIR / "最小检查集.md"
            f.write_text(f.read_text(encoding="utf-8").replace("| 前提条数 | **69**", "| 前提条数 | **68**"),
                         encoding="utf-8")
            from engine.doc_number_authority import audit
            errs = [i for i in audit() if i["level"] == "ERROR"]
            assert any("前提条" in i["detail"] and "68" in i["detail"] for i in errs), errs[:3]
        finally:
            _restore(snap)


class TestD2RuleReferenceSync:
    """D2 规则引用一致性。"""

    @pytest.mark.plain
    def test_pass_real_docs(self):
        from engine.rule_reference_sync import audit
        assert [i for i in audit() if i["level"] == "ERROR"] == []

    @pytest.mark.reverse
    def test_reverse_missing_new_rule_is_detected(self):
        """反向验证：新增一条规则但不更新引用处 ⇒ 必须报错（用户样例：TDS-⑨ 未进 02）。"""
        snap = _backup()
        cfgp = ROOT / "config" / "doc_consistency.json"
        cfg_snap = cfgp.read_text(encoding="utf-8")
        try:
            cfg = json.loads(cfg_snap)
            cfg["rule_catalog"].append({"id": "TDS-⑩", "desc": "测试用新规则"})
            cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
            import engine.doc_consistency_core as C
            C.reload_config()
            from engine.rule_reference_sync import audit
            errs = [i for i in audit() if i["level"] == "ERROR"]
            assert any("TDS-⑩" in i["detail"] for i in errs), errs[:3]
        finally:
            cfgp.write_text(cfg_snap, encoding="utf-8")
            import engine.doc_consistency_core as C
            C.reload_config()
            _restore(snap)

    @pytest.mark.reverse
    def test_reverse_unknown_rule_id_is_detected(self):
        """反向验证：文档引用一个**不存在**的编号 ⇒ 必须报错。"""
        snap = _backup()
        try:
            f = DOCDIR / "最小检查集.md"
            f.write_text(f.read_text(encoding="utf-8") + "\n引用一条不存在的规则 TDS-⑩。\n",
                         encoding="utf-8")
            from engine.rule_reference_sync import audit
            errs = [i for i in audit() if i["level"] == "ERROR"]
            assert any("TDS-⑩" in i["detail"] for i in errs), errs[:3]
        finally:
            _restore(snap)

    @pytest.mark.plain
    def test_collective_rule_reference_is_valid(self):
        """口径：`TDS-⑤⑥⑦⑧` 是集合引用（逐字符校验），**不得**误判为不存在。"""
        from engine.doc_consistency_core import config
        pat = config().get("rule_id_pattern")
        assert pat, "规则编号正则未登记"


class TestD3ResidueScan:
    """D3 全文残留校验（同义写法词典）。"""

    @pytest.mark.plain
    def test_pass_real_docs(self):
        from engine.doc_residue_scan import audit
        assert [i for i in audit() if i["level"] == "ERROR"] == []

    @pytest.mark.plain
    def test_grep_is_expanded_from_dictionary(self):
        """输出要求：必须给出**展开同义写法**后的 grep 命令。"""
        from engine.doc_residue_scan import expand_grep
        cmd = expand_grep("SV-testcount-25")
        for v in ("25 例", "25 passed", "25tests", "25 用例"):
            assert v in cmd, (v, cmd)

    @pytest.mark.reverse
    def test_reverse_unlisted_variant_is_reported(self):
        """反向验证：构造一种**词典未收录**的写法 ⇒ 必须报出来（提示补词典/属校验漏洞）。"""
        snap = _backup()
        cfgp = ROOT / "config" / "doc_synonyms.json"
        cfg_snap = cfgp.read_text(encoding="utf-8")
        try:
            f = DOCDIR / "最小检查集.md"
            f.write_text(f.read_text(encoding="utf-8") + "\n（历史遗留：当时是 1421 通过。）\n",
                         encoding="utf-8")
            from engine.doc_residue_scan import audit
            errs = [i for i in audit() if i["level"] == "ERROR"]
            assert any("1421" in i["detail"] for i in errs), errs[:3]
        finally:
            cfgp.write_text(cfg_snap, encoding="utf-8")
            _restore(snap)

    @pytest.mark.plain
    def test_range_form_is_not_residue(self):
        """口径：区间形态（「55.94–86.36s」）**不算残留**（否则把合规的浮动区间判成错误）。"""
        from engine.doc_consistency_core import check_residue
        assert [i for i in check_residue() if i["level"] == "ERROR"] == []


class TestD4TodoStatusSync:
    """D4 未完成事项状态同步。"""

    @pytest.mark.plain
    def test_pass_real_docs(self):
        from engine.todo_status_sync import audit
        assert [i for i in audit() if i["level"] == "ERROR"] == []

    @pytest.mark.plain
    def test_every_todo_has_status(self):
        """每项必须有状态字段（用户样例：U1 曾挂"未完成"却已修复）。"""
        from engine.todo_status_sync import core
        todos = core.parse_todo_table()
        assert todos, "未解析到 U1..Un"
        for tid, info in todos.items():
            assert info["状态"], (tid, info)

    @pytest.mark.plain
    def test_u1_is_marked_fixed(self):
        """本次 11 处问题的修复必须落到状态上：U1（综合疑点要件数=0 的 bug）＝ 已修复。"""
        from engine.todo_status_sync import core
        assert (core.parse_todo_table().get("U1") or {}).get("状态") == "已修复"

    @pytest.mark.reverse
    def test_reverse_status_conflict_is_detected(self):
        """反向验证：补做记录写「已修复」但不更新 U1 状态 ⇒ 必须报错。"""
        snap = _backup()
        try:
            f = DOCDIR / "08_未完成事项清单.md"
            t = f.read_text(encoding="utf-8")
            t = t.replace("| **U1** | **已修复** |", "| **U1** | **不阻断** |")
            f.write_text(t + "\n（补做记录：U1 已修复。）\n", encoding="utf-8")
            from engine.todo_status_sync import audit
            errs = [i for i in audit() if i["level"] == "ERROR"]
            assert any("U1" in i["detail"] for i in errs), errs[:3]
        finally:
            _restore(snap)


class TestD5RefGraph:
    """D5 跨文件引用一致性。"""

    @pytest.mark.plain
    def test_pass_real_docs(self):
        from engine.doc_ref_graph import audit
        assert [i for i in audit() if i["level"] == "ERROR"] == []

    @pytest.mark.plain
    def test_affected_downstream(self):
        """能力：上游变更 → 受影响下游清单。"""
        from engine.doc_ref_graph import affected_downstream
        assert "最小检查集.md" in affected_downstream("01_Skill设计文档.md")

    @pytest.mark.reverse
    def test_reverse_downstream_not_updated_is_detected(self):
        """反向验证：改上游（改坏下游数字）但不更新下游 ⇒ 必须报错。"""
        snap = _backup()
        try:
            f = DOCDIR / "最小检查集.md"
            t = f.read_text(encoding="utf-8")
            t = t.replace("本 Skill 专项 | `pytest tests/test_trigger_determination_separation.py -q` → **28 tests**",
                          "本 Skill 专项 | `pytest tests/test_trigger_determination_separation.py -q` → **25 tests**")
            f.write_text(t, encoding="utf-8")
            from engine.doc_ref_graph import audit
            from engine.doc_number_authority import audit as dn
            # 下游值改错 ⇒ D1（值比对）或 D5（未命中）至少一处必须报红
            errs = [i for i in (audit() + dn()) if i["level"] == "ERROR"]
            assert errs, "下游被改坏却无人报错"
        finally:
            _restore(snap)


class TestRegistrationAndWiring:
    """落地验收 1/2：写入系统配置 + 增加质量门禁。"""

    IDS = ("doc_number_authority", "rule_reference_sync", "doc_residue_scan",
           "todo_status_sync", "doc_ref_graph")

    @pytest.mark.plain
    def test_registered_in_skill_specs(self):
        specs = json.loads((ROOT / "config" / "skill_specs.json").read_text(encoding="utf-8"))
        ids = {s.get("id") for s in specs["skills"]}
        for i in self.IDS:
            assert i in ids, i

    @pytest.mark.plain
    def test_registry_validate_clean(self):
        from engine import skill_registry as SR
        assert SR.validate() == []

    @pytest.mark.plain
    def test_gates_wired_into_chain(self):
        src = (ROOT / "tools" / "audit_consistency.py").read_text(encoding="utf-8")
        for fn in ("check_doc_number_authority", "check_rule_reference_sync",
                   "check_doc_residue_scan", "check_todo_status_sync", "check_doc_ref_graph"):
            assert ("+ %s()" % fn) in src, "%s 未并入总链" % fn

    @pytest.mark.plain
    def test_all_five_gates_zero_error(self):
        import tools.audit_consistency as A
        for fn in (A.check_doc_number_authority, A.check_rule_reference_sync,
                   A.check_doc_residue_scan, A.check_todo_status_sync, A.check_doc_ref_graph):
            iss = fn()
            errs = [i for i in iss if i[0] == "ERROR"]
            assert errs == [], (fn.__name__, errs[:3])


class TestConfigHealthGate:
    """**数据表健康闸门**：表读不出来 / 缺必需键 ⇒ ERROR（**不得静默通过 = 假绿**）。

    实测事故（本批收口时真实发生）：`config/doc_consistency.json` 因**一处半角引号**导致 JSON 非法
    ⇒ 核心 `_load()` 返回 `{}` ⇒ 5 个门禁**全部报"0 项问题"**（假绿，且 5 个 Skill 的通过样例
    也会一起假通过）。故：**判据的第一条必须是"表能用"**，并**反向验证**（break ⇒ 必须变红）。
    """

    def _check_all(self):
        from engine import (doc_number_authority as D1, rule_reference_sync as D2,
                            doc_residue_scan as D3, todo_status_sync as D4,
                            doc_ref_graph as D5, doc_consistency_core as core)
        core.reload_config()
        out = {n: m.audit() for n, m in (("D1", D1), ("D2", D2), ("D3", D3),
                                         ("D4", D4), ("D5", D5))}
        core.reload_config()
        return out

    @pytest.mark.reverse
    def test_reverse_broken_json_turns_gates_red(self, tmp_path, monkeypatch):
        """**反向**：数据表 JSON 非法 ⇒ D1/D2/D4/D5 必须报 ERROR（D3 用另一张表，不受影响）。"""
        from engine import doc_consistency_core as core
        bad = tmp_path / "doc_consistency.json"
        bad.write_text('{"schema": 1, "numbers": [ {id: "x"} ]}', encoding="utf-8")   # 非法 JSON
        monkeypatch.setattr(core, "_CFG", bad)
        out = self._check_all()
        for k in ("D1", "D2", "D4", "D5"):
            assert any(i["level"] == "ERROR" for i in out[k]), (k, out[k][:2])
        monkeypatch.undo()
        core.reload_config()

    @pytest.mark.reverse
    def test_reverse_missing_key_turns_gates_red(self, tmp_path, monkeypatch):
        """**反向**：JSON 合法但缺必需键（空表）⇒ 必须报 ERROR，而不是"没有数字可查 = 通过"。"""
        from engine import doc_consistency_core as core
        empty = tmp_path / "empty.json"
        empty.write_text('{"schema": 1}', encoding="utf-8")
        monkeypatch.setattr(core, "_CFG", empty)
        out = self._check_all()
        for k in ("D1", "D2", "D4", "D5"):
            assert any(i["level"] == "ERROR" for i in out[k]), (k, out[k][:2])
        monkeypatch.undo()
        core.reload_config()

    @pytest.mark.reverse
    def test_reverse_broken_synonyms_turns_d3_red(self, tmp_path, monkeypatch):
        """**反向**：同义词典缺 `stale_values` ⇒ D3 必须报 ERROR。"""
        from engine import doc_consistency_core as core
        empty = tmp_path / "syn.json"
        empty.write_text('{"schema": 1, "scan_scope": {"include_globs": []}}', encoding="utf-8")
        monkeypatch.setattr(core, "_SYN", empty)
        out = self._check_all()
        assert any(i["level"] == "ERROR" for i in out["D3"]), out["D3"][:2]
        monkeypatch.undo()
        core.reload_config()

    @pytest.mark.plain
    def test_health_gate_present_in_source(self):
        """判据可自证存在（防止有人日后把健康闸门删掉）。"""
        src = (ROOT / "engine" / "doc_consistency_core.py").read_text(encoding="utf-8")
        assert "def _guard(" in src
        assert src.count("_guard(_CFG") >= 4, "五个 Skill 的判据必须都先过健康闸门"
        assert src.count("_guard(_SYN") >= 1


class TestNewJudgments:
    """本轮新增的 3 条判据（各配**可复现**的反向验证：改真文件 → 跑 → 还原）。

    为什么必须新增（本轮实测出的**判据缺口**）：
      · 「分项加总 31 而合计 28」—— 只抓单值的正则抓不到"文档自相矛盾"；
      · 「门禁行号 11123」—— 行号类数字此前**没有权威源**，只能靠人核；
      · 「U1 状态」—— 初版声明抽取扫全文 ⇒ **我自己的解释性散文**被当成"补做记录声明"（自造假红）。
    """

    F01 = "01_Skill设计文档.md"
    F08 = "08_未完成事项清单.md"
    F02 = "02_系统配置变更清单.md"

    @pytest.mark.breaking
    def test_sum_check_catches_inconsistent_total(self):
        """**反向**：把 `01` §6 的分项改成加总 31 ⇒ D1 必须报「分项加总 ≠ 合计」。"""
        from engine import doc_number_authority as D1
        p = DOCDIR / self.F01
        snap = p.read_text(encoding="utf-8")
        try:
            p.write_text(snap.replace("分项 10 + 7 + 3 + 3 + 2 + 3 = 28",
                                      "分项 10 + 7 + 3 + 3 + 2 + 6 = 31", 1), encoding="utf-8")
            errs = [i for i in D1.audit() if i["level"] == "ERROR"]
            assert any("分项加总" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D1.audit() if i["level"] == "ERROR"]

    @pytest.mark.plain
    def test_line_number_authority_comes_from_grep(self):
        """行号类数字的权威 = `grep -n` 实测（不靠人核）。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        val, why = core.authority_value({
            "kind": "grep_line", "path": "tools/audit_consistency.py",
            "pattern": "^def check_trigger_determination_separation"})
        assert isinstance(val, int) and val > 0, why
        assert "grep -n" in why

    @pytest.mark.reverse
    def test_reverse_wrong_line_number_is_detected(self):
        """**反向**：把 `02` 的门禁调用行号改成失真的值 ⇒ D1 必须报红。

        ★ 2026-10-08：变异锚点**动态取权威值**（原先写死 11200，闸门一行号位移用例即腐化）。
        """
        from engine import doc_number_authority as D1
        cur = _gate_call_line_authority()
        p = DOCDIR / self.F02
        snap = p.read_text(encoding="utf-8")
        old = "第 **%d** 行 `run_checks()` 总链" % cur
        try:
            got = snap.replace(old, "第 **%d** 行 `run_checks()` 总链" % (cur + 7), 1)
            assert got != snap, "变异锚点未命中：%s" % old
            p.write_text(got, encoding="utf-8")
            errs = [i for i in D1.audit() if i["level"] == "ERROR"]
            assert any("行号" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D1.audit() if i["level"] == "ERROR"]

    @pytest.mark.breaking
    def test_todo_declaration_must_carry_marker(self):
        """**反向**：删掉「状态同步声明」标记行 ⇒ D4 必须报「判据无法执行」。"""
        from engine import todo_status_sync as D4
        p = DOCDIR / self.F08
        snap = p.read_text(encoding="utf-8")
        try:
            p.write_text(snap.replace("**状态同步声明**", "**同步说明**", 1), encoding="utf-8")
            errs = [i for i in D4.audit() if i["level"] == "ERROR"]
            assert any("状态同步声明" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D4.audit() if i["level"] == "ERROR"]

    @pytest.mark.lock
    def test_prose_is_not_treated_as_declaration(self):
        """口径：**解释性散文不得被当成"补做记录声明"**（初版自造假红的根因）。"""
        from engine import todo_status_sync as D4
        p = DOCDIR / self.F08
        snap = p.read_text(encoding="utf-8")
        try:
            p.write_text(snap + "\n> 举例：假如把 U1 的状态改成「未开始」会怎样？\n", encoding="utf-8")
            errs = [i for i in D4.audit() if i["level"] == "ERROR"]
            assert errs == [], errs[:2]
        finally:
            p.write_text(snap, encoding="utf-8")

    @pytest.mark.lock
    def test_residue_outside_fence_still_red(self):
        """**口径锁**：围栏代码块（```…```）内的旧值算**引用**（允许）；**围栏外**必须报红。

        为什么需要这条：交付物必须贴「依据命令 + 实测输出」，而实测输出可能逐字含旧值
        （如展开式 `grep -rnE "(25 例|25 passed|…)"`）。**若不放开围栏 ⇒ 必然假红；
        若放开却不锁 ⇒ 会变成"把旧值塞进代码块就过关"的漏洞。**
        """
        from engine import doc_residue_scan as D3
        p = DOCDIR / "05_回归测试报告.md"
        snap = p.read_text(encoding="utf-8")
        try:
            p.write_text(snap + "\n正文直接写旧值：1421 passed。\n", encoding="utf-8")
            errs = [i for i in D3.audit() if i["level"] == "ERROR"]
            assert any("1421" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        try:
            p.write_text(snap + "\n```\n1421 passed\n```\n", encoding="utf-8")
            errs = [i for i in D3.audit() if i["level"] == "ERROR"]
            assert errs == [], errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D3.audit() if i["level"] == "ERROR"]


class TestFinalRoundJudgments:
    """最终修正轮新增的 4 类判据（缺口 A / A′ / B / C），每条都配**可复现**反向验证。

    诊断结论（见 `5个Skill判据缺口诊断报告.md`）：7 处不一致之所以没被抓，
    不是判据写错，而是**判据的存在范围 < 指标的出现范围**：
      · A  权威未登记（全量 passed / Skill 总数）；
      · A′ 不该用数值权威的指标缺"自洽"判据（耗时是易变值）；
      · B  权威已登记但 claims 覆盖不全（行号只接了 02，漏了 06/01）；
      · C  判据根本不存在（表格列数一致性）。
    """

    F01 = "01_Skill设计文档.md"
    F05 = "05_回归测试报告.md"
    F06 = "06_写入系统证据.md"
    F08 = "08_未完成事项清单.md"

    def _mutate(self, fname, old, new, gate, must_contain, extra_gate=None):
        """改真文件 → 跑门禁 → 还原（返回是否按预期报红）。"""
        from engine import doc_number_authority as D1, todo_status_sync as D4
        m = {"D1": D1, "D4": D4}
        p = DOCDIR / fname
        snap = p.read_text(encoding="utf-8")
        try:
            got = snap.replace(old, new, 1)
            assert got != snap, "变异锚点未命中：%s" % old[:40]
            p.write_text(got, encoding="utf-8")
            errs = [i for i in m[gate].audit() if i["level"] == "ERROR"]
            assert any(must_contain in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in m[gate].audit() if i["level"] == "ERROR"]

    # ---- 缺口 A：权威未登记 → 现已登记（pytest_receipt / json_len）----

    @pytest.mark.plain
    def test_receipt_authority_is_read_from_real_receipt(self):
        """全量 passed 的权威 = **最近一次全量运行的回执**（不是手抄、不是我在文档里写的数）。"""
        import json as _json
        from engine import doc_consistency_core as core
        rec_path = ROOT / "data" / "logs" / "pytest_last_run.json"
        assert rec_path.is_file(), "回执不存在 —— 先跑一次 `pytest tests/ -q`"
        rec = _json.loads(rec_path.read_text(encoding="utf-8"))
        core.reload_config()
        val, why = core.authority_value({"kind": "pytest_receipt", "field": "passed"})
        if val is not None:
            assert val == rec["passed"], (val, rec["passed"])
            assert "回执" in why
        else:
            # 口径：权威取不到时**必须说明原因**（回执过期 / 最近一次运行有失败），绝不静默。
            assert ("过期" in why) or ("失败" in why), why

    @pytest.mark.reverse
    def test_reverse_stale_receipt_is_rejected(self, tmp_path, monkeypatch):
        """**反向**：回执里的 `tests_max_mtime` 早于当前 tests/ ⇒ 权威取不到（"回执过期"），
        而**不是**静默用旧值。"""
        import json as _json
        from engine import doc_consistency_core as core
        fake = tmp_path / "receipt.json"
        fake.write_text(_json.dumps({"passed": 9999, "tests_max_mtime": 1.0,
                                     "finished_at": "1970-01-01 00:00:00",
                                     "command": "pytest tests/ -q"}), encoding="utf-8")
        monkeypatch.setattr(core, "_RECEIPT", fake)
        core.reload_config()
        val, why = core.authority_value({"kind": "pytest_receipt", "field": "passed"})
        assert val is None and "过期" in why, (val, why)
        monkeypatch.undo()
        core.reload_config()

    @pytest.mark.reverse
    def test_reverse_wrong_full_passed_is_detected(self):
        """**反向**：把 `05` §2 的 passed 改成别的数 ⇒ D1 必须报红。

        ⚠ **锚点必须从文件里现取**（不能硬编码 `1456`）：全量 passed 会随用例增减而变，
          硬编码会在下一次加测试时**静默失效**（锚点找不到 ⇒ 用例无效）。实测踩过。
        """
        import re
        cur = None
        for ln in (DOCDIR / self.F05).read_text(encoding="utf-8").split("\n"):
            m = re.match(r"\| passed \| \*{0,2}(\d+)\*{0,2} \|$", ln.strip())
            if m:
                cur = m.group(1)
                break
        assert cur, "未找到『| passed | **N** |』行 —— 文档结构变了"
        self._mutate(self.F05, "| passed | **%s** |" % cur, "| passed | **1424** |",
                     "D1", "全量回归 passed")

    @pytest.mark.reverse
    def test_reverse_wrong_skill_total_is_detected(self):
        """**反向**：把 `06` §1 的 Skill 总数改错 ⇒ D1 必须报红。"""
        self._mutate(self.F06, "| Skill 总数 | **62**", "| Skill 总数 | **55**",
                     "D1", "Skill 总数")

    # ---- 缺口 B：权威已登记但覆盖不全 → 现覆盖 02/06/01（+03 定义行）----

    @pytest.mark.reverse
    def test_reverse_wrong_gate_call_line_in_06_is_detected(self):
        """**反向**：`06 §4` 的调用行号改错 ⇒ D1 必须报红（此前 06 不在 claims 里）。

        ★ 2026-10-08：变异锚点动态取权威值（原先写死 11200 ⇒ 闸门行号位移后用例腐化）。
        """
        cur = _gate_call_line_authority()
        self._mutate(self.F06, "| 调用位置 | 第 **%d** 行" % cur,
                     "| 调用位置 | 第 **%d** 行" % (cur + 7),
                     "D1", "门禁调用行号")

    # ---- 缺口 A′：同文件内部自洽（耗时不设数值权威）----

    @pytest.mark.breaking
    def test_consistency_check_catches_intra_file_mismatch(self):
        """**反向**：`05` §2 的耗时与该文件文末的耗时不一致 ⇒ D1 必须报"同一文件内前后不一致"。"""
        import re
        from engine import doc_number_authority as D1
        p = DOCDIR / self.F05
        snap = p.read_text(encoding="utf-8")
        m = re.search(r"\| 耗时 \| \*{0,2}([\d.]+)s\*{0,2}", snap)
        assert m, "未找到『| 耗时 | **N.NNs**』行 —— 文档结构变了"
        cur = m.group(1)                        # ★ 同样**现取**，不硬编码（见上一个用例的说明）
        try:
            got = snap.replace("| 耗时 | **%ss**" % cur, "| 耗时 | **62.04s**", 1)
            assert got != snap
            p.write_text(got, encoding="utf-8")
            errs = [i for i in D1.audit() if i["level"] == "ERROR"]
            assert any("同一文件内前后不一致" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D1.audit() if i["level"] == "ERROR"]

    @pytest.mark.lock
    def test_duration_is_not_a_numeric_authority(self):
        """口径：耗时**不作为数值权威**（易变值 ⇒ 否则必然假红），而是"文件内自洽 + 注明同次运行"。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        ids = {n["id"] for n in core.config()["numbers"]}
        assert "full_pytest_duration" not in ids
        assert any(s["id"] == "CONS-05-duration" for s in core.config()["consistency_checks"])

    # ---- 缺口 C：表格列数一致性（判据原本不存在）----

    @pytest.mark.reverse
    def test_reverse_table_column_mismatch_is_detected(self):
        """**反向**：往 `08` 的表里**插一行列数不一致的行** ⇒ D4 必须报"表格列数与表头不一致"。

        ⚠ 必须**插进已有表格**（不能直接 append 到文件尾）：追加的行会自成一组（只有 1 行）
          ⇒ 不构成"表头 vs 数据行"的比较 ⇒ 用例会**空洞通过**（实测踩过）。
        """
        from engine import todo_status_sync as D4
        p = DOCDIR / self.F08
        snap = p.read_text(encoding="utf-8")
        lines = snap.split("\n")
        idx = next(i for i, ln in enumerate(lines) if ln.startswith("| **U6** |"))
        bad = lines[:idx + 1] + ["| **U99** | 不阻断 | 列数不一致的测试行 | **否** |"] + lines[idx + 1:]
        try:
            p.write_text("\n".join(bad), encoding="utf-8")
            errs = [i for i in D4.audit() if i["level"] == "ERROR"]
            assert any("表格列数与表头不一致" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D4.audit() if i["level"] == "ERROR"]

    @pytest.mark.lock
    def test_escaped_pipe_in_cell_is_not_a_column(self):
        """口径：单元格内的转义 `\\|` **不算列分隔**（否则含命令的单元格会把自己判成串列）。

        同样是**插进已有表格**（append 到文末会因"单行成组"而空洞通过）。
        """
        from engine import todo_status_sync as D4
        p = DOCDIR / self.F08
        snap = p.read_text(encoding="utf-8")
        lines = snap.split("\n")
        idx = next(i for i, ln in enumerate(lines) if ln.startswith("| **U6** |"))
        # 6 个单元格（与表头一致），第 3 格内含转义竖线
        row = "| **U98** | 不阻断 | 含转义竖线 \\| 的说明 | 原因 | 无 | 否 |"
        bad = lines[:idx + 1] + [row] + lines[idx + 1:]
        try:
            p.write_text("\n".join(bad), encoding="utf-8")
            errs = [i for i in D4.audit() if i["level"] == "ERROR"]
            assert errs == [], errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")

    # ---- 缺口 D：归属明确（D5 只管跨文件）----

    @pytest.mark.lock
    def test_d5_scope_is_cross_file_only(self):
        """口径：`d5_scope` 必须写清"同文件内部一致性不归 D5"。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        s = str(core.config().get("d5_scope") or "")
        assert "跨文件" in s and "不归 D5" in s


class TestUltimateRoundJudgments:
    """终极修正轮新增的判据：**元判据**（指标短语必须已登记）+ 2 种新 `authority.kind` + 四分类口径。

    诊断结论（见 `6处新不一致的判据缺口诊断报告.md`）：6 处里 **5 处**属同一病根 ——
    **"元事实"（关于事实的事实）从未被登记为权威**（权威有几条 / kind 有几种 / 判据有几条 /
    反向验证有几例 / 口径锁有几例）；另有 1 处是 **claims 正则只覆盖了"一种写法"**。
    """

    FA = "5个Skill设计文档.md"
    FV = "5个Skill验收自证.md"
    F05 = "05_回归测试报告.md"

    def _A(self, number_id):
        from engine import doc_consistency_core as core
        core.reload_config()
        for n in core.config()["numbers"]:
            if n["id"] == number_id:
                v, why = core.authority_value(n["authority"])
                assert v is not None, (number_id, why)
                return v
        raise KeyError(number_id)

    # ---- 元判据（D1-R9）----

    @pytest.mark.reverse
    def test_reverse_unregistered_indicator_phrase_is_flagged(self):
        """**反向**：在某份声明类文件里写一个**未被任何 claims 覆盖**的指标短语 ⇒ 元判据必须报 ERROR。

        用「共 N 种 kind」做样例（该短语的 claims 只挂在 5个Skill设计文档/配置JSON 上）。"""
        from engine import doc_number_authority as D1
        p = DOCDIR / self.F05
        snap = p.read_text(encoding="utf-8")
        try:
            p.write_text(snap + "\n（附注）该模块实测共 **7** 种 kind。\n", encoding="utf-8")
            errs = [i for i in D1.audit() if i["level"] == "ERROR"]
            assert any("元判据" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D1.audit() if i["level"] == "ERROR"]

    @pytest.mark.plain
    def test_meta_check_present_in_source(self):
        """判据自证存在（防止元判据日后被删）。"""
        src = (ROOT / "engine" / "doc_consistency_core.py").read_text(encoding="utf-8")
        assert "def check_meta_coverage(" in src
        assert "declaration_scope" in src

    @pytest.mark.plain
    def test_declaration_scope_covers_skill_docs(self):
        """口径：5 个 Skill 文档（既是对照类又是**声明类**）必须在 `declaration_scope` 里，
        否则它们声明的"当前事实"永远不会被校验（这正是本轮的病根之一）。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        scope = set(core.config().get("declaration_scope") or [])
        for f in ("5个Skill设计文档.md", "5个Skill配置JSON.md", "5个Skill门禁规则.md",
                  "5个Skill测试用例.md", "5个Skill回归测试报告.md", "5个Skill验收自证.md"):
            assert f in scope, f

    # ---- 新 kind：regex_count / distinct ----

    @pytest.mark.plain
    def test_regex_count_authority_equals_rule_rows(self):
        """`regex_count` 的权威值 == 门禁规则表里的判据行数（现算，不硬编码）。"""
        import re
        from engine import doc_consistency_core as core
        core.reload_config()
        assert self._A("judgement_count") == self._A("judgement_count")   # 幂等
        t = (DOCDIR / "5个Skill门禁规则.md").read_text(encoding="utf-8")
        rows = [l for l in t.split("\n") if re.match(r"^\| \*\*D[0-9]-R[0-9]+\*\*", l)]
        assert self._A("judgement_count") == len(rows)

    @pytest.mark.plain
    def test_distinct_authority_equals_kind_count(self):
        """`distinct:` 表达式 == `numbers[].authority.kind` 去重种类数。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        kinds = {n["authority"].get("kind") for n in core.config()["numbers"]}
        assert self._A("authority_kind_count") == len(kinds)

    # ---- 四类口径：拆得开、合得拢 ----

    @pytest.mark.lock
    def test_case_category_partition_sums_to_total(self):
        """**口径锁**：反向验证 + 破坏性 + 口径锁 + 正例/自证 == 用例总数（42）。

        这条锁防止再出现"用兜底残差当类别"（上一轮把 22 当类别，与其他文件的"5"打架）。"""
        total = self._A("doc_test_total")
        parts = (self._A("reverse_test_count"), self._A("break_test_count"),
                 self._A("lock_test_count"), self._A("plain_test_count"))
        assert sum(parts) == total, (parts, total)
        assert self._A("validation_case_total") == parts[0] + parts[1] + parts[2]

    @pytest.mark.plain
    def test_markers_registered(self):
        """四个分类 marker 必须已注册（否则 pytest 会报 unknown marker）。"""
        t = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
        for m in ("reverse", "breaking", "lock", "plain"):
            assert "\"%s\"" % m in t or "'%s'" % m in t, m

    # ---- 反向验证：新权威纠错 ----

    def _mutate(self, fname, fixed, broken):
        from engine import doc_number_authority as D1
        p = DOCDIR / fname
        snap = p.read_text(encoding="utf-8")
        try:
            got = snap if broken in snap else snap.replace(fixed, broken, 1)
            assert got != snap, "锚点未命中：%s" % fixed[:40]
            p.write_text(got, encoding="utf-8")
            errs = [i for i in D1.audit() if i["level"] == "ERROR"]
            assert errs, "改错后无人报错"
        finally:
            p.write_text(snap, encoding="utf-8")
        assert not [i for i in D1.audit() if i["level"] == "ERROR"]

    @pytest.mark.reverse
    def test_reverse_wrong_authority_count_detected(self):
        """**反向**：把「数字权威（N 个）」改错 ⇒ ERROR。"""
        self._mutate(self.FA, "**已登记的数字权威（%d 个）**" % self._A("authority_count"),
                     "**已登记的数字权威（7 个）**")

    @pytest.mark.reverse
    def test_reverse_wrong_kind_count_detected(self):
        """**反向**：把「N 种 kind」改错 ⇒ ERROR。"""
        self._mutate(self.FA, "取权威值（%d 种 kind）" % self._A("authority_kind_count"),
                     "取权威值（5 种 kind）")

    @pytest.mark.reverse
    def test_reverse_wrong_judgement_count_detected(self):
        """**反向**：把「（N 条判据）」改错 ⇒ ERROR。"""
        self._mutate(self.FV, "（**%d 条判据**）" % self._A("judgement_count"), "（11 条判据）")

class TestDeliverableNaming:
    """交付物命名规范（D1-R10）—— 防"同名 / 近名 / 程度词堆叠"复发。

    实测病根：同一批次追加 4 轮后出现 3 份「…修正记录」、2 份「…诊断报告」、2 份「…被抓记录」，
    且「最终」之后又出「终极」；更有**同一文件名被两轮指令点名**而我复用同一份文件 ⇒
    外人核对清单时会问「怎么会有同名的交付物？」。
    """

    @pytest.mark.breaking
    def test_reverse_unregistered_deliverable_is_flagged(self):
        """**反向**：在交付物目录里新增一个**未登记**的文件 ⇒ 命名判据必须报 ERROR。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        tmp = DOCDIR / "R9_临时未登记.md"
        try:
            tmp.write_text("# tmp\n", encoding="utf-8")
            errs = [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]
            assert any("未登记" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            tmp.unlink(missing_ok=True)
        core.reload_config()
        assert not [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]

    @pytest.mark.breaking
    def test_reverse_forbidden_word_in_round_file_is_flagged(self):
        """**反向**：轮次文件名里带**程度词**（如 `R9_最终记录.md`）⇒ 必须报 ERROR。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        tmp = DOCDIR / "R9_最终记录.md"
        try:
            tmp.write_text("# tmp\n", encoding="utf-8")
            errs = [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]
            assert any("程度词" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            tmp.unlink(missing_ok=True)
        core.reload_config()
        assert not [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]

    @pytest.mark.breaking
    def test_reverse_registry_ghost_is_flagged(self):
        """**反向**：登记表里放一个**不存在**的文件（幽灵登记）⇒ 必须报 ERROR。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        cfg = core.config()
        reg = cfg.setdefault("deliverable_registry", [])
        ghost = {"file": "R9_幽灵登记.md", "round": "R9", "role": "幽灵"}
        reg.append(ghost)
        try:
            errs = [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]
            assert any("幽灵登记" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            reg.remove(ghost)
            core.reload_config()

    @pytest.mark.breaking
    def test_reverse_duplicate_round_role_is_flagged(self):
        """**反向**：同一（轮次, 角色）登记两项 ⇒ 必须报 ERROR（防"同题材重复交付"）。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        cfg = core.config()
        reg = cfg.setdefault("deliverable_registry", [])
        dup = {"file": "R4_被抓记录.md", "round": "R4", "role": "被抓记录"}
        reg.append(dup)                      # 与已有同轮同角色重复（文件本身合法）
        try:
            errs = [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]
            assert any("重复" in str(i.get("detail")) for i in errs), errs[:3]
        finally:
            reg.remove(dup)
            core.reload_config()

    @pytest.mark.lock
    def test_resident_name_with_word_final_is_allowed(self):
        """**口径锁**：常驻名可以含「最终」（`最终判断.md` 是**用户指令点名的交付物名**，不得因此改名）。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        rules = core.config()["naming_rules"]
        assert "最终判断.md" in rules["resident_files"]
        assert "仅对**非常驻" in rules["scope_of_forbidden_words"]
        assert not [i for i in core.check_deliverable_naming() if i["level"] == "ERROR"]

    @pytest.mark.lock
    def test_lock_current_value_equal_to_stale_is_allowed(self):
        """**口径锁**：**当前值恰好等于某个历史旧值**时不算残留（判据应是"旧值不得残留"）。

        实测病根：新增"正例/自证用例数"权威后其值恰为 **25**，而「25 例」是登记的历史旧值 ⇒ D3 假阳性。
        口径：**「已登记的当前值声明行」不计残留**；**非声明行上的旧值仍必须报**。"""
        from engine import doc_residue_scan as D3, doc_consistency_core as core
        core.reload_config()
        assert not [i for i in D3.audit() if i["level"] == "ERROR"]
        # 该行同时满足：① 命中"正例/自证用例数"的 claims（当前值）② 含历史旧值「25 例」的写法
        hits = [(i, l) for i, l in enumerate(
            (DOCDIR / "最小检查集.md").read_text(encoding="utf-8").split("\n"), 1)
            if "正例/自证" in l]
        assert hits, "未找到『正例/自证』声明行"
        assert any(str(core.authority_value(
            [n for n in core.config()["numbers"] if n["id"] == "plain_test_count"][0]["authority"])[0]) in l
            for _, l in hits)

    @pytest.mark.plain
    def test_naming_gate_registered(self):
        """判据自证：函数存在 + 登记表覆盖目录全部文件 + (轮次,角色) 唯一。"""
        from engine import doc_consistency_core as core
        core.reload_config()
        src = (ROOT / "engine" / "doc_consistency_core.py").read_text(encoding="utf-8")
        assert "def check_deliverable_naming(" in src
        reg = core.config()["deliverable_registry"]
        files = {p.name for p in DOCDIR.glob("*.md")}
        assert {r["file"] for r in reg} == files
        assert len({(r["round"], r["role"]) for r in reg}) == len(reg)
