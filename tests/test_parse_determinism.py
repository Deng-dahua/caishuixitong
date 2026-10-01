# -*- coding: utf-8 -*-
"""可复现性闸门：同一份工资表在不同 Python hash 种子下必须解析出**完全相同**的行。

★ 背景（2026-10-01 真实事故，P0 可复现性）：
  `main._find_cols_semantic` 第 2 轮用 `set(mapping.values())` 决定字段处理顺序，
  而落列规则是「先处理者占列、后来者跳过」——`set` 顺序随 hash 随机化变化，
  于是两个字段竞争同一列时归属翻转（实测：工资表 `tax`(代扣个税) 与 `gross`(应发) 互换），
  进而使「个税三源勾稽」金额/差异变化、发现数在 159/162/163 间波动。
  已修：改为 `dict.fromkeys(...)`（有序去重，映射表声明顺序即优先级）。

★ 本闸门为何必须存在：
  该缺陷**语法合法、单测全绿**，只有「同输入重复跑并比对」才暴露。
  故用两个不同 `PYTHONHASHSEED` 的子进程各解析一次真实工资表，逐字节比对行内容。

判据：两次输出哈希相同 → 通过；不同 → ERROR（说明解析仍依赖无序容器顺序）。
依赖真实上传资料；若本地无工资表 `.xls`，则跳过（避免环境依赖导致假红）。
"""
import hashlib
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

_PROBE = r"""
import io, json, os, sys
os.chdir(r"{root}")
sys.path.insert(0, r"{root}")
from engine.workbook import load_workbook, close_workbook
import main
path = r"{f}"
wb = load_workbook(path)
try:
    sh = wb.sheet_by_index(0) if hasattr(wb, "sheet_by_index") else wb.active
    res = main._parse_salary_sheet(sh) or dict()
    print(json.dumps(res.get("rows") or [], ensure_ascii=False, sort_keys=True))
finally:
    close_workbook(wb)
"""


def _find_salary_file():
    updir = os.path.join(ROOT, "data", "uploads")
    if not os.path.isdir(updir):
        return None
    for cid in sorted(os.listdir(updir)):
        d = os.path.join(updir, cid)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.lower().endswith((".xls", ".xlsx")) and "工资" in fn:
                return os.path.join(d, fn)
    return None


def _parse_with_seed(path, seed):
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = str(seed)
    code = _PROBE.format(root=ROOT.replace("\\", "\\\\"), f=path.replace("\\", "\\\\"))
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True, env=env, timeout=300)
    out = (r.stdout or "").strip().splitlines()
    if not out:
        raise RuntimeError("子进程无输出；stderr=%s" % (r.stderr or "")[-600:])
    return hashlib.sha256(out[-1].encode("utf-8")).hexdigest()


class ParseDeterminismTests(unittest.TestCase):
    def test_salary_parse_is_hash_seed_independent(self):
        path = _find_salary_file()
        if not path:
            self.skipTest("本地无工资表样本（data/uploads/*/*工资*），跳过可复现性闸门")
        h1 = _parse_with_seed(path, 0)
        h2 = _parse_with_seed(path, 1)
        self.assertEqual(
            h1, h2,
            "工资表解析结果随 Python hash 种子变化（%s vs %s）——"
            "解析路径仍存在「用无序容器决定顺序」的缺陷（见 main._find_cols_semantic 的历史修复）。" % (h1[:12], h2[:12]))


if __name__ == "__main__":
    unittest.main()
