# -*- coding: utf-8 -*-
"""P2-3 反向验证：注入已知缺陷 ⇒ 必须变红；恢复后**逐字节一致**。

★ 备份 / 注入 / 恢复**一律走 bytes**；注入锚点**一律单行**。

场景：
  S1 engine/ai_assist.py 去掉 `"replaces_rules": False` ⇒ 闸门报"未显式声明"
  S2 engine/ai_assist.py 去掉 `ROLE = "advisory"` ⇒ 闸门报"缺少角色常量"
  S3 engine/ai_assist.py 把 `sanitize(text)` 调用去掉 ⇒ 闸门报"未过清洗"
  S4 ai_assist_api.py 写一份**免责声明字面量** ⇒ 闸门报"第二份声明"
  S5 ai_assist_api.py 把参数化段挪到 `meta` 之前 ⇒ 闸门报"路由顺序"
  S6 main.py 去掉 `app.include_router(ai_assist_router)` ⇒ 闸门报"缺接线"
  S7 把**规则侧线索冒充 AI**（`is_ai` 强制 True） ⇒ 「不冒充」判据变红
  S8 让 `sanitize` **只改写不记录**命中词 ⇒ 清洗双向判据变红
"""
from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _load_gate():
    spec = importlib.util.spec_from_file_location("ac", str(ROOT / "tools" / "audit_consistency.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["ac"] = m
    spec.loader.exec_module(m)
    return m


GATE = _load_gate()
_pass, _fail = [], []


def ok(name: str, cond: bool, detail: str = "") -> None:
    (_pass if cond else _fail).append(name)
    print("%s %s%s" % ("PASS" if cond else "FAIL", name, ("  | " + str(detail)) if detail else ""))


def _md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


class Inject:
    def __init__(self):
        self._bak: dict = {}

    def patch(self, rel: str, old: str, new: str) -> None:
        p = ROOT / rel
        self._bak.setdefault(rel, p.read_bytes())
        raw = p.read_bytes()
        ob, nb = old.encode("utf-8"), new.encode("utf-8")
        if raw.count(ob) < 1:
            raise AssertionError("锚点未命中 %s: %s" % (rel, old[:70]))
        p.write_bytes(raw.replace(ob, nb))

    def restore_all(self) -> None:
        for rel, data in self._bak.items():
            (ROOT / rel).write_bytes(data)

    def verify_restored(self) -> list:
        return [rel for rel, data in self._bak.items() if (ROOT / rel).read_bytes() != data]


def gate_errors(fn_name: str) -> list:
    return [x for x in getattr(GATE, fn_name)() if x[0] == "ERROR"]


def run_pytest(node: str) -> bool:
    cp = subprocess.run([sys.executable, "-m", "pytest", node, "-q"],
                        cwd=str(ROOT), capture_output=True, text=True, timeout=900)
    return cp.returncode == 0


T = "tests/test_ai_assist_p23.py"
inj = Inject()
try:
    # ── S1 replaces_rules 未显式声明 ───────────────────────────────
    inj.patch("engine/ai_assist.py", '"replaces_rules": False,', '"replaces_rules": None,')
    errs = gate_errors("check_ai_assist_wiring")
    ok("S1 未显式声明 replaces_rules ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S2 角色常量缺失 ──────────────────────────────────────────
    inj.patch("engine/ai_assist.py", 'ROLE = "advisory"', 'ROLE = "judgement"')
    errs = gate_errors("check_ai_assist_wiring")
    ok("S2 角色常量被改 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S3 清洗未接（AI 文本直出）────────────────────────────────
    inj.patch("engine/ai_assist.py", "    clean, hits = sanitize(text)", "    clean, hits = text, []")
    errs = gate_errors("check_ai_assist_wiring")
    ok("S3 去掉 sanitize 调用 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S4 免责声明第二份 ────────────────────────────────────────
    inj.patch("ai_assist_api.py", 'router = APIRouter(',
              'DISCLAIMER = "本内容由 AI 辅助生成，仅供线索参考"   # 注入：第二份声明\n\n'
              'router = APIRouter(')
    errs = gate_errors("check_ai_assist_wiring")
    ok("S4 免责声明字面量 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S5 路由顺序 ─────────────────────────────────────────────
    inj.patch("ai_assist_api.py", '@router.get("/ai-assist/meta"',
              '@router.post("/ai-assist/{code}")\n'
              'def _moved_placeholder(code: str):\n'
              '    return {}\n\n\n'
              '@router.get("/ai-assist/meta"')
    errs = gate_errors("check_ai_assist_wiring")
    ok("S5 路由顺序被破坏 ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S6 接线缺失 ─────────────────────────────────────────────
    inj.patch("main.py", "app.include_router(ai_assist_router)", "pass  # 注入：去掉接线")
    errs = gate_errors("check_ai_assist_wiring")
    ok("S6 去掉 include_router ⇒ 闸门报 ERROR", bool(errs),
       (errs[0][2][:74] if errs else "闸门未报（判据是假的）"))
    inj.restore_all()

    # ── S7 规则侧线索冒充 AI ⇒ 「不冒充」判据必须变红 ─────────────────
    inj.patch("engine/ai_assist.py",
              '    out.update({"engine": "rule_hint", "is_ai": False, "is_backend": backend,',
              '    out.update({"engine": "rule_hint", "is_ai": True, "is_backend": backend,')
    red = not run_pytest(T + "::AiAssistAdvisoryTests::test_no_llm_falls_back_honestly")
    ok("S7 线索冒充 AI ⇒ 「不冒充」判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    # ── S8 sanitize 只改写不记录 ⇒ 双向判据必须变红 ────────────────────
    inj.patch("engine/ai_assist.py",
              "            hits.append(term)",
              "            pass   # 注入：只改写不记录命中词")
    red = not run_pytest(T + "::AiAssistUnitTests::test_sanitize_rewrites_and_records")
    ok("S8 只改写不记录 ⇒ 清洗双向判据变红", red,
       "判据正确地失败了" if red else "判据仍绿（同义反复 ⇒ 假判据）")
    inj.restore_all()

    bad = inj.verify_restored()
    ok("恢复后全部文件逐字节一致", not bad, bad)
finally:
    inj.restore_all()

print("\nP2-3 反向验证：%d 通过 / %d 失败" % (len(_pass), len(_fail)))
if _fail:
    print("失败项：", _fail)
    raise SystemExit(1)
print("ALL PASS")
