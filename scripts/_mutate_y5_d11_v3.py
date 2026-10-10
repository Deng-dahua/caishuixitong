# -*- coding: utf-8 -*-
"""疑点5 · D11 收口：让 §三 与 §四 看到**同一份元素数据**（构造上不可能不一致）。

★ print 验证拿到的根因：§三 的 `_nr_el`（业态剔除）在**副本**上重写了 `name`，
  而 §四 读的仍是 `ev["elements"]` 里的**原名** ⇒ 两边元素名不同 ⇒ 同源计算也算出不同结果
  （§三 3 / §四 1）。同时发现引擎 `status` 取值只有
  `已有/待核/缺失/待企业提交`（**没有"待核实"**，那是我从报告层显示词猜的）。

修法（两处，各一行级）
----------------------
① `_nr_el`：把剔除后的名字**写回原 element**（`e["name"] = _n`），
   不再用副本 ⇒ §三 与 §四 读到的名字一致。
② `_SEPS11` 补 "或"（§三 的拆分正则含 `或`，我漏了 ⇒ 原子数可能仍不同）。

不动任何判定；`_nr_el` 只影响名字的业态剔除结果，而它本来就是为"剔除本业态不适用"服务的。
"""
import io
import os
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
ER = os.path.join(ROOT, "engine", "enterprise_report.py")
AR = os.path.join(ROOT, "engine", "argumentation.py")

# ① _nr_el 写回
OLD1 = (
    "            if _n == str((_e or {}).get(\"name\") or \"\").strip():" + NL +
    "                return _e" + NL +
    "            _c = dict(_e)" + NL +
    "            _c[\"name\"] = _n" + NL +
    "            return _c"
)
NEW1 = (
    "            if _n == str((_e or {}).get(\"name\") or \"\").strip():" + NL +
    "                return _e" + NL +
    "            # ★ 2026-10-05（疑点5 D11）：**写回原 element**，不再用副本 ——" + NL +
    "            #   旧实现只在副本上重写 name，§四 读 `ev[\"elements\"]` 仍是原名" + NL +
    "            #   ⇒ §三/§四 元素名不同 ⇒ 同源计算也算出不同项数（D11）。" + NL +
    "            try:" + NL +
    "                _e[\"name\"] = _n" + NL +
    "            except Exception:  # noqa: BLE001" + NL +
    "                pass" + NL +
    "            return _e"
)


def swap(path, old, new, tag):
    raw = io.open(path, "r", encoding="utf-8", newline="").read()
    crlf = CRLF in raw
    t = raw.replace(CRLF, NL)
    c = t.count(old)
    print("%s 命中 = %d" % (tag, c))
    if c != 1:
        print("!! %s 锚点异常 ⇒ 全不写盘" % tag)
        sys.exit(2)
    t = t.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
    print("OK " + tag)


swap(ER, OLD1, NEW1, "① _nr_el 写回")

# ② _SEPS11 补「或」
raw = io.open(AR, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
OLD2 = '    _SEPS11 = ("、", "，", ",", "；", ";", "／", "/", "或者", "以及", "与", "和", "及")'
NEW2 = '    _SEPS11 = ("、", "，", ",", "；", ";", "／", "/", "或者", "以及", "与", "和", "及", "或")'
swap(AR, OLD2, NEW2, "② _SEPS11 补「或」")
print("[DONE] 疑点5 D11 已收口")
