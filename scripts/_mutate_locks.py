# -*- coding: utf-8 -*-
"""把三件"诊断/口径层"的结论**锁成自动校验**，并修 ③ 的匹配漏项。

① 锁 D13：`数据源已具备（已有）却判未单独核对` 必须为 0 条（读真跑产物）。
   此前 D13 是**诊断证明不成立**而关闭的——没有闸门就可能静默复发。
② 锁报告层触红：企业报告 `confirmed_problems[*].verdict` 不得含「已触碰税务违规红线」。
   引擎中间层允许保留带限定的触红中间态（资料不足待补证），但**读者看到的结论层不得触红**。
   （这一条锁的是"分层口径"，避免以后再出现"全文多少条"的歧义。）
③ 修补资料清单的匹配漏项：状态过滤只认「未取得/待核」，而实际 many 行是「缺失」
   ⇒ 依赖度被算成 0 ⇒ 12 个疑点挂不出清单。改为**凡非「已有」的未核对状态都算**。

★ 文案不含 ASCII 引号；补丁用唯一锚点。
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)


def swap(path, pairs):
    p = os.path.join(ROOT, path)
    raw = io.open(p, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    for tag, old, new in pairs:
        c = t.count(old)
        if c != 1:
            print("!! %s 命中 %d 次（应为 1）" % (tag, c))
            sys.exit(2)
        t = t.replace(old, new, 1)
    io.open(p, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK %s" % path)


# ── ③ 修匹配漏项：凡非「已有」的未核对状态都计入依赖度 ──────────────────
swap("engine/enterprise_report.py", [(
    '            if "未取得" not in _st and "待核" not in _st and "未单独核对" not in _cc:',
    '            # ★ 2026-10-04：状态过滤放宽为「凡非已有」——实测 many 行的状态是「缺失」，\n'
    '            #   原过滤只认 未取得/待核 ⇒ 依赖度被算成 0 ⇒ 12 个疑点挂不出清单（空表）。\n'
    '            #   判据仍是"未核对"：状态不是「已有」，或结论写了未单独核对。\n'
    '            if _st == "已有" and "未单独核对" not in _cc:'
)])

# ── ①② 加闸门（读真跑产物）────────────────────────────────────────────
ANCH = ('                           "剔除了汇总行却未如实披露（不得静默少算）"))')
GATE = ANCH + NL + (
    NL +
    '        # ④ 分层口径 + D13 复发防护（2026-10-04）：' + NL +
    '        #   ① **报告结论层不得触红**：引擎中间层允许保留带限定的触红中间态' + NL +
    '        #      （资料不足待补证后判断），但读者看到的 `verdict` 不得出现触红断言。' + NL +
    '        #      锁这一条是为了消除"全文多少条触红"的口径歧义（此前实测 95 处，报告层 0 处）。' + NL +
    '        #   ② **数据源已具备却判未单独核对**必须为 0（D13 的复发防护；' + NL +
    '        #      该缺陷此前是**诊断证明不成立**而关闭的，没有闸门就会静默复发）。' + NL +
    '        try:' + NL +
    '            import json as _j4' + NL +
    '            _art4 = ROOT / "scripts" / "four_reports" / "company_1_full.json"' + NL +
    '            if not _art4.exists():' + NL +
    '                issues.append(("WARN", "scripts/four_reports/company_1_full.json",' + NL +
    '                               "无真跑产物，跳过分层口径与 D13 复发防护校验"))' + NL +
    '            else:' + NL +
    '                _d4 = _j4.loads(_art4.read_text(encoding="utf-8", errors="replace"))' + NL +
    '                _cp4 = ((_d4.get("enterprise_readable_report") or {})' + NL +
    '                        .get("confirmed_problems") or [])' + NL +
    '                for _p4 in _cp4:' + NL +
    '                    if "已触碰税务违规红线" in str(_p4.get("verdict") or ""):' + NL +
    '                        issues.append(("ERROR", "enterprise_readable_report",' + NL +
    '                                       "报告结论层出现触红断言（seq=%s）——读者看到的就是定性结论，' + NL +
    '                                       "不得触红；触红只能作为带限定的中间态留在引擎层" % _p4.get("seq")))' + NL +
    '                _b4 = 0' + NL +
    '                for _p4 in _cp4:' + NL +
    '                    for _n4 in (_p4.get("narrative_paragraphs") or []):' + NL +
    '                        for _t4 in (_n4.get("detail_tables") or []):' + NL +
    '                            if "独立核对表" not in str((_t4 or {}).get("title") or ""):' + NL +
    '                                continue' + NL +
    '                            for _r4 in ((_t4 or {}).get("rows") or []):' + NL +
    '                                if ("未单独核对" in str(_r4.get("核对结论") or "")' + NL +
    '                                        and str(_r4.get("数据源状态") or "") == "已有"):' + NL +
    '                                    _b4 += 1' + NL +
    '                if _b4:' + NL +
    '                    issues.append(("ERROR", "enterprise_readable_report",' + NL +
    '                                   "数据源已具备却判未单独核对 %d 条 ＝ 有数据却放弃核对（D13 复发）" % _b4))' + NL +
    '        except Exception as _e4:  # noqa: BLE001' + NL +
    '            issues.append(("ERROR", "tools/audit_consistency.py",' + NL +
    '                           f"分层口径/D13 防护断言执行失败：{_e4}"))'
)
swap("tools/audit_consistency.py", [(ANCH, GATE)])
print("[DONE] ①②闸门 + ③匹配修正 已落地")
