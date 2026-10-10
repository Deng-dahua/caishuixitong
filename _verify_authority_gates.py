# -*- coding: utf-8 -*-
"""反向验证：2026-10-09 本轮两道闸门**必须自证非假**（改坏 ⇒ 变红）。

闸门是"给单一权威配的自动校验"，但闸门自己也会假：
  · 假绿：判据同义反复 / 只看注释 / 缓存了旧模块 ⇒ 改坏了也不报；
  · 假红：把**说明文字**当代码审（本轮 `check_delete_exits` 实测踩过）。
本脚本对每一条判据**注入它本该抓到的缺陷**，断言必须变红；再恢复，断言回到绿。

覆盖：
  G1 `check_delete_exits`               —— 删除出口唯一（含"底层原语全仓唯一定义"）
  G2 `check_report_version_reuse_authority` —— 增量复用版式判据必须走权威（4 段判据）
  G3 `check_audit_trail_single_writer`  —— 业务留痕写入唯一权威（静态 + 子进程行为）
  G4 `check_report_payload_single_shape` —— 报告载荷形状唯一（T-P0-8：R10~R12）
  G5 `check_redline_detector_attribution` —— 红线归属须由检测器自报（A-P0-1：R13~R15）
  G6 `check_non_risk_findings_not_flagged` —— 正向发现不得被打风险等级（A-P0-3：R16~R17）
  G7 `check_redline_coverage_counts_authority_table` —— 覆盖率须认「归属权威表」形态（A-P0-4：R18~R19）
  G8 `check_redline_overlap_ledger` —— 同概念红线须登记且不靠兜底编闭环（A-P0-2：R20~R22）

其中 R6/R6b 专门证明 G1 的**扫描范围**真的覆盖 `tools/` 与 `scripts/`
—— 本轮补的正是这个缺口（原 `_SCAN` 只扫 `engine/*.py` + 4 个根文件，
`tools/cleanup_20261008.py` 里那份 `move_to_trash` 第二实现对闸门完全隐形）。
R8/R9 证明 G3 既抓得住"别处再写一份 INSERT"，也不会被**说明文字**误伤。
R10~R12 证明 G4 三段判据各自非假：手写载荷字面量 / 键名漂移 / PPTX 静默丢项，
且 R11b 证明它同样不审散文（`assert "..." not in s` 是正当断言，不是第二出处）。
R13~R15 证明 G5 三段判据各自非假：登记与代码不一致 / 非生产代码登记 / 红线 id 不存在。
R16~R17 证明 G6 是**端到端**判据：直接篡改真产物里的正向发现 ⇒ 必须抓到；修复后的真产物 ⇒ 必须 0 ERROR。
R18~R19 证明 G7 会抓「表声明的红线被算成仅兜底」与「归属权威表被清空」。
R20~R22 证明 G8 会抓「登记重复却仍靠兜底认要件」「登记重复却未声明有意不兜底」「净增量为空」。
   ★ R20/R21 的注入对象**动态选取 + 状态合成**（2026-10-10 两次修正）：
     旧版硬编码 `RL-VAT-012`，A 轨道给它建了真检测器后它走「有检测器 ⇒ 豁免」分支，
     注入被吃掉 ⇒ 反向验证静默失效。改为动态挑同概念成员后，**当晚所有成员也都建了检测器**
     ⇒ 再次无天然样检对象。**不能因此放弃自证**：现改为**合成健康态**——篡改覆盖率产物
     把该成员从 `has_detector` 摘掉、必要时临时加入 `_NB`，注入缺陷 ⇒ 必红，随后逐字节还原。

用法：`.venv/Scripts/python.exe _verify_authority_gates.py`

★★ 严禁与任何审计/测试**并行**运行 ★★
  本脚本为了证明"闸门不是假的"，必须把源码**临时改坏**（注入第二份原语实现、
  把权威函数改成恒 True……）。实测（2026-10-09）：在跑本脚本的同时另起
  `tools/audit_consistency.py`，审计读到的是**被改坏的源码** ⇒ 报出 19 项 ERROR，
  全部是并发污染的假红（单独重跑 ⇒ ERROR 0）。
  两条纪律：
    ① 跑本脚本时**不要**同时跑 audit / pytest / 端到端验收；
    ② 本脚本的 `Patch` 一律**原子写**（`runtime_storage.atomic_write_text`），
       避免并发读者读到**写了一半**的源码（截断的源码会造成更难解释的假红）。
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load_gates():
    spec = importlib.util.spec_from_file_location(
        "_ac_verify", ROOT / "tools" / "audit_consistency.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drop_engine_caches() -> None:
    """把按文件内容判定的模块踢出 `sys.modules`，否则改动被旧对象掩盖（假绿）。"""
    for k in list(sys.modules):
        if k.startswith(("engine.enterprise_report", "engine.audit_doctrine",
                         "engine.report_identity")):
            del sys.modules[k]


RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print("  %s  %s%s" % ("PASS" if ok else "FAIL", name, ("  | " + detail) if detail else ""))


class Patch:
    """临时改写一个源文件；退出时**逐字节还原**（`finally` 保证）。

    ★ 写入一律走 `runtime_storage.atomic_write_text`（fsync + `os.replace`）：
      本脚本运行期间源码处于"被改坏"状态，若用 `write_text` 直接覆盖，
      并发的读者可能读到**写了一半**的截断文件 ⇒ 产生无法解释的假红
      （实测：并发跑 audit 时报出 19 项 ERROR，单独重跑为 0）。
    """

    def __init__(self, rel: str):
        self.path = ROOT / rel
        self.orig = self.path.read_text(encoding="utf-8")

    def __enter__(self):
        return self

    def _write(self, text: str) -> None:
        from runtime_storage import atomic_write_text
        atomic_write_text(self.path, text)

    def apply(self, old: str, new: str) -> None:
        cur = self.path.read_text(encoding="utf-8")
        assert old in cur, "补丁锚点不存在：%r" % old[:60]
        self._write(cur.replace(old, new, 1))

    def __exit__(self, *exc):
        self._write(self.orig)
        _drop_engine_caches()
        return False


def _red(issues, needle: str) -> bool:
    """问题清单里是否出现某段文字（默认只看 `i[2]` 消息体）。"""
    return any(needle in i[2] for i in issues)


def _red_any(issues, needle: str) -> bool:
    """在**文件字段 `i[1]` 与消息 `i[2]` 两处**查找。

    ★ 2026-10-09 实测踩坑：R8 的断言只看消息体，而"是哪个文件"落在 `i[1]`
      ⇒ 闸门**明明抓到了**（`('ERROR','engine/_zz_probe_g3_second_writer.py', ...)`）
      断言却判 FAIL，是**判据错**不是闸门坏 —— 典型的"判据误报时改判据"。
    """
    return any((needle in i[2]) or (needle in str(i[1])) for i in issues)


def main() -> int:
    print("=" * 74)
    print("反向验证：本轮闸门必须自证非假（改坏 ⇒ 变红）")
    print("=" * 74)
    print("!! 本脚本运行期间源码会被**临时改坏**：请勿同时运行 audit / pytest / 端到端验收")

    # ── 基线：当前必须全绿 ──────────────────────────────────────────────
    print("\n[0] 基线（未注入缺陷）—— 必须全绿")
    g = _load_gates()
    base_del = g.check_delete_exits()
    base_reuse = g.check_report_version_reuse_authority()
    base_payload = g.check_report_payload_single_shape()
    check("G1 check_delete_exits 基线为空", base_del == [], repr(base_del[:2]))
    check("G2 check_report_version_reuse_authority 基线为空",
          base_reuse == [], repr(base_reuse[:2]))
    check("G4 check_report_payload_single_shape 基线为空",
          base_payload == [], repr(base_payload[:2]))

    # ── R1：真删除调用（非声明出口）必须变红；仅"提到"不得变红 ──────────
    print("\n[R1] G1：注入真删除调用 ⇒ 必须 ERROR（判据不是只看注释）")
    with Patch("engine/analysis_jobs.py") as p:
        p.apply("def last_error() -> Optional[str]:",
                "def _injected_probe_undeclared_delete():\n"
                "    import os\n"
                "    os.unlink('should-be-caught')\n"
                "    return None\n\n\n"
                "def last_error() -> Optional[str]:")
        _drop_engine_caches()
        issues = _load_gates().check_delete_exits()
        check("G1 抓到未声明的 os.unlink", _red(issues, "_injected_probe_undeclared_delete")
              or _red(issues, "未声明的删除调用"), repr(issues[:2]))

    print("\n[R1b] G1：docstring 里只**提到** os.unlink ⇒ 不得 ERROR（判据不审散文）")
    with Patch("engine/analysis_jobs.py") as p:
        p.apply("def last_error() -> Optional[str]:",
                "def _injected_probe_doc_only():\n"
                "    \"\"\"说明：从前这里顺手写过 os.unlink(tmp)，已被权威取代。\"\"\"\n"
                "    return None\n\n\n"
                "def last_error() -> Optional[str]:")
        _drop_engine_caches()
        issues = _load_gates().check_delete_exits()
        check("G1 未把 docstring 里的说明误判为删除调用",
              not _red(issues, "_injected_probe_doc_only"), repr(issues[:2]))

    # ── R2：权威函数被删 ⇒ G2 的 A 段变红 ───────────────────────────────
    print("\n[R2] G2-A：删掉权威函数 `is_current_report_version` ⇒ 必须 ERROR")
    with Patch("engine/enterprise_report.py") as p:
        p.apply("def is_current_report_version(readable_report: Any) -> bool:",
                "def is_current_report_version_RENAMED(readable_report: Any) -> bool:")
        _drop_engine_caches()
        issues = _load_gates().check_report_version_reuse_authority()
        check("G2-A 抓到权威函数缺失", _red(issues, "缺 `is_current_report_version()`"),
              repr(issues[:2]))

    # ── R3：main.py 自行解释 compilation_style（旧缺陷的样子）⇒ B 段变红 ──
    print("\n[R3] G2-B：把 main.py 改回「自行读 compilation_style」（即原缺陷）⇒ 必须 ERROR")
    main_txt = (ROOT / "main.py").read_text(encoding="utf-8")
    tax_risk_txt = (ROOT / "tax_risk.py").read_text(encoding="utf-8")
    domain_txt = (ROOT / "engine" / "domain_analysis.py").read_text(encoding="utf-8")
    _anchor = "                _cached_report_ok = False\n                try:\n                    from engine.enterprise_report import ("
    assert _anchor in main_txt, "main.py 补丁锚点不在（增量复用分支结构已变）"
    with Patch("main.py") as p:
        p.apply(_anchor,
                "                _cached_report_ok = False\n"
                "                try:\n"
                "                    _cer = ((_cached.get('report') or {}).get('report') or {}).get('enterprise_readable_report') or {}\n"
                "                    _cached_report_ok = _cer.get('compilation_style') in ('内部辅助分析工作底稿（风险检查文书式）',)\n"
                "                except Exception:\n"
                "                    _cached_report_ok = False\n"
                "                try:\n"
                "                    from engine.enterprise_report import (")
        issues = _load_gates().check_report_version_reuse_authority()
        check("G2-B 抓到主流程自行解释 compilation_style",
              _red(issues, "主流程出现 `compilation_style`"), repr(issues[:2]))

    # ── R4：权威函数被改成"恒放行" ⇒ D 段行为断言变红 ────────────────────
    print("\n[R4] G2-D：把权威改成恒 True（任何缓存都可复用）⇒ 必须 ERROR")
    with Patch("engine/enterprise_report.py") as p:
        p.apply("    if not isinstance(readable_report, dict):\n        return False",
                "    return True\n    if not isinstance(readable_report, dict):\n        return False")
        _drop_engine_caches()
        issues = _load_gates().check_report_version_reuse_authority()
        check("G2-D 抓到「空报告/禁止别名/缺 document_meta 也放行」",
              _red(issues, "带**禁止别名**") or _red(issues, "空报告仍被判为可复用"),
              repr(issues[:2]))

    # ── R5：报告名的第二出处复活 ⇒ C 段变红 ─────────────────────────────
    print("\n[R5] G2-C：在 audit_doctrine 恢复 compilation_style 副本（第二出处）⇒ 必须 ERROR")
    with Patch("engine/audit_doctrine.py") as p:
        p.apply('        "code": "working_paper",',
                '        "code": "working_paper",\n'
                '        "compilation_style": "涉税风险检查工作报告（风险检查文书式）",')
        _drop_engine_caches()
        issues = _load_gates().check_report_version_reuse_authority()
        check("G2-C 抓到报告名第二出处复活",
              _red(issues, "仍有 `compilation_style`"), repr(issues[:2]))

    # ── R6：底层原语第二份实现（在 tools/）⇒ 必须变红 ─────────────────────
    #   这正是本轮实测到的真实违规（`tools/cleanup_20261008.py::move_to_trash`）。
    print("\n[R6] G1：在 tools/ 注入第二份原语实现 ⇒ 必须 ERROR（扫描范围真的覆盖 tools/）")
    with Patch("tools/cleanup_20261008.py") as p:
        p.apply("def protected(p: str) -> bool:",
                "def purge_file(_probe):\n"
                "    return (True, 'injected-probe')\n\n\n"
                "def protected(p: str) -> bool:")
        issues = _load_gates().check_delete_exits()
        check("G1 抓到 tools/ 里的第二份 `purge_file`",
              _red(issues, "出现 2 份实现") and _red(issues, "tools/cleanup_20261008.py"),
              repr(issues[:2]))

    # ── R6b：底层原语第二份实现（在 scripts/）⇒ 必须变红 ──────────────────
    print("\n[R6b] G1：在 scripts/ 注入第二份原语实现 ⇒ 必须 ERROR（扫描范围真的覆盖 scripts/）")
    with Patch("scripts/_render_report_html.py") as p:
        p.apply("def tr(s, n=600):", "def atomic_write_text(_a, _b):\n"
                                    "    return None\n\n\n"
                                    "def tr(s, n=600):")
        issues = _load_gates().check_delete_exits()
        check("G1 抓到 scripts/ 里的第二份 `atomic_write_text`",
              _red(issues, "出现 2 份实现") and _red(issues, "scripts/_render_report_html.py"),
              repr(issues[:2]))

    # ── R7：唯一实现被改名搬走 ⇒ 必须变红（"找不到实现"这一支） ────────────
    print("\n[R7] G1：把 runtime_storage 里的唯一实现改名 ⇒ 必须 ERROR（禁止静默失去唯一实现）")
    with Patch("runtime_storage.py") as p:
        p.apply("def purge_file(file_path) -> tuple:",
                "def purge_file_RENAMED(file_path) -> tuple:")
        issues = _load_gates().check_delete_exits()
        check("G1 抓到原语全仓无实现",
              _red(issues, "全仓找不到实现") and _red(issues, "purge_file"),
              repr(issues[:2]))

    # ── R8：业务留痕"第二写入点" ⇒ 必须变红 ────────────────────────────
    #   这正是本轮要根治的形态："表在、读接口在、写入零" ⇒ 谁都能自己补一句写入。
    #   字面量**一律运行期拼**：本脚本自身也被闸门扫描，说明文字不得变成"第二写入点"
    #  （实测踩过：`print("... INSERT INTO audit_logs ...")` 被闸门判为真写入）。
    _needle = "INSERT " + "INTO " + "audit_logs"
    print("\n[R8] G3：别处再写一份 `%s` ⇒ 必须 ERROR" % _needle)
    _probe = ROOT / "engine" / "_zz_probe_g3_second_writer.py"
    _probe.write_text(
        "# -*- coding: utf-8 -*-\n"
        "def bad(conn):\n"
        "    conn.execute(\"%s (company_id, action) VALUES (1, 'x')\")\n" % _needle,
        encoding="utf-8")
    try:
        issues = _load_gates().check_audit_trail_single_writer()
        check("G3 抓到第二写入点",
              _red_any(issues, "_zz_probe_g3_second_writer")
              and _red(issues, "只允许在唯一权威"),
              repr(issues[:2]))
    finally:
        if _probe.exists():
            _probe.unlink()

    # ── R9：只在 docstring/注释里"提到"该写法 ⇒ 不得变红（判据不审散文）────
    print("\n[R9] G3：只在说明文字里提到 INSERT ⇒ 不得 ERROR")
    _probe2 = ROOT / "engine" / "_zz_probe_g3_prose_only.py"
    _probe2.write_text(
        "# -*- coding: utf-8 -*-\n"
        "def note():\n"
        "    \"\"\"说明：从前这里顺手写过 %s，已被唯一权威取代。\"\"\"\n"
        "    # %s 只出现在注释里\n"
        "    return None\n" % (_needle, _needle),
        encoding="utf-8")
    try:
        issues = _load_gates().check_audit_trail_single_writer()
        check("G3 未把说明文字误判为写入点",
              not _red(issues, "_zz_probe_g3_prose_only"), repr(issues[:2]))
    finally:
        if _probe2.exists():
            _probe2.unlink()

    # ── R10：载荷又出现"手写字面量 return" ⇒ 必须变红（G4-A）────────────
    #   这正是 T-P0-8 的病根：两个 return 各自手写形状 ⇒ summary 一处 str 一处 dict。
    print("\n[R10] G4-A：让 `get_tax_risk_report()` 再手写一个字典 return ⇒ 必须 ERROR")
    with Patch("tax_risk.py") as p:
        p.apply("    if not _has_any_business_data(db, company_id):\n"
                "        return _report_payload(",
                "    if not _has_any_business_data(db, company_id):\n"
                "        return {\"summary\": \"该公司暂无业务数据\"}\n"
                "    if False:\n"
                "        return _report_payload(")
        issues = _load_gates().check_report_payload_single_shape()
        check("G4-A 抓到第二处手写载荷字面量",
              _red(issues, "不是 `_report_payload(...)`"), repr(issues[:2]))

    # ── R11：中风险键名第二写法 ⇒ 必须变红（G4-B）───────────────────────
    _badkey = "medium_" + "risk_count"           # 运行期拼：本脚本自身不得写死
    print("\n[R11] G4-B：把中风险键名写成 `%s` ⇒ 必须 ERROR" % _badkey)
    _probe4 = ROOT / "engine" / "_zz_probe_g4_key_drift.py"
    _probe4.write_text("# -*- coding: utf-8 -*-\ndef bad(payload):\n"
                       "    return payload[\"%s\"]\n" % _badkey, encoding="utf-8")
    try:
        issues = _load_gates().check_report_payload_single_shape()
        check("G4-B 抓到中风险键名漂移",
              _red_any(issues, "_zz_probe_g4_key_drift")
              and _red(issues, "键名唯一权威是"), repr(issues[:2]))
    finally:
        if _probe4.exists():
            _probe4.unlink()

    print("\n[R11b] G4-B：说明文字/断言里**提到**该写法 ⇒ 不得 ERROR（判据不审散文）")
    _probe4b = ROOT / "engine" / "_zz_probe_g4_prose_only.py"
    _probe4b.write_text(
        "# -*- coding: utf-8 -*-\ndef note(s):\n"
        "    \"\"\"说明：从前中风险键名写作 %s，已收敛为 mid_risk_count。\"\"\"\n"
        "    assert \"%s\" not in s, \"这是正当的测试断言，不是第二出处\"\n"
        "    return None\n" % (_badkey, _badkey), encoding="utf-8")
    try:
        issues = _load_gates().check_report_payload_single_shape()
        check("G4-B 未把说明文字/断言误判为键名漂移",
              not _red_any(issues, "_zz_probe_g4_prose_only"), repr(issues[:2]))
    finally:
        if _probe4b.exists():
            _probe4b.unlink()

    # ── R12：恢复"每页第 7 项被 continue 丢掉" ⇒ 必须变红（G4-C 行为）─────
    print("\n[R12] G4-C：恢复 PPTX 的 `if idx > 0 and idx % 6 == 0: continue` ⇒ 必须 ERROR")
    with Patch("tax_risk.py") as p:
        p.apply("    for idx, r in enumerate(results):\n        if idx % 6 == 0:",
                "    for idx, r in enumerate(results):\n"
                "        if idx > 0 and idx % 6 == 0:\n"
                "            continue\n"
                "        if idx % 6 == 0:")
        issues = _load_gates().check_report_payload_single_shape()
        check("G4-C 抓到 PPTX 静默丢项",
              _red(issues, "PPTX 静默丢项") or _red(issues, "丢项"), repr(issues[:2]))

    # ── R13：检测器的归属声明被删 ⇒ 必须变红（G5-B）─────────────────────
    #   这正是 A-P0-1 的病根：事实算出来了，却没声明它属于哪条红线 ⇒ 引擎按关键词猜。
    print("\n[R13] G5：删掉 `_domain_depreciation_match` 的 `redline_id` 声明 ⇒ 必须 ERROR")
    with Patch("engine/domain_analysis.py") as p:
        p.apply('            "redline_id": "RL-AST-001",\n', "")
        issues = _load_gates().check_redline_detector_attribution()
        check("G5 抓到「登记了声明、代码里没有」",
              _red(issues, "找不到声明"), repr(issues[:2]))

    # ── R14：把归属登记到一次性脚本上 ⇒ 必须变红（G5-B 生产代码口径）──────
    print("\n[R14] G5：把 `detector_file` 指向 scripts/ ⇒ 必须 ERROR（非生产代码等于没登记）")
    _conf = ROOT / "config" / "redline_detector_attribution.json"
    _conf_txt = _conf.read_text(encoding="utf-8")
    with Patch("config/redline_detector_attribution.json") as p:
        p.apply('"detector_file": "engine/domain_analysis.py"',
                '"detector_file": "scripts/_audit_redline_coverage.py"')
        issues = _load_gates().check_redline_detector_attribution()
        check("G5 抓到非生产代码登记",
              _red(issues, "不是生产代码"), repr(issues[:2]))

    # ── R15：声明一个不存在的红线 id ⇒ 必须变红（G5-C）──────────────────
    print("\n[R15] G5：把 `redline_id` 换成不存在的 id ⇒ 必须 ERROR")
    with Patch("config/redline_detector_attribution.json") as p:
        p.apply('"redline_id": "RL-AST-001"', '"redline_id": "RL-XXX-999"')
        issues = _load_gates().check_redline_detector_attribution()
        check("G5 抓到红线 id 不存在",
              _red(issues, "不在红线库里"), repr(issues[:2]))

    # ── R16：G6 必须在**真产物**上抓到"正向发现被打风险等级" ⇒ 端到端判据非假 ──
    #   复刻缺陷形态：把真产物里的一条正向发现的 level 改回「待核验」，判据必须抓到。
    print("\n[R16] G6：把真产物里的正向发现 level 改成「待核验」⇒ 必须抓到（端到端）")
    import json as _json
    _dump = ROOT / "scripts" / "four_reports" / "company_1_full.json"
    if not _dump.exists():
        check("G6 端到端判据（产物缺失，如实记为未验证）", False,
              "无 %s ⇒ 跑 scripts/run_companies.py 后重跑本脚本" % _dump.name)
    else:
        _data = _json.loads(_dump.read_text(encoding="utf-8"))
        _found = []

        def _poke(o, _seen=None):
            """就地找到第一条正向发现，把它的 level 篡改成「待核验」（只在内存里）。"""
            if _seen is None:
                _seen = set()
            if isinstance(o, dict):
                if id(o) in _seen:
                    return False
                _seen.add(id(o))
                if (o.get("tax_benefit") or o.get("non_risk_semantic")) and o.get("level"):
                    o["level"] = "待核验"
                    _found.append(o.get("type"))
                    return True
                return any(_poke(v, _seen) for v in o.values())
            if isinstance(o, list):
                return any(_poke(v, _seen) for v in o)
            return False

        _mutated = _poke(_data[:] if isinstance(_data, list) else _data)
        _conf6 = _load_gates().non_risk_level_conflicts([("probe", _data)])
        check("G6 抓到被篡改的正向发现",
              bool(_mutated) and bool(_conf6) and any("待核验" in d for _, d in _conf6),
              "mutated=%r conflicts=%r" % (_mutated, _conf6[:2]))

    # ── R17：真产物本身必须**零冲突**（修复后的正例；G6 不得靠误报过日子）──
    print("\n[R17] G6：修复后的真产物必须 0 ERROR（正例）")
    if _dump.exists():
        _issues = [i for i in _load_gates().check_non_risk_findings_not_flagged()
                   if i[0] == "ERROR"]
        check("G6 真产物无正向发现被打等级", not _issues, repr(_issues[:2]))
    else:
        check("G6 真产物正例（产物缺失，如实记为未验证）", False, "见 R16")

    # ── R18：覆盖率口径漏掉「归属权威表」形态 ⇒ 必须变红（G7-B）─────────────
    #   复刻缺陷形态：把表声明过的红线挪回 `only_fallback`（改造前就是这样）。
    print("\n[R18] G7：把表声明的红线挪回 `only_fallback` ⇒ 必须 ERROR")
    import json as _json2
    _covp = ROOT / "scripts" / "_redline_coverage.json"
    if not _covp.exists():
        check("G7 覆盖率口径判据（产物缺失，如实记为未验证）", False,
              "无 %s ⇒ 先跑 scripts/_audit_redline_coverage.py" % _covp.name)
    else:
        _cov = _json2.loads(_covp.read_text(encoding="utf-8"))
        _table = {"RL-CIT-008", "RL-PAY-002"}
        _bad = dict(_cov)
        _bad["has_detector"] = [x for x in _cov["has_detector"] if x not in _table]
        _bad["only_fallback"] = list(_cov["only_fallback"]) + ["RL-CIT-008"]
        _probs = _load_gates().coverage_missing_authority_table(_bad, _table)
        check("G7 抓到「表声明的红线被算成仅兜底」",
              any("only_fallback" in p for p in _probs)
              and any("has_detector" in p for p in _probs),
              repr(_probs[:3]))
        check("G7 正例：真实产物必须 0 问题",
              _load_gates().coverage_missing_authority_table(_cov, _table) == [],
              repr(_load_gates().coverage_missing_authority_table(_cov, _table)[:2]))

    # ── R19：归属权威表被清空 ⇒ 必须变红（G7-A）──────────────────────────
    print("\n[R19] G7：清空归属权威表 ⇒ 必须 ERROR（归属层唯一权威不得被清空）")
    from engine import subject_consistency as _SC
    _keep_decl = _SC.REDLINE_SUBJECT_DECL
    try:
        _SC.REDLINE_SUBJECT_DECL = {}
        issues = _load_gates().check_redline_coverage_counts_authority_table()
        check("G7 抓到归属权威表被清空",
              any("归属权威表为空" in i[2] for i in issues), repr(issues[:2]))
    finally:
        _SC.REDLINE_SUBJECT_DECL = _keep_decl

    # ── 收尾：全部还原后必须回到全绿 ────────────────────────────────────
    #   ★ 本脚本的 `Patch` 是"改坏再逐字节还原"，**还原也会刷新 mtime** ⇒
    #     `scripts/_redline_coverage.json` 这类**派生产物**必然变成"比源文件旧"，
    #     从而让 G5/G7 的新鲜度判据与 `tests/test_redline_attribution.py` 的
    #     `test_coverage_artifact_not_stale` 变成**假红**（判据没错，是工作区不一致）。
    #   故收尾必须把派生产物**重算一遍**（与"还原源码"同一性质：把工作区恢复成一致状态）。
    # ── R20/R21：G8-C 分支（"登记重复却仍靠兜底认要件 / 未声明有意不兜底"）──
    #   ★★ 注入对象必须**动态选取**（2026-10-10 实测修正）：旧版硬编码 `RL-VAT-012`。
    #     而 A 轨道已给 012 建了**真检测器** ⇒ G8 的 `has_detector ⇒ 豁免` 分支让它
    #     不再受本约束，注入被豁免吃掉 ⇒ 反向验证**静默失效**（闸门没坏，是样检前提陈旧）。
    #     现改为：动态挑同概念成员并**在进程内合成健康态**（见下）。
    #   ★★ 二次修正（2026-10-10 当晚）：台账里的同概念成员**现已全部建了真检测器**
    #     （本轨道目标达成）⇒ 已无"天然无检测器"的注入对象，"无样检对象就报错"会让
    #     反向验证**从此废止**。正确做法不是放弃，而是**合成状态**：
    #       ① 动态取 `constituent_duplicate` 成员；
    #       ② 篡改覆盖率产物把它从 `has_detector` 摘掉（= 合成"无检测器"）；
    #       ③ 确保它在 `_NB` 内、不在 `_DH`（= 合成"正确的健康态"）；
    #       ④ 注入缺陷 ⇒ 必须变红；⑤ 逐字节还原覆盖率产物与内存表。
    from engine import redline_engine as _RE
    _dh = _RE._DEFAULT_HIT_INDEX
    _nb = _RE._NO_BLIND_CONSTITUENT_FALLBACK
    _ledger_data = _json2.loads((ROOT / "config" / "redline_overlap_ledger.json").read_text(encoding="utf-8"))
    _cov_orig = _covp.read_bytes() if _covp.exists() else None
    _cov_synth = _json2.loads(_cov_orig.decode("utf-8")) if _cov_orig else {}
    _members = [str(m) for _p in (_ledger_data.get("pairs") or [])
                if _p.get("verdict") == "constituent_duplicate"
                for m in (_p.get("members") or [])]
    check("台账存在可注入的同概念成员", bool(_members))
    _target = _members[0] if _members else None
    _added_nb = False
    if _target:
        for _fld in ("has_detector", "has_detector_static", "has_detector_authority_table",
                     "blind", "only_fallback", "no_blind_fallback_no_detector"):
            if isinstance(_cov_synth.get(_fld), list):
                _cov_synth[_fld] = [x for x in _cov_synth[_fld] if x != _target]
        _covp.write_text(_json2.dumps(_cov_synth, ensure_ascii=False, indent=2), encoding="utf-8")
        _added_nb = _target not in _nb
        if _added_nb:
            _nb.add(_target)

    if _target:
        # ── R20：登记为"要件重复"却仍靠兜底认要件 ⇒ 必须变红（G8-C）──────
        print("\n[R20] G8：把 %s 的兜底序号加回去 ⇒ 必须 ERROR（假闭环仍在）" % _target)
        try:
            _dh[_target] = [1, 2, 3, 4]
            issues = _load_gates().check_redline_overlap_ledger()
            check("G8 抓到「登记重复却仍靠兜底认要件」",
                  any("假闭环仍在" in i[2] for i in issues), repr(issues[:2]))
        finally:
            _dh.pop(_target, None)

        # ── R21：登记为"要件重复"却不在"有意不兜底"名单 ⇒ 必须变红（G8-C）─
        print("\n[R21] G8：把 %s 移出 `_NO_BLIND_CONSTITUENT_FALLBACK` ⇒ 必须 ERROR" % _target)
        try:
            _nb.discard(_target)
            issues = _load_gates().check_redline_overlap_ledger()
            check("G8 抓到「登记重复却未声明有意不兜底」",
                  any("须有意不做盲发兜底" in i[2] for i in issues), repr(issues[:2]))
        finally:
            _nb.add(_target)

        # ── 还原合成状态（覆盖率产物逐字节还原；内存表复原）──────────────
        if _added_nb:
            _nb.discard(_target)
        if _cov_orig is not None:
            _covp.write_bytes(_cov_orig)
        check("R20/R21 合成状态已还原（覆盖率产物逐字节一致）",
              _cov_orig is None or _covp.read_bytes() == _cov_orig)

    # ── R22：净增量为空 ⇒ 必须变红（G8-D：没有独立存在必要，应提请合并）──
    print("\n[R22] G8：把某成员的净增量清空 ⇒ 必须 ERROR（提请裁定合并）")
    with Patch("config/redline_overlap_ledger.json") as p:
        p.apply('"RL-VAT-012": "对外投资、分配给股东/投资者"', '"RL-VAT-012": ""')
        issues = _load_gates().check_redline_overlap_ledger()
        check("G8 抓到「未给出净增量」",
              any("未给出净增量" in i[2] for i in issues), repr(issues[:2]))

    # ── 收尾：全部还原后必须回到全绿 ────────────────────────────────────
    print("\n[8b] 重算派生产物（还原源码会刷新 mtime ⇒ 必须让派生产物跟上）")
    try:
        import subprocess as _sp
        _cp = _sp.run([sys.executable, "scripts/_audit_redline_coverage.py"],
                      cwd=str(ROOT), capture_output=True, text=True, timeout=300)
        check("覆盖率派生产物已重算", _cp.returncode == 0,
              ((_cp.stdout or "") + (_cp.stderr or "")).strip()[-160:])
    except Exception as exc:                    # noqa: BLE001
        check("覆盖率派生产物已重算", False, repr(exc))

    print("\n[9] 还原后必须回到全绿（证明上面的变红是被注入缺陷引起，而非环境坏）")
    g = _load_gates()
    check("G1 还原后为空", g.check_delete_exits() == [])
    check("G2 还原后为空", g.check_report_version_reuse_authority() == [])
    check("G3 还原后为空", g.check_audit_trail_single_writer() == [])
    check("G4 还原后为空", g.check_report_payload_single_shape() == [])
    # ⚠ G5 的 D 段含**新鲜度**判据：本脚本刚刚改写并还原了 `engine/domain_analysis.py`（mtime 变了），
    #   覆盖率产物自然"比源文件旧" ⇒ 必然留下一条 WARN。这是**判据正确的行为**（防读过期产物假绿），
    #   故这里只断言 **无 ERROR**，并单独确认那条 WARN 就是新鲜度告警。
    _g5 = g.check_redline_detector_attribution()
    check("G5 还原后无 ERROR（WARN 仅应为「覆盖率产物过期」这一条）",
          not [i for i in _g5 if i[0] == "ERROR"]
          and all("覆盖率产物比被扫描的源文件旧" in i[2] or "覆盖率权威产物" in i[2]
                  for i in _g5 if i[0] == "WARN"),
          repr(_g5[:2]))
    check("G6 还原后为空", [i for i in g.check_non_risk_findings_not_flagged()
                            if i[0] == "ERROR"] == [])
    check("G7 还原后为空", [i for i in g.check_redline_coverage_counts_authority_table()
                            if i[0] == "ERROR"] == [])
    check("G8 还原后为空", [i for i in g.check_redline_overlap_ledger()
                            if i[0] == "ERROR"] == [])
    check("探针文件已清理干净",
          not (ROOT / "engine" / "_zz_probe_g3_second_writer.py").exists()
          and not (ROOT / "engine" / "_zz_probe_g3_prose_only.py").exists()
          and not (ROOT / "engine" / "_zz_probe_g4_key_drift.py").exists()
          and not (ROOT / "engine" / "_zz_probe_g4_prose_only.py").exists())
    check("main.py 逐字节还原",
          (ROOT / "main.py").read_text(encoding="utf-8") == main_txt)
    check("tax_risk.py 逐字节还原",
          (ROOT / "tax_risk.py").read_text(encoding="utf-8") == tax_risk_txt)
    check("domain_analysis.py 逐字节还原",
          (ROOT / "engine" / "domain_analysis.py").read_text(encoding="utf-8") == domain_txt)
    check("归属登记表逐字节还原",
          _conf.read_text(encoding="utf-8") == _conf_txt)

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "-" * 74)
    print("合计 %d 项 | 通过 %d | 失败 %d" % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    print("-" * 74)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
