# -*- coding: utf-8 -*-
"""结果级验收：分析作业流水（engine/analysis_jobs.py）。

★ 在**隔离实例**（临时 APP_DATA_DIR 起独立进程）下跑，绝不碰真实项目 data/。
★ 每一条"应该通过"的断言，都配一条**反向验证**（注入缺陷 ⇒ 必须变红），
   否则判据是假的。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")

CHILD = r'''
# -*- coding: utf-8 -*-
import json, os, sys
from pathlib import Path
ROOT = Path(os.environ["CAISHUI_ROOT"])
sys.path.insert(0, str(ROOT))
fails = []
def ok(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ((" | " + str(extra)) if extra else ""))
    if not cond:
        fails.append(name)

from engine import analysis_jobs as AJ
p = AJ.jobs_path()
ok("① 路径跟随 APP_DATA_DIR（不得写真实项目）",
   str(p).startswith(str(Path(os.environ["APP_DATA_DIR"]).resolve())), p)

# ── 正向：一次完整作业（started → finished done）──
AJ.job_started(company_id=77, job_id="jobA", started_by=5, trigger="force",
               force=True, started_at="2026-10-09T10:00:00+08:00",
               data_fingerprint="dfp1", rules_fingerprint="rfp1")
AJ.job_finished("jobA", "done", finished_at="2026-10-09T10:00:07+08:00",
                findings_count=12, overall_level="高", report_doc_no="DOC-77-V1")
jobs = AJ.list_jobs(company_id=77)
ok("② 起一次分析 ⇒ 恰好 1 条作业", len(jobs) == 1, len(jobs))
j = jobs[0] if jobs else {}
ok("③ status=done", j.get("status") == "done", j.get("status"))
ok("④ duration_ms 由流水推导 = 7000", j.get("duration_ms") == 7000, j.get("duration_ms"))
ok("⑤ started_by 非空 = 5", j.get("started_by") == "5", j.get("started_by"))
ok("⑥ trigger 保留 = force", j.get("trigger") == "force", j.get("trigger"))
ok("⑦ findings_count = 12", j.get("findings_count") == 12, j.get("findings_count"))
ok("⑧ overall_level = 高", j.get("overall_level") == "高", j.get("overall_level"))
ok("⑨ is_terminal", j.get("is_terminal") is True)

# ── 重启语义：重新 import 后依然查得到（落盘而非内存）──
import importlib
importlib.reload(AJ)
j2 = AJ.get_job("jobA")
ok("⑩ 重启（重载模块）后按 job_id 仍查得到终态", bool(j2) and j2.get("status") == "done",
   (j2 or {}).get("status"))

# ── 失败作业：错误信息与失败阶段 ──
AJ.job_started(company_id=77, job_id="jobB", started_by=6, trigger="manual",
               started_at="2026-10-09T11:00:00+08:00")
AJ.job_finished("jobB", "error", finished_at="2026-10-09T11:00:03+08:00",
                error_step="domain_analysis", error_message="除零")
jb = AJ.get_job("jobB") or {}
ok("⑪ 失败作业 error_step/error_message 留痕",
   jb.get("status") == "error" and jb.get("error_step") == "domain_analysis"
   and jb.get("error_message") == "除零", jb.get("status"))
ok("⑫ 未完成作业（仅 started）status=running 且 is_terminal=False",
   (AJ.job_started(company_id=78, job_id="jobC", started_by=7) is not None)
   and (AJ.get_job("jobC") or {}).get("status") == "running"
   and (AJ.get_job("jobC") or {}).get("is_terminal") is False)

# ── 终态幂等：重复登记被忽略（同一作业只有一个终点）──
AJ.job_started(company_id=79, job_id="jobD", started_by=8,
               started_at="2026-10-09T12:00:00+08:00")
AJ.job_finished("jobD", "error", company_id=79, finished_at="2026-10-09T12:00:01+08:00")
dup = AJ.job_finished("jobD", "done", company_id=79,
                      finished_at="2026-10-09T12:00:09+08:00", findings_count=3)
jd = AJ.get_job("jobD") or {}
ok("⑬ 终态幂等：重复登记被忽略、首次终态保留(error)",
   dup is None and jd.get("status") == "error" and jd.get("duration_ms") == 1000,
   (dup, jd.get("status"), jd.get("duration_ms")))
_d_lines = [l for l in AJ.jobs_path().read_text(encoding="utf-8").splitlines()
            if '"job_id": "jobD"' in l]
ok("⑬-b 该作业 finished 行恰好 1 条（无覆盖、无双写）",
   len([l for l in _d_lines if '"finished"' in l]) == 1, len(_d_lines))

# ── 分企业隔离 & limit ──
ok("⑭ list_jobs 按企业过滤", len(AJ.list_jobs(company_id=77)) == 2, len(AJ.list_jobs(company_id=77)))
ok("⑮ limit 生效", len(AJ.list_jobs(limit=1)) == 1)

# ── 自检（正向：真实流水应通过）──
problems = AJ.selfcheck()
ok("⑯ selfcheck 在合法流水上通过（空清单）", problems == [], problems)

# ── 删除（"删了就是真删了"：含终态行一起删净）──
_before = len([l for l in AJ.jobs_path().read_text(encoding="utf-8").splitlines()
               if '"company_id": "77"' in l])
n = AJ.remove_company_jobs(77)
ok("⑰ 删除企业 77 的行数 = 删除前实测行数", n == _before and n > 0, (n, _before))
ok("⑱ 删除后读不到任何残留（内存与磁盘都无）",
   AJ.list_jobs(company_id=77) == [] and AJ.get_job("jobA") is None)
raw = AJ.jobs_path().read_text(encoding="utf-8")
ok("⑲ 磁盘原文里也查不到 77 的作业 id 与 company_id",
   "jobA" not in raw and "jobB" not in raw and '"company_id": "77"' not in raw)
ok("⑳ 其它企业作业不受影响", len(AJ.list_jobs(company_id=78)) == 1)

# ══ 反向验证：注入缺陷 ⇒ 自检必须变红 ══
with open(AJ.jobs_path(), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"schema": 1, "event": "finished", "job_id": "GHOST",
                         "company_id": "999", "status": "done",
                         "finished_at": "2026-10-09T13:00:00+08:00"},
                        ensure_ascii=False) + "\n")
bad = AJ.selfcheck()
ok("R1 反向：有终态无起点 ⇒ 自检变红",
   any("没有起点" in x for x in bad), [x for x in bad if "没有起点" in x])
with open(AJ.jobs_path(), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"schema": 1, "event": "finished", "job_id": "GHOST2",
                         "company_id": "999", "status": "bogus",
                         "started_at": "2026-10-09T13:00:00+08:00",
                         "finished_at": "2026-10-09T13:00:01+08:00"},
                        ensure_ascii=False) + "\n")
bad = AJ.selfcheck()
ok("R2 反向：非终态被记为 finished ⇒ 自检变红",
   any("非终态" in x for x in bad), [x for x in bad if "非终态" in x])
with open(AJ.jobs_path(), "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"schema": 1, "event": "started", "job_id": "GHOST3",
                         "company_id": "999", "started_by": "",
                         "started_at": "2026-10-09T13:00:00+08:00",
                         "trigger": "manual"},
                        ensure_ascii=False) + "\n")
bad = AJ.selfcheck()
ok("R2-b 反向：缺少发起人 ⇒ 自检变红",
   any("缺少发起人" in x for x in bad), [x for x in bad if "缺少发起人" in x])

# ══ 反向验证：写失败绝不静默 ══
AJ.RAISE_ON_WRITE_ERROR = True
import engine.analysis_jobs as _AJ2
_orig = _AJ2._append_row
_AJ2._append_row = lambda row: (_ for _ in ()).throw(IOError("磁盘满"))
raised = False
try:
    AJ.job_started(company_id=80, job_id="jobE", started_by=9)
except Exception as e:
    raised = True
ok("R3 反向：写入失败 ⇒ 抛异常（不静默）", raised)
ok("R4 反向：写入失败 ⇒ last_error 留痕", bool(AJ.last_error()), AJ.last_error())
_AJ2._append_row = _orig

# ══ 反向验证：报告合规装配失败的根因（`json.dumps` 遇 set）═══
#   证明两件事：① 原缺陷真实存在（裸 dumps 必抛）；② 采用的修法口径真的有效。
_blob = {"compliance": {"document": {"name": "工作底稿"}},
         "enterprise_readable_report": {"tags": {"增值税", "印花税"}, "n": 1}}
_raised_bare = False
try:
    import json as _J
    _J.loads(_J.dumps(_blob))
except TypeError:
    _raised_bare = True
ok("R5 反向：裸 json.dumps 遇到 set 必抛 TypeError（原缺陷真实存在）", _raised_bare)
from runtime_storage import _to_json_safe as _jss
_ok_fix = False
try:
    _out = _jss(_blob)
    _ok_fix = isinstance(_out, dict) and isinstance(_out["enterprise_readable_report"]["tags"], list)
except Exception as e:                           # noqa: BLE001
    _ok_fix = False
ok("R6 修复口径 runtime_storage._to_json_safe 能序列化含 set 的报告", _ok_fix)

print("FAILS=%d" % len(fails))
sys.exit(1 if fails else 0)
'''


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="ajobs_")
    env = dict(os.environ)
    env["APP_DATA_DIR"] = tmp
    env["CAISHUI_ROOT"] = str(ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    print("隔离实例 APP_DATA_DIR =", tmp)
    r = subprocess.run([PY, "-c", CHILD], env=env, capture_output=True, text=True,
                       encoding="utf-8", cwd=str(ROOT))
    print(r.stdout or "")
    if r.stderr.strip():
        print("--- stderr ---")
        print(r.stderr[-2000:])
    produced = Path(tmp) / "analysis_jobs.jsonl"
    print("产物文件存在:", produced.exists(),
          ("大小=%d" % produced.stat().st_size) if produced.exists() else "")
    print("真实数据目录未被写入:", not (ROOT / "data" / "analysis_jobs.jsonl").exists()
          or "（已存在，请核对是否本次产生）")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
