# -*- coding: utf-8 -*-
"""第三行闸门：要件数据源状态**不得**由环节 `has_data` 决定（必须走资料齐备性唯一权威）。

行为级断言（构造：回退路径 + 节点 has_data=False + 资料已提供）：
  · 数据源状态不得是"未取得"（否则 = 有数据却判未核对）；
  · 依据不得写"本轮为「未取得」"。

幂等保护：写入前后各断言标记唯一（上一轮踩过"补丁脚本不幂等导致闸门重复插入"）。
反向验证：把 constituent_checkpoint 改回 `has_data` 判据 ⇒ 闸门必须变红。
"""
import io
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NL = chr(10)
CRLF = chr(13) + chr(10)
AUDIT = os.path.join(ROOT, "tools", "audit_consistency.py")
CCP = os.path.join(ROOT, "engine", "constituent_checkpoint.py")

MARK = '        # ④ 要件数据源状态'

GATE = MARK + NL + (
    '        # ④ 要件数据源状态（合并批次第三行 / 疑点2 D13，2026-10-04）：' + NL +
    '        #    数据源状态**只能**来自资料齐备性唯一权威，**不得**取环节 `has_data`' + NL +
    '        #    （后者语义是"本环节有没有对题读数"，不是"这份资料有没有提供"）。' + NL +
    '        #    混用会让"资料已提供"被写成"独立数据源本轮未取得"⇒ 要件"未单独核对"' + NL +
    '        #    ＝"有数据却放弃核对"。' + NL +
    '        try:' + NL +
    '            from engine.constituent_checkpoint import (  # noqa: PLC0415' + NL +
    '                build_constituent_checkpoints as _bcc)' + NL +
    '            _syn = {' + NL +
    '                "redline_id": "RL-T", "redline_name": "n",' + NL +
    '                "constituents": ["存在工资未申报情形"],' + NL +
    '                # ⚠ 刻意**不声明** constituent_sources ⇒ 走"回退路径"' + NL +
    '                "clue_chain": {"nodes": [{"step": 1, "source": "工资表",' + NL +
    '                                         "output": "工资台账", "has_data": False}]},' + NL +
    '                "evidence_chain": {"available_materials": ["工资表"], "elements": []},' + NL +
    '                "argumentation": {"constituent_hits": []},' + NL +
    '            }' + NL +
    '            _cps = _bcc(_syn, {"id": "RL-T", "name": "n",' + NL +
    '                               "constituents": ["存在工资未申报情形"]}) or []' + NL +
    '            for _cp in _cps:' + NL +
    '                _stx = str(_cp.get("数据源状态") or "")' + NL +
    '                _bsx = str(_cp.get("依据") or "")' + NL +
    '                if "未取得" in _stx or "本轮为「未取得」" in _bsx:' + NL +
    '                    issues.append(("ERROR", "engine/constituent_checkpoint.py",' + NL +
    '                                   "资料已提供（工资表）却因环节 has_data=False 判"未取得" ⇒"' + NL +
    '                                   "有数据却放弃核对；数据源状态须走资料齐备性唯一权威"))' + NL +
    '        except Exception as _e2:  # noqa: BLE001' + NL +
    '            issues.append(("ERROR", "engine/constituent_checkpoint.py",' + NL +
    '                           f"要件数据源状态断言执行失败：{_e2}"))'
)

s = io.open(AUDIT, "r", encoding="utf-8", newline="").read()
has_crlf = CRLF in s
t = s.replace(CRLF, NL)
if t.count(MARK) == 0:
    # 插在"③ 汇总行"断言之后（同一 try 块内，缩进一致）
    ANCH = '                           "\u5254\u9664\u4e86\u6c47\u603b\u884c\u5374\u672a\u5982\u5b9e\u62ab\u9732\uff08\u4e0d\u5f97\u9759\u9ed8\u5c11\u7b97\uff09"))'
    if t.count(ANCH) != 1:
        print("!! 插入锚点命中 %d 次" % t.count(ANCH))
        sys.exit(2)
    t = t.replace(ANCH, ANCH + NL + GATE, 1)
    print("OK 闸门已插入")
elif t.count(MARK) == 1:
    print("闸门已存在，跳过插入（幂等）")
else:
    print("!! 闸门标记出现 %d 次，需先清理" % t.count(MARK))
    sys.exit(2)
assert t.count(MARK) == 1, "写入后标记数应为 1"
io.open(AUDIT, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if has_crlf else t)

RUN = ("import sys; sys.path.insert(0, %r);"
       "from tools.audit_consistency import check_report_consistency as f;"
       "iss=[i for i in f() if i[0]=='ERROR']; print(len(iss));"
       "[print(chr(32)*4, i[1], i[2][:95]) for i in iss]") % ROOT


def run():
    r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                       cwd=ROOT, encoding="utf-8", errors="replace")
    return ((r.stdout or "") + (r.stderr or "")).strip()


print("\n=== 基线 ===")
print(run())

base = io.open(CCP, "r", encoding="utf-8", newline="").read()
crlf = CRLF in base
t2 = base.replace(CRLF, NL)
OLD = '        _cands.append((nm, _st_node or "未知"))'
NEW = '        _cands.append((nm, "已有" if n.get("has_data") else "未取得"))  # MUTATED'
if t2.count(OLD) != 1:
    print("\n!! 变异锚点命中 %d 次" % t2.count(OLD))
else:
    t2 = t2.replace(OLD, NEW, 1)
    io.open(CCP, "w", encoding="utf-8", newline="").write(t2.replace(NL, CRLF) if crlf else t2)
    print("\n=== 反向验证：退回 has_data 判据 ⇒ ===")
    print(run())
    io.open(CCP, "w", encoding="utf-8", newline="").write(base)
    print("\n=== 还原后 ===")
    print(run())
