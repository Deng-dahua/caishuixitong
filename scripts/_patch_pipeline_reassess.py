# -*- coding: utf-8 -*-
"""接线：pipeline._run_analyze 里在 Phase 2 之前做一次行业「随资料再判读」。

pipeline.py 是 **LF 既有文件**，注入块用 \n，绝不整文件转 CRLF。
幂等：含哨兵则跳过。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "engine", "pipeline.py")
SENTINEL = "# ★ 2026-10-02：行业「随资料再判读」"

BLOCK = u'''    # ★ 2026-10-02：行业「随资料再判读」
    #   资料（合同台账 / 进项票品名 / 已上传资料清单）现已全部就位，回头再判一次行业口径。
    #   口径：只有**新证据一致指向同一个具体行业**才变更；证据不足 / 并票无共识一律 keep。
    #   全部决策留痕进 pipeline_log（报告层可披露「行业判定依据」）。
    try:
        _pur_goods = []
        for _inv in (pur_invs or []):
            _g = str(_inv.get("goods", _inv.get("货物或应税劳务名称", "")) or "").strip()
            if _g:
                _pur_goods.append(_g)
        _mat_hints = []
        for _fr in (file_results or []):
            for _k in ("name", "filename", "file_name", "display_name", "type", "doc_type"):
                _v = str(_fr.get(_k) or "").strip()
                if _v and _v not in _mat_hints:
                    _mat_hints.append(_v)
        _ct_text = " ".join(
            str(_c.get("name") or _c.get("title") or _c.get("contract_name") or "")
            for _c in (contract_data or []))
        from engine.industry_resolver import reassess_industry as _reassess
        _ra = _reassess(
            current_industry=ctx.company_profile.get("industry", ""),
            current_source=ctx.company_profile.get("industry_source", ""),
            purchase_goods=_pur_goods,
            material_hints=_mat_hints,
            contract_text=_ct_text,
            pipeline_log=pipeline_log,
        )
        ctx.company_profile["industry_reassess"] = _ra.get("decision", "")
        ctx.company_profile["industry_reassess_reason"] = _ra.get("reason", "")
        if _ra.get("decision") == "change":
            _old_i3 = str(ctx.company_profile.get("industry", ""))
            _new_i3 = str(_ra.get("industry", ""))
            ctx.company_profile["industry"] = _new_i3
            ctx.company_profile["industry_source"] = "随资料再判读"
            pipeline_log.append("[行业口径] 随资料再判读完成：'%s' → '%s'" % (_old_i3, _new_i3))
            # 成本识别的行业口径同步（唯一注入点，与 _detect_target_entity 一致）
            try:
                from engine.main_biz_cost import set_active_industry as _set_ind3
                from engine.main_biz_cost import set_active_industries as _set_inds3
                _set_ind3(_new_i3)
                _set_inds3([_new_i3])
            except Exception:
                pass
    except Exception as _ra_err:
        pipeline_log.append("[行业再判读] 跳过（保留原行业口径）: %s" % _ra_err)

'''

ANCHOR = u"    # 2026-09-22：显式传入 tax_declarations，供 Phase2 的「增值税申报比对」域使用"


def main():
    with io.open(TARGET, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    if SENTINEL in src:
        print("SKIP: already wired")
        return 0
    assert ANCHOR in src, "anchor not found"
    block = BLOCK.replace("\n", "\r\n") if False else BLOCK
    src = src.replace(ANCHOR, block + ANCHOR, 1)
    with io.open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(src)
    print("OK: wired into %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
