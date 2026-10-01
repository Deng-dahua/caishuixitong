# -*- coding: utf-8 -*-
"""RL-SPT-012 专用 detectors 的**反向验证**：故意破坏 → 闸门必须变红。

纪律（2026-10-01 血泪总结）：
  1. 破坏点必须打准（锚点字节级匹配，中文锚点一律用 ESCAPE 纯 ASCII 探针）；
  2. 破坏方向要能**反转语义**（关死闸门 = 恒假/恒真都会造成假绿，必须让被守护的行为反过来）；
  3. 破坏后必须 os.utime(未来) + PYTHONDONTWRITEBYTECODE=1，否则可能读到缓存/py 文件；
  4. 备份只放 scripts/_bak/（放 engine/ 会被 audit 判成第二套实现）。

用法：python scripts/_reverse_verify_rlspt012.py
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "engine", "special_redline_detectors.py")
TEST = os.path.join(ROOT, "tests", "test_special_redline_detectors.py")
BAK = os.path.join(ROOT, "scripts", "_bak")
PY = sys.executable

CR = chr(13) + chr(10)
# ── 纯 ASCII 探针（中文一律转义，规避 Write/Edit 把字节写成字面双反斜杠）──
P_EXTRA_LOOP = ("for _extra in _EXTRA_DETECTORS:").encode("utf-8")
P_PAY_ANY = ("if any(k in pay_text for k in _EQUITY_PAY_EVIDENCE):").encode("utf-8")
P_REDLINE_ID = ('redline_id = "RL-SPT-012"').encode("utf-8")
P_FINDING = ("redline_id, topic, \"个人所得税\", detail,").encode("utf-8")
P_HITS = ("hits = [k for k in _EQUITY_SIGNALS if k in src_text]").encode("utf-8")

CASES = [
    # (编号, 描述, 目标文件, 原字节, 破坏后字节, 期望变红的测试)
    ("C1", "运行器不再遍历 _EXTRA_DETECTORS（专用探测器变死代码）",
     TARGET, P_EXTRA_LOOP, b"if True:", "test_extra_detectors_are_invoked_by_runner"),
    ("C2", "完税凭证反证失效（已申报也会置疑）",
     TARGET, P_PAY_ANY, b"if False:", "test_tax_paid_evidence_suppresses"),
    ("C3", "生产代码里丢掉 redline_id 字面量登记（覆盖审计认领不到）",
     TARGET, P_REDLINE_ID, b'redline_id = ""', "test_rlspt012_declared_in_production_source"),
    ("C4", "信号判定恒空（有股权转让线索也不产出）",
     TARGET, P_HITS, b"hits = []", "test_fires_on_equity_change_signal"),
    ("C5", "把银行手续费当'涉及金额'报出去",
     TARGET, P_FINDING,
     ('redline_id, topic, "个人所得税", detail + "涉及金额 1000 元",').encode("utf-8"),
     "test_reports_count_but_not_amount"),
]


def run_test(one=None):
    """跑目标测试，返回 (returncode, 是否被该测试判红, stdout, stderr)。

    判红口径(防止假绿)：必须 rc != 0 **且** 输出里出现该用例节点名；
    若整文件因 import/收集错误全挂，节点名不会出现 => 判为"未变红"，逼人工复核。
    """
    # ★ 坑：节点选择器必须和文件拼成**同一个 argv 元素**，
    #   拆成两个参数时 pytest 会报 "directory argument cannot contain :: selection parts"(rc=4)。
    args = [PY, "-m", "pytest", "-q",
            "tests/test_special_redline_detectors.py"
            + (("::EquityTransferIITTests::" + one) if one else "")]
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = "."
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, env=env,
                       encoding="utf-8", errors="replace", timeout=300)
    out = p.stdout or ""
    saw_red = (one is None) or (one in out)
    return p.returncode, saw_red, out, (p.stderr or "")


def touch_future(path):
    t = time.time() + 120
    os.utime(path, (t, t))


def main():
    if not os.path.isdir(BAK):
        os.makedirs(BAK)
    bak_target = os.path.join(BAK, "_srd_cur.py")
    bak_test = os.path.join(BAK, "_srd_tests_cur.py")
    open(bak_target, "wb").write(open(TARGET, "rb").read())
    open(bak_test, "wb").write(open(TEST, "rb").read())
    print("backup ->", bak_target, bak_test)

    base_rc, _, _, _ = run_test()
    print("基线: pytest returncode =", base_rc)
    if base_rc != 0:
        print("[ABORT] 基线不是全绿，反向验证无意义")
        return 1

    ok = 0
    for cid, desc, path, old, new, want_test in CASES:
        raw = open(path, "rb").read()
        if old not in raw:
            print("  [%s SKIP] 破坏点未命中：%s" % (cid, desc))
            continue
        open(path, "wb").write(raw.replace(old, new, 1))
        touch_future(path)
        rc, saw_red, out, err = run_test(want_test) if want_test else run_test()
        if rc != 0 and not saw_red:
            print("    --- 子进程输出诊断(防止假绿) ---")
            for tag, blob in (("stdout", out), ("stderr", err)):
                for line in blob.replace("\r", "").rstrip().split("\n")[-8:]:
                    print("    [%s] %s" % (tag, line))
            print("    --- 诊断结束 ---")
        if rc != 0 and saw_red:
            print("  [%s OK] %s => %s 变红 (rc=%d)" % (cid, desc, want_test, rc))
            ok += 1
        else:
            print("  [%s FAIL] %s => 未变红 (rc=%d)" % (cid, desc, rc))
        # 还原
        open(path, "wb").write(raw)
        touch_future(path)

    touch_future(TEST)
    rc, _, _, _ = run_test()
    print("还原后: pytest returncode =", rc)

    print("\n结果：%d/%d 破坏即红" % (ok, len(CASES)))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
