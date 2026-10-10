# -*- coding: utf-8 -*-
"""一次性数据迁移：把 rulelist_v11.json 的字段名对齐 rulelist_v1.json（单一权威风格）。

为什么必须做：两张数据表若用两套字段名（v1: src/sev/status/by ｜ v11: id/level/coverage/mapped_to），
下游（导出器 / 闸门 / 报告）就得写两套分支 —— 这正是项目反复出事故的「多头维护」根因。
本脚本把 v11 归一为 v1 的字段名，并给两表补齐 `action`（处理方式）与 `params_ref`（阈值指针）。

- src       规则 ID（原 v11 的 id）
- name      规则名
- sev       等级 high/medium/low（原 v11 的中文 高/中/低）
- status    covered / partial / missing（原 v11 的 coverage）
- by        对应系统实现（原 v11 的 mapped_to）
- action    keep_existing / merge / add / drop（V1.0 由 status 推导，V1.1 自带）
- note      备注
- params_ref 指向阈值登记处（不内联数值）

跑完逐项断言命中数，不符即失败（防静默改坏）。
"""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent
V1 = ROOT / "config" / "rulelist_v1.json"
V11 = ROOT / "config" / "rulelist_v11.json"

SEV_MAP = {"高": "high", "中": "medium", "低": "low"}
STATUS_TO_ACTION = {"covered": "keep_existing", "partial": "merge", "missing": "add"}


def _norm_v11() -> None:
    d = json.loads(V11.read_text(encoding="utf-8"))
    rules = d["rules"]
    out = []
    for r in rules:
        sev = r.get("sev") or SEV_MAP.get(r.get("level"), None)
        assert sev in ("high", "medium", "low"), "等级无法归一: %s" % r
        status = r.get("status") or r.get("coverage")
        assert status in ("covered", "partial", "missing"), "覆盖状态非法: %s" % r
        item = {
            "src": r.get("src") or r.get("id"),
            "name": r["name"],
            "sev": sev,
            "status": status,
            "by": r.get("by") or r.get("mapped_to") or "",
            "action": r.get("action") or STATUS_TO_ACTION[status],
            "params_ref": "config/rulelist_v11.json::params.%s" % (r.get("src") or r.get("id")),
        }
        if r.get("note"):
            item["note"] = r["note"]
        out.append(item)
    # 断言：条数不变、ID 唯一
    ids = [x["src"] for x in out]
    assert len(out) == 174, "条数变了: %d" % len(out)
    assert len(set(ids)) == 174, "ID 有重复"
    d["rules"] = out
    V11.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[V1.1] 已归一 174 条；status 分布:", dict(Counter(x["status"] for x in out)))
    print("[V1.1] action 分布:", dict(Counter(x["action"] for x in out)))


def _patch_v1() -> None:
    d = json.loads(V1.read_text(encoding="utf-8"))
    rules = d["rules"]
    n_action = 0
    for r in rules:
        if not r.get("action"):
            r["action"] = STATUS_TO_ACTION[r["status"]]
            n_action += 1
        if not r.get("params_ref"):
            r["params_ref"] = "config/rulelist_v1.json::params.%s" % r["src"]
        # 统一 sev 为英文（V1.0 本就是英文，做一次自检）
        assert r["sev"] in ("high", "medium", "low"), "V1.0 sev 异常: %s" % r
    d["supplement"] = "config/rulelist_v11.json（V1.1 补充规则集 174 条的分册；V1.0 + V1.1 合计 234 条）"
    V1.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[V1.0] 补 action %d 条 / params_ref %d 条；status 分布:" % (n_action, len(rules)),
          dict(Counter(x["status"] for x in rules)))


if __name__ == "__main__":
    _norm_v11()
    _patch_v1()
    # 交叉校验：两表 ID 无冲突
    a = {r["src"] for r in json.loads(V1.read_text(encoding="utf-8"))["rules"]}
    b = {r["src"] for r in json.loads(V11.read_text(encoding="utf-8"))["rules"]}
    clash = a & b
    print("两表 ID 冲突:", sorted(clash) or "无 ✓")
    print("合计候选规则:", len(a) + len(b))
