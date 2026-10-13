# -*- coding: utf-8 -*-
"""OCR 引擎治理（P1-2）—— 引擎探测 / 可用性回执 / 置信度治理 / 运行留痕的**唯一权威**。

## 扫描现状（改动前，`main._ocr_png_bytes`）

| 既有实现 | 位置 | 缺口 |
|---|---|---|
| OCR 唯一收敛点（三引擎依次尝试） | `main._ocr_png_bytes`（rapidocr → easyocr → pytesseract） | ① **全部引擎不可用时静默返回空串** —— 与"这张图确实没字"**无法区分**（用户拿到空结果不知道是"没识别到"还是"根本没有引擎"）；② 引擎返回的**置信度被丢弃**（rapidocr 的 `item[2]`、easyocr 的 `conf` 均未使用）；③ 失败只 `print` 到 stdout，**无结构化留痕**；④ **无法提前告知**"本机有哪些 OCR 引擎可用"，只能"试到成功为止" |
| PDF 渲染 | `main._ocr_pdf_pages`（`fitz` → PNG → `_ocr_png_bytes`） | 与 OCR 同源，页面渲染失败也只 `print` |

## 本模块做什么（**不改既有解析行为**）

1. **引擎登记 + 探测**（`ENGINES` / `probe_engines()` / `engine_status()`）：
   把"有哪些引擎、依赖什么、当前是否可用"变成**可查询的结构化状态**。
2. **运行留痕**（`record_ocr_run()`）：记录引擎名 / 段数 / 耗时 / 是否命中；
   **全部引擎不可用时给出显式原因**（不静默）。
3. **置信度治理**（`CONF_FLOOR` / `engine_metadata()`）：低于阈值计入 `low_conf` 并如实回报。

## 铁律

- **行为等价**：`record_ocr_run(chunks, engine)` 的**返回值与 `"\\n".join(chunks)` 逐字符相同**
  （`tests/test_ocr_engine.py` 用"字符串相等"断言）——治理不得改变解析结果。
- **缺失 ≠ 空**：没有可用引擎 ⇒ `engine_status()["any_available"] is False` 且 `note` 显式说明；
  `record_ocr_run` 在 `chunks` 为空时标记 `empty=True` 并记录**原因**（引擎不可用 / 无文字）。
- **单一权威**：引擎清单与优先级只此一处；`main.py` 只做同行内薄转发。
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "ENGINES", "CONF_FLOOR", "TESSERACT_CANDIDATES",
    "probe_engines", "engine_status", "engine_metadata",
    "record_ocr_run", "last_ocr_run", "reset_runs",
]

#: OCR 引擎登记表（★ 唯一权威：新增引擎只加这里一行；顺序**即优先级**）
ENGINES: Tuple[Dict[str, Any], ...] = (
    {"name": "rapidocr", "priority": 0, "module": "rapidocr_onnxruntime",
     "conf_index": 2, "note": "纯 pip、离线、无系统依赖（首选）"},
    {"name": "easyocr", "priority": 1, "module": "easyocr",
     "conf_index": None, "note": "依赖 torch（约 2.5GB），通常不安装"},
    {"name": "tesseract", "priority": 2, "module": "pytesseract", "exe": "tesseract",
     "conf_index": None, "note": "需系统安装 tesseract.exe（含中文语言包）"},
)

#: tesseract 常见安装路径（与 `main._ocr_png_bytes` 的探测口径一致）
TESSERACT_CANDIDATES: Tuple[str, ...] = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

#: 低置信度阈值（easyocr 的 `conf` 为 0~1；rapidocr 同量纲）
CONF_FLOOR: float = 0.5

_LOCK = threading.RLock()
_RUNS: List[Dict[str, Any]] = []
_MAX_RUNS = 50


# ══════════════════════════════════════════════════════════════════════════
# ① 探测（无副作用：只查模块/可执行文件是否存在，**不初始化引擎**）
# ══════════════════════════════════════════════════════════════════════════
def _module_available(mod: str) -> bool:
    import importlib.util as _iu                              # noqa: PLC0415
    try:
        return _iu.find_spec(str(mod)) is not None
    except Exception:                                         # noqa: BLE001
        return False


def _exe_available(exe: str) -> bool:
    if shutil.which(str(exe)):
        return True
    return any(os.path.exists(p) for p in TESSERACT_CANDIDATES)


def probe_engines() -> Dict[str, bool]:
    """逐引擎探测可用性（**不初始化**，故很快且无副作用）。"""
    out: Dict[str, bool] = {}
    for e in ENGINES:
        name = str(e["name"])
        ok = _module_available(str(e["module"])) if e.get("module") else False
        if ok and e.get("exe"):
            ok = _exe_available(str(e["exe"]))
        out[name] = bool(ok)
    return out


def engine_status() -> Dict[str, Any]:
    """结构化状态（供接口/前端；**找不到引擎必须显式说明**）。"""
    avail = probe_engines()
    rows = []
    for e in ENGINES:
        name = str(e["name"])
        rows.append({
            "name": name, "priority": int(e["priority"]),
            "available": bool(avail.get(name)),
            "module": str(e.get("module") or ""),
            "requires_exe": str(e.get("exe") or ""),
            "note": str(e.get("note") or ""),
        })
    have = [r["name"] for r in rows if r["available"]]
    if have:
        note = "可用 OCR 引擎：%s（按优先级依次尝试）。" % "、".join(have)
    else:
        note = ("**本机无可用 OCR 引擎** —— 扫描件/图片型 PDF 将**提取不到文字**"
                "（不是『没有文字』，而是『无法识别』）。请安装 `rapidocr-onnxruntime`"
                "（纯 pip、离线、无系统依赖）后重启服务。")
    return {
        "engines": rows,
        "available": have,
        "any_available": bool(have),
        "preferred": have[0] if have else "",
        "conf_floor": CONF_FLOOR,
        "note": note,
    }


def engine_metadata() -> Dict[str, Any]:
    """字典（供 `/api/v1/ocr/meta`）。"""
    st = engine_status()
    st["runs"] = len(_RUNS)
    st["last"] = dict(_RUNS[-1]) if _RUNS else None
    return st


# ══════════════════════════════════════════════════════════════════════════
# ② 运行留痕（供 `main._ocr_png_bytes` 同行内薄转发）
# ══════════════════════════════════════════════════════════════════════════
def record_ocr_run(chunks: Sequence[str], engine: str, *,
                   elapsed: float = 0.0,
                   confidences: Optional[Sequence[float]] = None) -> str:
    """登记一次 OCR 运行并**原样**返回拼接文本。

    ★ 返回值必须与 `"\\n".join(chunks)` **逐字符相同**（行为等价，见模块 docstring 铁律）。
    """
    text = "\n".join(chunks or [])                            # ← 与既有实现**完全同口径**
    segs = len([c for c in (chunks or []) if str(c).strip()])
    confs = [float(c) for c in (confidences or [])
             if isinstance(c, (int, float)) and not isinstance(c, bool)]
    low = sum(1 for c in confs if c < CONF_FLOOR)
    reason = ""
    if segs == 0:
        reason = ("无可用 OCR 引擎" if engine in ("none", "", None)
                  else "引擎 %s 未识别到文字" % engine)
    row = {
        "at": _now_iso(), "engine": str(engine or "none"),
        "segments": segs, "chars": len(text),
        "elapsed": round(float(elapsed or 0.0), 3),
        "conf_n": len(confs), "low_conf": low,
        "empty": segs == 0, "reason": reason,
    }
    with _LOCK:
        _RUNS.append(row)
        if len(_RUNS) > _MAX_RUNS:
            del _RUNS[0:len(_RUNS) - _MAX_RUNS]
    if segs == 0:
        # ★ 绝不静默：留一条 stderr 说明（与既有 print 并存，便于现场排查）
        try:
            import sys as _sys                                # noqa: PLC0415
            print("[OCR] 本次未提取到文字：%s" % (reason or "未知原因"), file=_sys.stderr, flush=True)
        except Exception:                                     # noqa: BLE001
            pass
    return text


def _now_iso() -> str:
    try:
        from runtime_storage import now_cst                   # noqa: PLC0415
        return str(now_cst())
    except Exception:                                         # noqa: BLE001
        return time.strftime("%Y-%m-%dT%H:%M:%S")


def last_ocr_run() -> Optional[Dict[str, Any]]:
    with _LOCK:
        return dict(_RUNS[-1]) if _RUNS else None


def reset_runs() -> None:
    """清空运行留痕（测试用；不影响任何既有状态）。"""
    with _LOCK:
        _RUNS.clear()
