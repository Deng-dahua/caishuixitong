# -*- coding: utf-8 -*-
"""扫「缺资料被写成违规」全项目路径（D2 违反）。

判据（与工资社保事件同一性质）：
  一条 finding 的 **type/detail/description 文本里出现"缺失/未提供/无法验证/无法执行/无法判断"**
  等缺资料信号，但它的 **level 是 中风险/高风险/极高风险**（= 把"资料没交"表述成企业风险）。

这类发现会：① 让企业背不存在的锅；② 掩盖真正的动作（该补资料的，写成"企业有问题"）。
正确做法：降级为「待核验」+ 明确写"缺资料不等于违规" + 给出需补自证资料。

用法：python scripts/_hunt_missing_as_violation.py [--fix-levels]
  --fix-levels 仅把命中的 level 改为「待核验」（不改文案），用于评估影响面；
  默认只报告不改动。
"""
import ast
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HIGH_LEVELS = {"中风险", "高风险", "极高风险"}
# ⚠ 两类必须区分（否则会把"业务事实"误当成"缺资料违规"）：
#   · 上传层缺失（D2 真违规）：企业**没交资料/交了读不出来** → 不能写成企业风险等级
#   · 业务层事实（合理）：企业自己的业务数据存在缺口/差异（发票缺数量栏、进销存勾稽不平衡、
#     无采购记录、合同覆盖率低）→ 这是「查出来的事实」，本就该给等级
UPLOAD_LAYER_HINTS = (
    "未上传", "未提交", "文件解析失败", "解析失败", "均为空", "数据为空", "为空",
    "未提供", "无法执行", "无法进行", "无法评估", "资料缺失", "缺少文件", "未取得",
)
TYPE_UPLOAD_MARKERS = ("资料缺失", "无法执行", "解析失败", "未提供", "缺少数据", "未上传")
BUSINESS_LAYER_HINTS = (
    "缺少数量", "无采购记录", "覆盖率", "勾稽", "不平衡", "缺数量", "未匹配", "差异",
)
# 反向：已经写明"不等于违规/待补证/不作认定"的不算越界
GUARDED = ("不等于违规", "不作认定", "待补证", "待核验", "不作违规推定", "补充资料后",
           "待补充", "排查清单")


def _str_const(node):
    """取 dict 字面量里可以是字符串/拼接常量的值。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):            # f-string → 取其中的常量片段
        return " ".join(v.value for v in node.values
                        if isinstance(v, ast.Constant) and isinstance(v.value, str))
    if isinstance(node, ast.BinOp):                # 字符串 +
        return " ".join(filter(None, (_str_const(node.left), _str_const(node.right))))
    return ""


def scan_file(path):
    rel = os.path.relpath(path, ROOT).replace("\\", "/")
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(src)
    except Exception:
        return []
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        kv = {}
        for k, v in zip(node.keys, node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                kv[k.value] = v
        if "level" not in kv:
            continue
        lv = _str_const(kv["level"])
        if lv not in HIGH_LEVELS:
            continue
        text = " ".join(filter(None, (_str_const(kv.get("type")), _str_const(kv.get("detail")),
                                      _str_const(kv.get("description")))))
        if not text:
            continue
        if any(g in text for g in GUARDED):
            continue
        ftype = _str_const(kv.get("type"))
        up_hints = [h for h in UPLOAD_LAYER_HINTS if h in text]
        # 判定为「上传层缺失」需满足：type 明示上传/缺失类，或正文出现上传层信号
        is_upload_layer = bool(up_hints) and (
            any(m in ftype for m in TYPE_UPLOAD_MARKERS) or "未上传" in text
            or "文件解析失败" in text or "解析失败" in text or "均为空" in text
        )
        # 业务层事实（企业自己的数据差异）不算 D2 违规，单列备查
        is_business = any(h in text for h in BUSINESS_LAYER_HINTS) and not is_upload_layer
        if not up_hints and not is_business:
            continue
        hits.append({
            "file": rel, "line": node.lineno, "level": lv,
            "type": ftype[:60],
            "kind": "上传层缺失(D2违规)" if is_upload_layer else "业务层事实(合理)",
            "hints": sorted(set(up_hints))[:5],
            "snippet": text[:150],
        })
    return hits


def main():
    # ★ 复用闸门的唯一实现，避免"脚本一套口径、闸门另一套"（本项目复发型坑）
    from tools.audit_consistency import scan_upload_layer_violations, ROOT as _ROOT  # noqa
    d2 = scan_upload_layer_violations()
    print("=" * 78)
    print(f"A. 上传层缺失被写成风险等级（D2 违规）—— 共 {len(d2)} 处")
    print("=" * 78)
    order = {"极高风险": 0, "高风险": 1, "中风险": 2}
    for rel, lineno, lv, ftype in sorted(d2, key=lambda x: (order.get(x[2], 9), x[0])):
        print(f"  [{lv}] {rel}:{lineno}  {ftype}")
    print("\n  分级：", {lv: sum(1 for _, _, x, _ in d2 if x == lv)
                          for lv in ("极高风险", "高风险", "中风险")})
    if not d2:
        print("  ✓ 无（与闸门 check_missing_as_violation 同源，闸门 ERROR 0 即通过）")

    # 业务层事实（企业自身业务数据差异）单列备查，不算 D2 违规
    biz = []
    for f in ["main.py"] + sorted(glob.glob(os.path.join(ROOT, "engine", "**", "*.py"), recursive=True)):
        if "__pycache__" in f:
            continue
        biz.extend([h for h in scan_file(f) if not h["kind"].startswith("上传层")])
    print("\n" + "=" * 78)
    print(f"B. 业务层事实带风险等级（合理，仅备查）—— 共 {len(biz)} 处")
    print("=" * 78)
    for h in biz[:40]:
        print(f"  [{h['level']}] {h['file']}:{h['line']}  {h['type']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
