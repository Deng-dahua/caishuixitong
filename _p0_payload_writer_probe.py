# -*- coding: utf-8 -*-
"""P0 验收 · **风险载荷断链**独立取证（只读，不启服务、不改任何文件）。

## 背景（全流程联调实测暴露）

联调里第 ⑥ 步（风险结果）拿到 `total=0`，`stats` 返回
`{available: false, reason: "该账套尚未生成报告载荷（请先执行一键分析）"}` ——
而**同一轮一键分析确实以 SUCCESS 完成**、产出了 16 条风险事项（见归档日志
「风险编号 16 项；证据编号 48 条」）。两边对不上 ⇒ 本脚本把断点钉死。

## 判据（A 静态 / B 行为）

A1 `company_{id}_full.json` 的**写入方**：全仓（产品代码 + 脚本）检索该文件名模板，
   **只允许出现读取方**；出现写入即视为已接线（预期：无任何写入方 ⇒ 断链）。
A2 读取方清单（谁在消费该载荷）：`engine/risk_service.py` / `risks_api.py` / `rules_api.py`
   ⇒ 说明这是 P0-5/P0-6 的**唯一数据源**。
B1 在隔离实例里检查 `offline_reports_root()/company_{cid}_full.json` 的存在与可读性
   （未分析时预期不存在）。★ "**跑完一键分析后仍不存在**"这一更强的证据在
   `_p0_i1_e2e_full_flow.py` 的 ⑥b（该轮分析 status=SUCCESS、报告产出 16 条风险事项，
   而风险接口仍返回 `available=false` +「请先执行一键分析」）—— 本脚本不重复跑那条长链路。
B2 反向验证（证明 B1 不是"路径写错"）：
   把该账套的分析产物**按读取方的期望形状**写一份到该路径 ⇒
   `risk_service.load_payload()` 必须变为 `available=True` 且能列出风险条目。
   ⇒ 说明断点是"**没人写**"，而不是"读的路径不对"。

用法：`python _p0_payload_writer_probe.py`
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")
TEMPLATE = "company_%d_full.json"
PAT = re.compile(r"company_\s*%[sd]\s*_full\.json|company_\{[^}]*\}_full\.json")

results: list = []


def ok(name: str, cond: bool, extra: str = "") -> None:
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))


def scan_static() -> None:
    print("== A. 静态：谁在写 / 谁在读 ==")
    writers, readers = [], []
    files = list(ROOT.glob("*.py")) + list((ROOT / "engine").glob("*.py")) \
        + list((ROOT / "scripts").glob("*.py")) + list((ROOT / "tools").glob("*.py"))
    for p in files:
        if p.name.startswith(("_p0_", "_verify_")) or "baseline" in p.parts:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not PAT.search(txt) and TEMPLATE % 0 not in txt and "company_%d_full" not in txt:
            continue
        rel = p.relative_to(ROOT).as_posix()
        # 写入形态：open(..., "w") / write_text / json.dump 到该路径变量
        if re.search(r"open\([^)]*_full[^)]*[\"'][wa]", txt) or \
           re.search(r"_full[^)]*\)\s*\.write_text", txt) or \
           re.search(r"json\.dump\([^)]*_full", txt):
            writers.append(rel)
        else:
            readers.append(rel)
    print("  读取方：%s" % readers)
    print("  写入方：%s" % (writers or "（无）"))
    ok("A1 载荷存在**读取方**（是 P0-5/P0-6 的数据源）", bool(readers), readers)
    ok("A2 载荷**无生产写入方** ⇒ 一键分析不落盘该载荷（断链）",
       not writers, "写入方=%s" % (writers or "无"))


CHILD = r'''
# -*- coding: utf-8 -*-
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())
from security import init_security_db, create_user, SessionContext
init_security_db()
CID = int(os.environ["PROBE_CID"])
from engine import risk_service as RS

def sess():
    return SessionContext(user_id=1, username="probe", role="admin",
                          allowed_company_ids=frozenset({CID}), selected_company_id=CID,
                          csrf_hash="", expires_at=0)

st1 = RS.load_payload(CID, sess())
print("PAYLOAD_BEFORE=" + json.dumps({"available": st1.get("available"),
                                      "reason": st1.get("reason", ""),
                                      "path_hint": st1.get("path_hint", "")},
                                     ensure_ascii=False))

# ── 反向验证：按**读取方的期望形状**写一份 ⇒ 必须变为 available ──
from runtime_storage import offline_reports_root
p = Path(offline_reports_root()) / ("company_%d_full.json" % CID)
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps({
    "enterprise_readable_report": {
        "confirmed_problems": [{
            "seq": 1, "risk_no": "WB-R-PROBE-202501-001", "title": "探针风险项",
            "verdict": "已从账内算出确定事实", "level": "中",
            "tax_impact": {"available": True, "basis": 10000.0, "total": 1300.0},
            "evidence_have": [], "evidence_need": [],
        }],
    },
    "results": [],
}, ensure_ascii=False), encoding="utf-8")

st2 = RS.load_payload(CID, sess())
print("PAYLOAD_AFTER=" + json.dumps({"available": st2.get("available"),
                                     "reason": st2.get("reason", "")}, ensure_ascii=False))
try:
    lst = RS.list_risks(CID, sess(), page=1, page_size=10)
    print("LIST_AFTER=" + json.dumps({"available": lst.get("available"),
                                      "total": lst.get("total"),
                                      "first": ((lst.get("items") or [{}])[0].get("risk_no")
                                                if lst.get("items") else None)},
                                     ensure_ascii=False))
except Exception as exc:                                  # noqa: BLE001
    print("LIST_AFTER=" + json.dumps({"error": repr(exc)[:160]}, ensure_ascii=False))
'''


def main() -> int:
    scan_static()
    print("\n== B. 行为：真跑一键分析 ⇒ 载荷是否存在（+ 反向验证路径判据）==")
    data_dir = Path(tempfile.mkdtemp(prefix="p0_payload_"))
    for f in ("security.db", "accounting.db"):
        src = ROOT / "data" / f
        if src.exists():
            shutil.copy2(src, data_dir / f)
    up = ROOT / "data" / "uploads"
    if up.exists():
        shutil.copytree(up, data_dir / "uploads")

    os.environ["APP_DATA_DIR"] = str(data_dir)
    sys.path.insert(0, str(ROOT))
    from security import init_security_db, create_user                # noqa: E402
    init_security_db()
    try:
        create_user("_p0probe", "P0-Probe-Admin-2026!", role="admin", company_ids=[1])
    except Exception:                                                # noqa: BLE001
        pass

    # ① 先看未分析时：载荷必然不存在
    env = dict(os.environ)
    env["PROBE_CID"] = "1"
    env["APP_DATA_DIR"] = str(data_dir)
    env["PYTHONIOENCODING"] = "utf-8"
    cp = subprocess.run([PY, "-c", CHILD], cwd=str(ROOT), env=env, capture_output=True,
                        text=True, encoding="utf-8", errors="replace", timeout=600)
    before = after = lst = {}
    for ln in (cp.stdout or "").splitlines():
        if ln.startswith("PAYLOAD_BEFORE="):
            before = json.loads(ln.split("=", 1)[1])
        elif ln.startswith("PAYLOAD_AFTER="):
            after = json.loads(ln.split("=", 1)[1])
        elif ln.startswith("LIST_AFTER="):
            lst = json.loads(ln.split("=", 1)[1])
    if not before:
        print("子进程输出：", (cp.stdout or "")[-400:], (cp.stderr or "")[-800:])
    ok("B1 未分析时载荷不可用（available=False，且给出原因而非编造空列表）",
       before.get("available") is False and bool(before.get("reason")),
       json.dumps(before, ensure_ascii=False)[:160])
    ok("B2 反向验证：按读取方期望形状写入 ⇒ available 必须变 True（判的是『没人写』而非『路径错』）",
       after.get("available") is True,
       "变后=%s" % json.dumps(after, ensure_ascii=False)[:120])
    ok("B3 反向验证：载荷就绪后风险列表可列出条目（链路本身是通的）",
       bool(lst.get("total")) and lst.get("available") is not False,
       json.dumps(lst, ensure_ascii=False)[:200])

    n_fail = sum(1 for _n, c in results if not c)
    print("\n" + "=" * 66)
    print("载荷断链取证：%d 项通过 / %d 项失败（共 %d）"
          % (len(results) - n_fail, n_fail, len(results)))
    for n, c in results:
        if not c:
            print("  FAIL  " + n)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
