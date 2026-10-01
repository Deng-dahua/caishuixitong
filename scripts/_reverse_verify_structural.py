# -*- coding: utf-8 -*-
"""反向验证：把本轮新增的「结构性证据层 / 命中层自动裁决」闸门**故意破坏**，
确认对应测试**真的变红**。

★ 为什么必须做（2026-10-01 教训复盘，本库踩过三次）：
  1) 破坏点必须打准 —— 曾把「排除 svc 过滤」与「排除购销兜底口径」混为一谈 ⇒ 假绿；
  2) 破坏后必须 `os.utime(path, 未来时间)` —— 否则源与 .pyc 同秒，Python 复用旧字节码，
     探针与 pytest 都跑旧码 ⇒ 反向验证全是假的（PYTHONDONTWRITEBYTECODE=1 只挡写不挡读）；
  3) 探针命令必须**纯 ASCII** —— `python -c` 的中文参数经 Windows 控制台代码页会变 `?` ⇒ 假绿。

用法：
    .venv/Scripts/python.exe scripts/_reverse_verify_structural.py
"""
import os
import shutil
import subprocess
import sys
import time

ROOT = os.getcwd()
PY = sys.executable
TF = os.path.join("tests", "test_account_classifier.py")
BAK_DIR = os.path.join("scripts", "_bak")
os.makedirs(BAK_DIR, exist_ok=True)

# ★ 探针纯 ASCII（中文一律用 _esc 转成 \uXXXX），并屏蔽 .pyc 缓存
ENV = dict(os.environ)
ENV["PYTHONDONTWRITEBYTECODE"] = "1"
ENV["PYTHONIOENCODING"] = "utf-8"


def _esc(s):
    return "".join("\\u%04x" % ord(c) if ord(c) > 127 else c for c in s)


def _bpath(rel):
    return os.path.join(BAK_DIR, os.path.basename(rel) + ".bak")


def _snap(rel):
    dst = _bpath(rel)
    if not os.path.exists(dst):
        shutil.copy2(rel, dst)
    return dst


def _write_future(rel):
    """写盘后把 mtime 推到未来，确保 Python 一定重编译（见文件头教训 ②）。"""
    fut = time.time() + 120
    os.utime(rel, (fut, fut))


def _run_test(test_id):
    cmd = [PY, "-m", "pytest", "tests/test_account_classifier.py::" + test_id,
           "-q", "--no-header", "-p", "no:cacheprovider"]
    p = subprocess.run(cmd, cwd=ROOT, env=ENV, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, timeout=600)
    return p.returncode != 0, p.stdout.decode("utf-8", "replace")[-600:]


CASES = [
    {
        "id": "C1 业态闸门（服务型无存货 ⇒ 运输/搬运不得判成本）",
        "file": os.path.join("engine", "account_classifier.py"),
        # ★ 破坏方向：**反转**业态条件（not in → in），让闸门"永远放行"、服务型也被判成成本。
        #   （反面教材：先前的破坏写成 `not kw or True:` —— 那个式子恒真 ⇒ 恒 return None，
        #     等于把闸门**关死**，行为反而更保守 ⇒ 测试照样绿，是彻头彻尾的假绿。）
        "anchor": "if not kw or _business_category(ind_list) not in (\"贸易型\", \"生产型\"):".encode("utf-8"),
        "broken": "if not kw or _business_category(ind_list) in (\"贸易型\", \"生产型\"):".encode("utf-8"),
        "test": "test_inventory_support_not_cost_in_service_industry",
    },
    {
        "id": "C2 服务轨道入口（结构性定性为无实物 ⇒ 走服务轨道）",
        "file": os.path.join("engine", "account_classifier.py"),
        "anchor": b"if _kind in (KIND_SERVICE, KIND_PREPAID, KIND_AGENCY):",
        "broken": b"if False:",
        "test": "test_service_purchase_never_cost_by_business_type_fallback",
    },
    {
        "id": "C3 fieldkit 真列名（真实列名是「税收编码」）",
        "file": os.path.join("engine", "fieldkit.py"),
        "anchor": b'"tax_code", "\xe7\xa8\x8e\xe6\x94\xb6\xe7\xbc\x96\xe7\xa0\x81",',
        "broken": b'"tax_code", "',
        "test": "test_fieldkit_tax_code_of_reads_the_real_column",
    },
    {
        "id": "C4 classify_lines 把结构性证据带进权威层",
        "file": os.path.join("engine", "account_classifier.py"),
        "anchor": b'tax_code=ln.get("tax_code")',
        "broken": b'tax_code="",',
        "test": "test_classify_lines_forwards_structural_fields",
    },
    {
        "id": "C5 管道 _agg_invs 保住 tax_code/unit/biz_type",
        "file": os.path.join("engine", "pipeline.py"),
        "anchor": b'for _sk, _getter in (("tax_code", _tc_of), ("unit", _u_of), ("biz_type", _bt_of)):',
        "broken": b"for _sk, _getter in ():",
        "test": "test_pipeline_agg_keeps_structural_fields",
    },
]


def main():
    ok = 0
    for cs in CASES:
        rel = cs["file"]
        _snap(rel)
        with open(rel, "rb") as fh:
            src = fh.read()
        if cs["anchor"] not in src:
            print("[SKIP] %s —— 锚点未命中（破坏点打错 => 反向验证无意义）: %s" % (cs["id"], rel))
            continue
        with open(rel, "wb") as fh:
            fh.write(src.replace(cs["anchor"], cs["broken"], 1))
        _write_future(rel)
        turned_red, tail = _run_test(cs["test"])
        with open(rel, "wb") as fh:
            fh.write(src)
        _write_future(rel)
        status = "OK  破坏即红" if turned_red else "*** 假绿！破坏后测试仍绿 ***"
        if turned_red:
            ok += 1
        print("[%s] %s\n        → %s" % ("PASS" if turned_red else "FAIL", cs["id"],
                                         status.replace("\n", " ")))
        if not turned_red:
            print("        " + tail.replace("\n", "\n        ")[:400])
    print("\n%d/%d 条守卫通过反向验证（备份在 %s）" % (ok, len(CASES), BAK_DIR))
    return 0 if ok == len(CASES) else 1


if __name__ == "__main__":
    sys.exit(main())
