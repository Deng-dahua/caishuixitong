# -*- coding: utf-8 -*-
"""反向验证：2026-10-09 本轮两道闸门**必须自证非假**（改坏 ⇒ 变红）。

闸门是"给单一权威配的自动校验"，但闸门自己也会假：
  · 假绿：判据同义反复 / 只看注释 / 缓存了旧模块 ⇒ 改坏了也不报；
  · 假红：把**说明文字**当代码审（本轮 `check_delete_exits` 实测踩过）。
本脚本对每一条判据**注入它本该抓到的缺陷**，断言必须变红；再恢复，断言回到绿。

覆盖：
  G1 `check_delete_exits`               —— 删除出口唯一（含"底层原语全仓唯一定义"）
  G2 `check_report_version_reuse_authority` —— 增量复用版式判据必须走权威（4 段判据）

其中 R6/R6b 专门证明 G1 的**扫描范围**真的覆盖 `tools/` 与 `scripts/`
—— 本轮补的正是这个缺口（原 `_SCAN` 只扫 `engine/*.py` + 4 个根文件，
`tools/cleanup_20261008.py` 里那份 `move_to_trash` 第二实现对闸门完全隐形）。

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
    return any(needle in i[2] for i in issues)


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
    check("G1 check_delete_exits 基线为空", base_del == [], repr(base_del[:2]))
    check("G2 check_report_version_reuse_authority 基线为空",
          base_reuse == [], repr(base_reuse[:2]))

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

    # ── 收尾：全部还原后必须回到全绿 ────────────────────────────────────
    print("\n[9] 还原后必须回到全绿（证明上面的变红是被注入缺陷引起，而非环境坏）")
    g = _load_gates()
    check("G1 还原后为空", g.check_delete_exits() == [])
    check("G2 还原后为空", g.check_report_version_reuse_authority() == [])
    check("main.py 逐字节还原",
          (ROOT / "main.py").read_text(encoding="utf-8") == main_txt)

    bad = [r for r in RESULTS if not r[1]]
    print("\n" + "-" * 74)
    print("合计 %d 项 | 通过 %d | 失败 %d" % (len(RESULTS), len(RESULTS) - len(bad), len(bad)))
    print("-" * 74)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
