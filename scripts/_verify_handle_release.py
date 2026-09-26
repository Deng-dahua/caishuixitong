# -*- coding: utf-8 -*-
"""端到端验证：分析完成后立即删除资料，不得出现"被本服务自身占用"。

用户报「已彻底清理 0 个文件；1 个仍被程序占用，怎么还能被占用」。
本脚本复刻其真实操作序列并断言修复有效：

  ① 上传一份合成资料（走真实上传接口，免去"重启才扫描"的耦合）
  ② 强制分析（真实跑完整管道，会打开并关闭该 xlsx）
  ③ 分析一结束就删除该资料
  ④ 断言：磁盘真实消失、left_on_disk == 0、失败明细为空；随后自行清理

若 ③ 出现 left_on_disk > 0，即"分析句柄泄漏仍会占住文件"，本脚本必须失败。
脚本自给自足、可重复运行（自造数据 + 自清理），不依赖服务重启。
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
import http.cookiejar

B = "http://127.0.0.1:8001"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CID = 1
CJ = http.cookiejar.CookieJar()
OP = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CJ))
CS = ""


def req(m, p, b=None, t=900):
    r = urllib.request.Request(B + p, data=json.dumps(b).encode() if b is not None else None, method=m)
    r.add_header("Content-Type", "application/json")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=t) as x:
            return x.status, json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:500]


def _xlsx_bytes():
    """在内存里造一份真实 xlsx（银行流水样式，能被指纹识别），无需落盘模板。"""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["交易日期", "对方户名", "对方账号", "借方金额", "贷方金额", "余额", "摘要"])
    ws.append(["2025-01-05", "深圳市某某科技有限公司", "6222021234567890", 120000.00, "", 380000.00, "货款"])
    ws.append(["2025-01-18", "广州市某某贸易有限公司", "6222029876543210", "", 95000.00, 475000.00, "收款"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def upload_synthetic():
    """经真实上传接口登记一份合成资料，返回 (doc_id, disk_path)。"""
    name = f"句柄验证_{uuid.uuid4().hex[:8]}.xlsx"
    data = _xlsx_bytes()
    boundary = "----wbboundary" + uuid.uuid4().hex
    body = io.BytesIO()

    def w(s):
        body.write(s.encode("utf-8") if isinstance(s, str) else s)

    w(f"--{boundary}\r\n")
    w(f'Content-Disposition: form-data; name="files"; filename="{name}"\r\n')
    w("Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
    w(data)
    w(f"\r\n--{boundary}--\r\n")
    payload = body.getvalue()
    r = urllib.request.Request(
        B + f"/api/tax-risk-docs/upload?company_id={CID}",
        data=payload,
        method="POST",
    )
    r.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    if CS:
        r.add_header("X-CSRF-Token", CS)
    try:
        with OP.open(r, timeout=300) as x:
            js = json.loads(x.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        print("   上传失败:", e.code, e.read().decode("utf-8", "replace")[:300])
        return None, None
    st, lst = req("GET", f"/api/tax-risk-docs/list?company_id={CID}")
    lst = lst if isinstance(lst, list) else []
    hit = next((d for d in lst if d.get("original_name") == name), None)
    if not hit:
        print("   上传后列表未出现该文件:", js if isinstance(js, dict) else js)
        return None, None
    return hit["id"], os.path.join(ROOT, "data", "uploads", str(CID), f"{CID}_{hit['id']}_{name}")


st, js = req("POST", "/api/auth/login", {"username": "admin", "password": "Admin@2024caishui"})
CS = next((c.value for c in CJ if c.name == "csrf_token"), "")
print("① 登录:", js.get("ok"))

doc_id, path = upload_synthetic()
if not doc_id:
    sys.exit(2)
print(f"   已上传合成资料 doc_id={doc_id}")
print("   落盘路径存在:", os.path.exists(path), "|", os.path.basename(path or ""))

print("\n② 强制分析（真实跑管道，会打开并关闭该 xlsx）")
st, s = req("POST", f"/api/tax-risk-docs/analyze-start?company_id={CID}&force=1")
print("   analyze-start:", json.dumps(s, ensure_ascii=False)[:200])
tid = s.get("task_id")
stt = {}
_transient = 0
for _ in range(450):
    st, stt = req("GET", "/api/tax-risk-docs/analyze-status/" + str(tid))
    if not isinstance(stt, dict):
        # 环境瞬时异常（如 sqlite 临时只读）不应让验证脚本崩溃
        _transient += 1
        if _transient > 6:
            print("   状态查询持续异常:", st, str(stt)[:200])
            break
        time.sleep(2)
        continue
    _transient = 0
    if stt.get("status") in ("done", "error"):
        break
    time.sleep(2)
print("   分析结束:", stt.get("status"), stt.get("progress"))
if stt.get("status") != "done":
    print("! 分析未成功:", stt.get("message"))
    req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": [doc_id]})
    sys.exit(3)

print("   分析后文件可自由重命名:", end=" ")
try:
    os.replace(path, path + ".r")
    os.replace(path + ".r", path)
    print("是（本服务句柄已释放）")
except PermissionError as e:
    print("否 —— 仍被占用:", e)

print("\n③ 分析后立即删除该资料")
st, res = req("POST", "/api/tax-risk-docs/batch-delete", {"company_id": CID, "doc_ids": [doc_id]})
print("   HTTP", st, "→", json.dumps(res, ensure_ascii=False)[:500])

print("\n④ 断言")
ok = True
if not isinstance(res, dict):
    ok = False
    print("   ✗ 返回非 JSON")
else:
    if res.get("disk_removed") != 1:
        ok = False
        print(f"   ✗ disk_removed={res.get('disk_removed')}，期望 1")
    if res.get("left_on_disk"):
        ok = False
        print(f"   ✗ left_on_disk={res.get('left_on_disk')}，文件仍留在磁盘")
    if res.get("failures"):
        ok = False
        print("   ✗ 存在失败明细:", res.get("failures"))
if path and os.path.exists(path):
    ok = False
    print("   ✗ 文件仍在磁盘:", path)

if ok:
    print("   ✓ 分析后立即删除成功：磁盘真实消失、无占用、无失败明细")
    print("   ✓ 结论：'文件被程序占用' 的占用者曾是本服务自身的解析句柄，现已消除")

# 自清理放在结论之后，且整体兜底：环境的安全删除守护对单轮 os.remove 计数有限额，
# 被拦截时不得影响验证结论（清理残留可另行处理）。
try:
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from runtime_storage import load_doc_tombstones, save_doc_tombstones
    trash = os.path.join(ROOT, "data", "trash")
    stem = os.path.basename(path) if path else ""
    removed = 0
    for f in (os.listdir(trash) if os.path.isdir(trash) else []):
        if stem and stem.split(".")[0] in f:
            try:
                os.remove(os.path.join(trash, f))
                removed += 1
            except OSError:
                pass
    tb = load_doc_tombstones()
    cleared = 0
    for k in [k for k in tb if stem and os.path.basename(k) == stem]:
        tb.pop(k, None)
        cleared += 1
    save_doc_tombstones(tb)
    print(f"   [清理] 回收站副本移除 {removed} 个、墓碑清除 {cleared} 条")
except BaseException as exc:      # 含守护进程抛出的 BaseException，一律不影响结论
    print("   [清理] 被环境删除守护拦截或异常（不影响上述结论）:", type(exc).__name__)

sys.exit(0 if ok else 1)
