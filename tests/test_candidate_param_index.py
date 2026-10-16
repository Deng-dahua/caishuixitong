# -*- coding: utf-8 -*-
"""候选阈值**唯一索引**（D-01）—— 行为级验收 + 反向验证（2026-10-16）。

背景（阶段 1 D-01 裁定）：三册 `config/rulelist_v1|v11|v12.json` 各自维护 `params`，
此前消费方两条取法互不一致（`dict.update()` 静默覆盖 vs 只读 V1.0）⇒ 同一规则阈值
可能得到两个答案且无人发现。现收敛为 `engine.rule_loader.param_index()` 单一入口。

本文件验四件事：
  ① **索引完整性**：键数与三册去重键数一致；无跨册冲突；params_ref 指向存在的分册；
  ② **单点取用**：`param_of(rid)` 对三册各有正确归属（V1.0/V1.1/V1.2），未知 id ⇒ None（不兜底）；
  ③ **不静默覆盖**：注入同名同值 ⇒ 记 redundant 且**报错留痕**；注入同名异值 ⇒ 记 conflict（**不得**静默取后册）；
  ④ **消费方单源**：导出器 `rules_export/*.yaml` 的 `params_ref` 与索引一致。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import rule_loader as RL  # noqa: E402

BOOKS = ("rulelist_v1.json", "rulelist_v11.json", "rulelist_v12.json")


def _read(name: str) -> dict:
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


def test_index_keys_match_books() -> None:
    """① 索引键数 == 三册 params 去重键数（防漏读/多读）。"""
    idx = RL.param_index()
    raw = set()
    for name in BOOKS:
        raw |= {str(k) for k in (_read(name).get("params") or {}) if not str(k).startswith("_")}
    assert idx["stats"]["keys"] == len(raw), (idx["stats"]["keys"], len(raw))
    assert idx["stats"]["keys"] > 0


def test_no_cross_book_conflict() -> None:
    """① 当前三册**无跨册冲突**（若失败：说明有人把同一阈值两册各写一份且取值不同）。"""
    assert RL.param_conflicts() == []


def test_param_ref_points_to_existing_book() -> None:
    """① 索引内每个 params_ref 指向的分册确实存在。"""
    for key, ent in RL.param_index()["params"].items():
        assert (ROOT / ent["file"]).exists(), (key, ent["file"])
        assert ent["params_ref"].startswith("config/rulelist_v"), key


def test_param_of_book_attribution() -> None:
    """② 三册各自的规则取到正确归属；未知 id ⇒ None（**不兜底为空 dict**）。"""
    idx = RL.param_index()
    by_book = {}
    for key, ent in idx["params"].items():
        by_book.setdefault(ent["book"], key)
    assert set(by_book) == {"V1.0", "V1.1", "V1.2"}, by_book
    for book, key in by_book.items():
        ent = RL.param_of(key)
        assert ent and ent["book"] == book, (key, book, ent)
    assert RL.param_of("NOT-EXIST-999") is None
    assert RL.param_of("") is None


def test_no_silent_overwrite(monkeypatch=None) -> None:
    """③ **反向验证**：同名异值必须记 conflict（不得静默取后册）；同名同值记 redundant。

    做法：把 V1.1 里再登记一份 VAT-004（V1.0 已有）。异值 ⇒ conflict；同值 ⇒ redundant。
    验完立即还原（不使用 git checkout 回退数据产物）。
    """
    p = ROOT / "config" / "rulelist_v11.json"
    original = p.read_text(encoding="utf-8")
    try:
        d = json.loads(original)
        base = dict(_read("rulelist_v1.json")["params"]["VAT-004"])

        # A. 同值 ⇒ redundant（提示可收敛），**不算冲突**
        d["params"]["VAT-004"] = dict(base)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        idx = RL.param_index()
        assert idx["conflicts"] == [], idx["conflicts"]
        assert "VAT-004" in idx["redundant"], idx["redundant"]

        # B. 异值 ⇒ conflict，且**保留先册**（V1.0），不静默取后册（V1.1）
        bad = dict(base)
        bad["growth_gap"] = float(base.get("growth_gap", 0.3)) + 0.5
        d["params"]["VAT-004"] = bad
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        idx2 = RL.param_index()
        assert [c["key"] for c in idx2["conflicts"]] == ["VAT-004"], idx2["conflicts"]
        ent = RL.param_of("VAT-004")
        assert ent["book"] == "V1.0", ent
        assert ent["value"].get("growth_gap") == base.get("growth_gap"), ent
    finally:
        p.write_text(original, encoding="utf-8")
    # 还原后必须回到无冲突
    assert RL.param_conflicts() == []


def test_exported_yaml_params_ref_consistent() -> None:
    """④ 导出产物的 `params_ref` 与索引一致（防消费方各写一份）。"""
    idx = RL.param_index()["params"]
    yml_dir = ROOT / "rules_export"
    if not yml_dir.exists():
        return
    try:
        import yaml  # noqa: PLC0415
    except Exception:                                            # noqa: BLE001
        return
    seen = 0
    for f in sorted(yml_dir.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for r in (doc.get("rules") or []):
            rid = str(r.get("rule_id") or "")
            ent = idx.get(rid)
            if not ent:
                continue
            seen += 1
            assert r.get("params_ref") == ent["params_ref"], (rid, r.get("params_ref"), ent["params_ref"])
    assert seen > 0, "导出产物里一个可核对条目都没有 ⇒ 判据空转"
