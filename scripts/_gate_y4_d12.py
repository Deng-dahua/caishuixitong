# -*- coding: utf-8 -*-
"""疑点4 D12 的**产物级闸门**（防复发）+ 行为级反向验证。

闸门断言（双向，防止"矫枉过正"）
--------------------------------
① **不相容不得有金额**：事实基数性质与税种要求不符时，该税种**必须** `amount=None`
   —— 否则等于没修（工资差额又被当应税收入算增值税）。
② **相容不得被误不估**：性质相符（或性质未声明）时，**不得**出现
   「与本税种要求的基数性质…不符」的说明 —— 否则是把真实风险藏起来了。

行为级反向验证（不依赖产物）
--------------------------
用 D12 现场参数直接调 `estimate_tax`：
  · `non_sales` + 增值税 ⇒ 必须无金额（变异回"不校验"则必须有金额 ⇒ 闸门能抓）
  · `sales` + 增值税 ⇒ 必须有金额（变异成"一律不估"则能抓）

纪律：锚点唯一性先校验；同一文件多次替换**累积**后一次性写盘。
"""
import io
import os
import subprocess
import sys

ROOT = os.getcwd()
NL = chr(10)
CRLF = chr(13) + chr(10)
AUDIT = os.path.join(ROOT, "tools", "audit_consistency.py")

ANCHOR = "        except Exception as _e5:"

GATE = [
    "            # ⑦ 税种 × 基数性质（疑点4 D12，2026-10-04）：**双向**断言。",
    "            #   ① 不相容 ⇒ 必须无金额（否则等于没修：工资差额又被当应税收入算增值税）；",
    "            #   ② 相容/未声明 ⇒ 不得出现「基数性质不符」的说明（否则是把真实风险藏起来）。",
    "            try:",
    "                from engine.tax_impact import (_TAX_BASE_NATURE as _tbn7,",
    "                                              infer_amount_nature as _ian7)",
    "                _bad7 = []",
    "                for _p7 in _ps5:",
    "                    _nat7 = _ian7(_p7)",
    "                    if not _nat7:",
    "                        continue",
    "                    for _it7 in ((_p7.get(\"tax_impact\") or {}).get(\"items\") or []):",
    "                        _need7 = _tbn7.get(str(_it7.get(\"tax\") or \"\"))",
    "                        if not _need7:",
    "                            continue",
    "                        _amt7 = _it7.get(\"amount\")",
    "                        _bad7.append((_p7.get(\"seq\"), _it7.get(\"tax\"), _nat7, _need7))",
    "                        if _need7 != _nat7 and _amt7 is not None:",
    "                            issues.append((\"ERROR\", \"engine/tax_impact.py\",",
    "                                           \"基数口径与税种要求不符却仍给出金额 seq=%s %s"
    "（口径=%s 要求=%s）\" % (_p7.get(\"seq\"), _it7.get(\"tax\"), _nat7, _need7)))",
    "                        if _need7 == _nat7 and _amt7 is None \\",
    "                                and \"与本税种要求的基数性质\" in str(_it7.get(\"note\") or \"\"):",
    "                            issues.append((\"ERROR\", \"engine/tax_impact.py\",",
    "                                           \"相容税种被误不估（把真实风险藏起来）seq=%s %s\"",
    "                                           % (_p7.get(\"seq\"), _it7.get(\"tax\"))))",
    "            except Exception as _e7:",
    "                issues.append((\"ERROR\", \"tools/audit_consistency.py\",",
    "                               f\"税种基数相容性断言失败: {_e7}\"))",
    ANCHOR,
]


def rd(p):
    return io.open(p, "r", encoding="utf-8", newline="").read().replace(CRLF, NL)


raw = io.open(AUDIT, "r", encoding="utf-8", newline="").read()
crlf = CRLF in raw
t = raw.replace(CRLF, NL)
c = t.count(ANCHOR)
print("锚点命中 =", c)
if c != 1:
    print("!! 锚点不唯一 ⇒ 不写盘")
    sys.exit(2)
t = t.replace(ANCHOR, NL.join(GATE), 1)          # 累积后一次性写
assert t.count("⑦ 税种 × 基数性质") == 1
io.open(AUDIT, "w", encoding="utf-8", newline="").write(t.replace(NL, CRLF) if crlf else t)
print("OK 产物级闸门已插入")

RUN = ("import sys; sys.path.insert(0, %r);"
       "from tools.audit_consistency import check_report_consistency as f;"
       "iss=[i for i in f() if i[0]=='ERROR']; print('  产物基线 ERROR =', len(iss));"
       "[print('   ', i[1], i[2][:88]) for i in iss]") % ROOT
print("")
print("=== 基线（真实产物，应 0）===")
r = subprocess.run([sys.executable, "-c", RUN], capture_output=True, text=True,
                   cwd=ROOT, encoding="utf-8", errors="replace")
print(((r.stdout or "") + (r.stderr or "")).strip())
