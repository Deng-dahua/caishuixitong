# -*- coding: utf-8 -*-
"""反向验证：行业「随资料再判读」的四条守卫，故意破坏后必须让对应测试变红。

纪律：只要守卫没被真的触发过，闸门就是假的。备份一律放 scripts/（勿放 engine/）。
"""
import io
import os
import time
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
ENGINE = os.path.join(ROOT, "engine", "industry_resolver.py")
PIPE = os.path.join(ROOT, "engine", "pipeline.py")
BAK_E = os.path.join(ROOT, "scripts", "_bak_reassess_engine.py")
BAK_P = os.path.join(ROOT, "scripts", "_bak_reassess_pipeline.py")


def read_raw(p):
    return io.open(p, "rb").read()


def _env():
    """★ 必须关掉 pyc：破坏若落在同一秒内，Python 会复用旧 .pyc，
    探针与 pytest 看到的是**没被破坏**的代码 —— 反向验证就成了假验证。"""
    e = {**os.environ, "PYTHONPATH": ".", "PYTHONDONTWRITEBYTECODE": "1"}
    return e


def write_raw(p, b):
    with io.open(p, "wb") as f:
        f.write(b)
    return len(b)


def run_case(testid):
    r = subprocess.run([PY, "-m", "pytest", "tests/test_industry_resolver.py::"
                        "TestReassessIndustry::%s" % testid, "-q"],
                       cwd=ROOT, capture_output=True, text=True,
                       env=_env())
    print("      [diag] rc=%s | %s" % (
        r.returncode, (r.stdout or "").strip().splitlines()[-1][:120]
        if (r.stdout or "").strip() else "(no stdout)"))
    return r.returncode == 0


def _esc(s):
    return "".join("\\u%04x" % ord(c) for c in s)


ESC_FEED = _esc("饲料")        # 商品名（铁律 R1：不得当行业）
ESC_TIE = _esc("饲料采购单.docx")


CASES = [
    ("高权威门槛（单路不得推翻）", ENGINE,
     b"enough = (top_routes >= 2) or (is_fallback and top_routes >= 1)",
     b"enough = True",
     "test_high_authority_not_overturned_by_single_route"),
    ("并票无共识（并列不得变更）", ENGINE,
     b"if len(tied) > 1:",
     b"if False:",
     "test_tie_has_no_consensus"),
    # ★ 破坏点必须命中 **svc 过滤**（商品名不算行业/R1）：
    #   把 `v not in svc` 抹掉，production_industries 的商品（饲料→农业生产）就会被当行业。
    ("商品名不算行业（R1）", ENGINE,
     b"if not v or v not in svc or v in _TRADE_FALLBACK_INDUSTRIES:",
     b"if not v or v in _TRADE_FALLBACK_INDUSTRIES:",
     "test_commodity_names_never_count_as_industry"),
    ("主链路接线（防退回一次性定死）", PIPE,
     b"from engine.industry_resolver import reassess_industry as _reassess",
     b"from engine.industry_resolver import reassess_industry as _reassess_DISABLED",
     "test_reverse_pipeline_call_site_wired"),
]


def main():
    shutil.copyfile(ENGINE, BAK_E)
    shutil.copyfile(PIPE, BAK_P)
    ok = True
    try:
        for name, path, old, new, testid in CASES:
            raw = read_raw(path)
            if old not in raw:
                print("SKIP  %-28s (anchor missing)" % name)
                ok = False
                continue
            _w = write_raw(path, raw.replace(old, new, 1))
            # ★ 关键：把 mtime 推到未来。否则破坏后的源与已有 .pyc 落在同一秒，
            #   Python 会判定 pyc 仍有效、继续用**没被破坏**的旧字节码 ——
            #   反向验证会假绿（或假红）。仅设 PYTHONDONTWRITEBYTECODE 不够，因为它只挡写、不挡读。
            os.utime(path, (time.time() + 30, time.time() + 30))
            _chk = read_raw(path)
            print("      [diag] 落盘校验 old=%d/new=%d bytes=%d" % (
                _chk.count(old), _chk.count(new), _w))
            # 破坏是否真的影响运行期行为：直接调用一次看决策。
            # ★ 探针必须 **纯 ASCII**：python -c 的中文参数经 Windows 控制台代码页会被
            #   替换成 '?'，探针会假绿。行业名/关键词一律写成 \\uXXXX 转义。
            _probe = subprocess.run(
                [PY, "-c",
                 "from engine.industry_resolver import reassess_industry as R;"
                 "r=R(current_industry='IT',purchase_goods=['" + ESC_FEED + "'],"
                 "material_hints=['" + ESC_TIE + "'],current_source='invoice');"
                 "print('PROBE', r['decision'], r['industry'])"],
                cwd=ROOT, capture_output=True, text=True,
                env={**_env(), "PYTHONIOENCODING": "utf-8"})
            print("      [diag] 子进程探针: %s" % (_probe.stdout.strip() or _probe.stderr[-200:]))
            # 同进程探针（子进程探针受 Windows 控制台代码页/编码影响，仅作交叉核对）
            try:
                import importlib
                _m = importlib.import_module("engine.industry_resolver")
                _r = _m.reassess_industry(
                    current_industry="IT",
                    purchase_goods=["饲料"],
                    material_hints=["饲料采购单.docx"],
                    current_source="invoice")
                print("      [diag] 同进程探针: %s | %s"
                      % (_r["decision"], _r["industry"]))
            except Exception as _pe:
                print("      [diag] 同进程探针异常: %s" % _pe)
            passed = run_case(testid)
            verdict = "FAIL(红)" if not passed else "PASSED(绿) —— 守卫没生效！"
            print("%-28s → 破坏后 %s" % (name, verdict))
            if passed:
                ok = False
            write_raw(path, read_raw(BAK_E if path == ENGINE else BAK_P))
    finally:
        write_raw(ENGINE, read_raw(BAK_E))
        write_raw(PIPE, read_raw(BAK_P))
    print("\n结论：%s" % ("四条守卫反向验证全部成立（破坏即红）" if ok else
                          "有守卫未生效，闸门是假的，必须修"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
