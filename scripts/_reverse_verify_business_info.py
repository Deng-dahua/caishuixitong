# -*- coding: utf-8 -*-
"""反向验证：把「工商信息查询 + 超经营范围规则」的关键判据逐个改坏，测试必须变红。

★ 为什么必须做：判据若恒真（假绿），等于没测。每个注入都对应一条**真实会发生的
  退化路径**（缓存失效、等级写错、阈值放宽、反证条被删、门禁被绕过、按钮不受控）。

用法：`./.venv/Scripts/python.exe scripts/_reverse_verify_business_info.py`
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
TESTS = ["tests/test_business_info.py", "tests/test_business_scope_rule.py"]

STORE = os.path.join(ROOT, "engine", "business_info", "store.py")
RULE = os.path.join(ROOT, "engine", "business_scope_rule.py")
RL = os.path.join(ROOT, "engine", "tax_redlines.py")
API = os.path.join(ROOT, "business_api.py")
HTML = os.path.join(ROOT, "static", "projects.html")
CFG = os.path.join(ROOT, "config", "business_info.json")


def _run() -> tuple:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run([PY, "-m", "pytest"] + TESTS + ["-q", "--no-header",
                                                      "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True, env=env, timeout=900)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _bump(p: str) -> None:
    st = os.stat(p)
    os.utime(p, (st.st_atime + 120, st.st_mtime + 120))


def _patch(path: str, old: str, new: str) -> None:
    txt = open(path, encoding="utf-8").read()
    assert old in txt, "注入锚点不存在：%r（%s）" % (old[:60], os.path.basename(path))
    open(path, "w", encoding="utf-8", newline="").write(txt.replace(old, new, 1))
    _bump(path)


# ── ① 缓存失效（时间格式解析不出 ⇒ 永不过期判断失败）──
def inj_cache_dead() -> None:
    # ★ 第一次注入写成"抛异常"被兜底分支救活了（假注入）⇒ 直接让函数恒返 None
    _patch(STORE, "    return max(0.0, (base - t).total_seconds() / 3600.0)", "    return None")


# ── ② 等级词表外（写成展示名 ⇒ 会被封印静默丢弃）──
def inj_bad_level() -> None:
    _patch(RULE, '    level = str(cfg.get("level") or "高风险")', '    level = "涉嫌风险"')


# ── ③ 阈值放宽（全部判匹配 ⇒ 预警永不触发）──
def inj_threshold_zero() -> None:
    _patch(RULE, '    matched_at = float(cfg.get("matched_at") or 0.5)',
           '    matched_at = 0.0')


# ── ④ 反证条被删（规则退化成"超范围即违法"）──
def inj_drop_reversal() -> None:
    _patch(RL, '"企业已依法变更登记、或所营项目属无需许可的一般项目且交易真实的，不认定为本项（属合法且具正当理由的情形）。"',
           '"（未登记反证条）"')


# ── ⑤ 门禁被绕过（不校验项目写权限）──
def inj_no_permission_check() -> None:
    _patch(API, '    _require_perm(session, "project.write")', '    pass')


# ── ⑥ 前端按钮不受控（去掉 data-perm-btn）──
def inj_button_ungated() -> None:
    _patch(HTML, 'data-perm="project.write"\n                      title="按企业全称查询',
           'data-noperm="1"\n                      title="按企业全称查询')


# ── ⑦ 失败语义被破坏（失败也返回 ok=True）──
def inj_fail_silently() -> None:
    _patch(RULE, '        if not scope:\n            receipt["note"] = "未取得经营范围 ⇒ 本项**未参与**（不据此判「无风险」）"\n            return [], receipt',
           '        if not scope:\n            receipt["note"] = "未取得经营范围"\n            scope = "空范围"')
    _patch(CFG, '"unmatched_below": 0.2', '"unmatched_below": 0.99')


CASES = [
    ("① 缓存失效（时间解析不出）", inj_cache_dead, STORE),
    ("② 等级写成展示名（词表外）", inj_bad_level, RULE),
    ("③ 匹配阈值归零", inj_threshold_zero, RULE),
    ("④ 反证条被删", inj_drop_reversal, RL),
    ("⑤ 权限门禁被绕过", inj_no_permission_check, API),
    ("⑥ 按钮去掉权限门控", inj_button_ungated, HTML),
    ("⑦ 缺失经营范围不拦（失败即静默）", inj_fail_silently, RULE),
]


def main() -> int:
    base_rc, base_out = _run()
    tail = base_out.strip().splitlines()[-1] if base_out.strip() else ""
    print("基线：rc=%d %s" % (base_rc, tail))
    if base_rc != 0:
        print("✗ 基线未绿：\n%s" % base_out[-2000:])
        return 2

    results = []
    for name, fn, extra in CASES:
        targets = {STORE, RULE, RL, API, HTML, CFG}
        baks = {}
        for t in targets:
            b = t + ".bak"
            shutil.copy2(t, b)
            baks[t] = b
        try:
            fn()
            rc, out = _run()
            detail = ""
            for line in reversed(out.strip().splitlines()):
                if "failed" in line or "passed" in line:
                    detail = line.strip()
                    break
            results.append({"case": name, "turned_red": rc != 0, "detail": detail})
            print("%s %s → %s" % ("✓" if rc != 0 else "✗", name, detail))
        finally:
            for t, b in baks.items():
                shutil.move(b, t)
                _bump(t)

    after_rc, after_out = _run()
    tail2 = after_out.strip().splitlines()[-1] if after_out.strip() else ""
    print("还原后：rc=%d %s" % (after_rc, tail2))
    ok = all(r["turned_red"] for r in results) and after_rc == 0
    print("\n===== 结论 =====")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    print("反向验证 %d/%d 触发红灯；还原后 %s"
          % (sum(1 for r in results if r["turned_red"]), len(results),
             "绿" if after_rc == 0 else "仍红（异常）"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
