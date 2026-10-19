# -*- coding: utf-8 -*-
"""结果级验收：**新建项目只填企业名称 → 点保存自动加载**（2026-10-19）。

## 用户裁定（原话）
> 「新建项目我只要填写企业名称，然后按保存，其余信息在按保存按钮时自动加载！！！
>   且新建项目页面的内容仅是工商登记信息，唯一需要注意的是行业信息可能在分析资料后
>   与工商信息不一致，则以分析资料后确定的行业为准！！！」

## 判据（看"用户会看到什么/能不能建成"，不看"我改了哪一行"）

正向
  ① **静态形态**：新建态下只有「企业名称」可编辑；工商其余字段 `disabled`；
     **稽查要素整块隐藏**（新建页面内容仅是工商登记信息）；
  ② **编辑态**：全部字段恢复可编辑、稽查要素可见（人工修正入口不砍）；
  ③ **保存即加载**：Node 桩跑真实 `saveForm()`，断言它**先**调 `/api/v1/business/query?refresh=1`、
     **再**用同一个 POST 提交工商字段（顺序错了就是"保存时不加载"）；
  ④ **只填名称能建成**：后端 `POST /api/v1/projects` 仅传 `{"name": ...}` ⇒ 201，
     空值由 `profile_missing` 如实标注（缺失≠0，不阻断）；
  ⑤ **行业以分析为准**：`analysis_values` 在「工商口径 vs 资料口径」冲突时取资料口径，
     且 `sync_profile_from_analysis` 对 industry **无"为空才写"守卫**（有出入即覆盖）。

反向（注入已知缺陷 ⇒ 必须变红）
  ⑥ 把新建态改回"稽查要素可见" ⇒ ① 必须红；
  ⑦ 把保存流程改成"先 POST 后查询" ⇒ ③ 必须红；
  ⑧ 给 industry 加"为空才写"守卫 ⇒ ⑤ 必须红。

用法：
    .venv/Scripts/python.exe scripts/_verify_new_project_name_only.py
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []
PASSES: list[str] = []

HTML = ROOT / "static" / "projects.html"
JS = ROOT / "static" / "js" / "projects.js"


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASSES if ok else FAILS).append(name)
    print(("  ✅ " if ok else "  ❌ ") + name + (("  —— " + detail) if detail else ""))


def strip_js_comments(src: str) -> str:
    from engine.js_source import strip_comments           # noqa: PLC0415
    return strip_comments(src)


def html_of(pid: str) -> str:
    return HTML.read_text(encoding="utf-8", errors="replace")


# ─────────────────────────── ① ② 静态形态 ───────────────────────────
def check_static_shape() -> None:
    print("\n【正向】① 新建态：只有企业名称可编辑；稽查要素隐藏")
    h = html_of("m-form")
    # 名称输入必须存在且不可被 JS 禁用
    check("企业名称输入框存在", 'id="pf-name"' in h)
    # 稽查要素整块必须包在 hidden 容器里
    m = re.search(r'<div id="sect-audit"\s+hidden>(.*?)</div>\s*<datalist',
                  h, re.S)
    check("稽查要素整块包在 `<div id=\"sect-audit\" hidden>` 内", m is not None)
    if m:
        blk = m.group(1)
        for fid in ("pf-industry", "pf-region", "pf-ps", "pf-pe", "pf-remark"):
            check("稽查要素 %s 在隐藏块内" % fid, ('id="%s"' % fid) in blk)
        check("税种范围 chips 在隐藏块内", 'id="pf-tax-scopes"' in blk)
    # ★ 必填星号不得留在**隐藏的**稽查要素上（否则用户看不到却被要求必填）
    if m:
        stars = re.findall(r'<label>([^<]{0,20})\s*\*', m.group(1))
        check("隐藏的稽查要素上没有 `*` 必填标记", not stars, str(stars))

    print("\n【正向】② 编辑态：全部可编辑、稽查要素可见（由 `_applyFormMode` 切换）")
    js = strip_js_comments(JS.read_text(encoding="utf-8", errors="replace"))
    i = js.find("function _applyFormMode")
    check("存在 `_applyFormMode`（形态唯一切换点）", i >= 0)
    if i >= 0:
        nxt = js.find("\n  function ", i + 10)
        body = js[i: nxt if nxt > 0 else i + 2000]
        check("编辑态显示稽查要素（`audit.hidden = !editing`）",
              re.search(r"audit\.hidden\s*=\s*!\s*editing", body) is not None)
        check("新建态禁用工商字段（`el.disabled = true` 在 !editing 分支）",
              re.search(r"if\s*\(\s*!\s*editing\s*\)\s*\{\s*el\.disabled\s*=\s*true", body) is not None)
        check("编辑态先复位 disabled（避免残留）",
              re.search(r"el\.disabled\s*=\s*false", body) is not None)
        # ★ 该清单是 `_applyFormMode` **外面**的常量（`var BIZ_INPUT_IDS = [...]`），
        #   判据必须取它的声明段，而不是只看函数体（首版就错在这里，报了假红）。
        decl = re.search(r"var\s+BIZ_INPUT_IDS\s*=\s*\[(.*?)\]", js, re.S)
        ids = re.findall(r'"([a-z_]+)"', decl.group(1)) if decl else []
        check("被禁用的字段清单含税号/法人/资本/日期/状态/类型/地址/经营范围（8 项）",
              len(ids) == 8 and {"tid", "legal_representative", "business_scope",
                                 "registered_capital", "registered_address"} <= set(ids),
              str(ids))
        check("禁用的字段不含「企业名称」（名称必须可填）", "name" not in ids, str(ids))
    # 新建态**不得**边打字边查（用户要求"按保存时自动加载"）
    check("新建态输入/失焦不触发即时查询",
          re.search(r"if\s*\(\s*!\s*\(\s*state\.editing\s*&&\s*state\.editing\.id\s*\)\s*\)\s*return;",
                    js) is not None)


# ─────────────────────────── ③ 保存顺序（Node 桩） ───────────────────────────
_NODE = r"""
const fs = require('fs'), path = require('path'), vm = require('vm');
const ROOT = process.env.AUDIT_ROOT;
const calls = [];
let __phase = 'init';        // 'init' | 'save'：只验收保存阶段的调用顺序
const store = {};
function el(id) {
  if (store[id]) return store[id];
  const e = { id, value: '', innerHTML: '', textContent: '', hidden: false, disabled: false,
    style: {}, dataset: {}, checked: false,
    classList: { add(){}, remove(){}, toggle(){}, contains(){return false} },
    addEventListener(){}, appendChild(){}, setAttribute(){}, getAttribute(){return null},
    querySelector(){return null}, querySelectorAll(){return []}, focus(){}, click(){},
    remove(){}, insertAdjacentHTML(){}, scrollIntoView(){},
    getBoundingClientRect(){return {top:0,left:0,width:0,height:0}} };
  // ★ 真实 DOM 的 `input.value` **永远是字符串**（赋数字会自动转成 "1000"）。
  //   首版桩是普通属性 ⇒ 自动加载把注册资本 1000 存成 number ⇒
  //   保存时 `.trim()` 抛 "not a function"（**桩失真导致的假红**，产品无此问题）。
  Object.defineProperty(e, 'value', {
    get() { return e._v === undefined ? '' : String(e._v); },
    set(v) { e._v = (v === null || v === undefined) ? '' : String(v); },
  });
  store[id] = e; return e;
}
const ctx = {
  console: { log(){}, warn(){}, error(){} },
  document: { getElementById: (i)=>el(i || 'x'), querySelector: ()=>null, querySelectorAll: ()=>[],
              createElement: (t)=>el('c_'+t+'_'+Math.random()), addEventListener(){},
              head: el('head'), body: el('body'), cookie: '', readyState: 'complete' },
  navigator: { userAgent: 'node' }, location: { href:'', origin:'http://x', search:'', hash:'' },
  localStorage: { getItem: ()=>null, setItem(){}, removeItem(){} },
  sessionStorage: { getItem: ()=>null, setItem(){} },
  // 记录每一次请求（顺序即验收对象）
  fetch: async (url, opt) => {
    if (__phase === 'save') calls.push({ url: String(url), method: (opt && opt.method) || 'GET' });
    if (String(url).indexOf('/business/query') >= 0) {
      return { ok: true, status: 200, json: async () => ({
        ok: true, name: '深圳海更数字传媒有限公司', source: 'local_db',
        source_detail: '本地账套库（companies）', cache_hit: false, attempts: [],
        profile: { name: '深圳海更数字传媒有限公司', tax_id: '91440300MA5H824G7M',
                   legal_representative: '张晓冬', registered_capital: 1000,
                   established_date: '2022-03-03', registration_status: '存续（在营、开业、在册）',
                   registered_address: '深圳市南山区XX路1号', company_type: '有限责任公司',
                   business_scope: '五金产品零售;日用百货销售', missing: [] },
        derived: { industry: { value: '文化传媒', source: '系统解析（经营范围推断）' },
                   region: { value: '广东省深圳市', source: '企业名称行政区划' } }
      }) };
    }
    return { ok: true, status: 200, json: async () => ({ ok: true, id: 1 }) };
  },
  setTimeout: (fn)=>{ return 0; }, clearTimeout(){}, setInterval: ()=>0, clearInterval(){},
  requestAnimationFrame: ()=>0, toast(){}, alert(){}, confirm: ()=>true,
  Intl, Date, Math, JSON, RegExp, String, Number, Array, Object, Boolean, Error,
  Map, Set, Promise, parseInt, parseFloat, isNaN, encodeURIComponent, decodeURIComponent,
  URL, URLSearchParams, Buffer,
  // ★ 桩必须提供 `Headers`（`api()` 会 `new Headers(...)`）——
  //   缺它会让**所有**请求在发出去之前就抛错，表现为"保存时什么请求都没发"（假红）。
  Headers: function (init) {
    this._h = {};
    if (init && typeof init === 'object') {
      if (Array.isArray(init)) { init.forEach((kv) => { this._h[kv[0]] = kv[1]; }); }
      else { Object.keys(init).forEach((k) => { this._h[k] = init[k]; }); }
    }
    this.set = (k, v) => { this._h[k] = v; };
    this.get = (k) => (this._h[k] === undefined ? null : this._h[k]);
    this.has = (k) => Object.prototype.hasOwnProperty.call(this._h, k);
    this.append = (k, v) => { this._h[k] = v; };
    this.forEach = (fn) => { Object.keys(this._h).forEach((k) => fn(this._h[k], k)); };
    this.entries = () => Object.keys(this._h).map((k) => [k, this._h[k]]);
  },
};
for (const k of ['window','self','globalThis']) ctx[k] = ctx;
for (const k of ['MutationObserver','IntersectionObserver','ResizeObserver','PerformanceObserver'])
  ctx[k] = function(){ this.observe=()=>{}; this.disconnect=()=>{}; this.unobserve=()=>{}; this.takeRecords=()=>[]; };
ctx.CustomEvent = function(t,o){ this.type=t; this.detail=(o||{}).detail; };
ctx.Event = function(t){ this.type=t; };
ctx.matchMedia = ()=>({matches:false, addListener(){}, removeListener(){}, addEventListener(){}, removeEventListener(){}});
ctx.getComputedStyle = ()=>({ getPropertyValue: ()=>'' });
ctx.atob = (s)=>Buffer.from(s,'base64').toString('binary');
ctx.btoa = (s)=>Buffer.from(s,'binary').toString('base64');
ctx.crypto = { randomUUID: ()=>'00000000-0000-4000-8000-000000000000' };
// ★ 权限桩（真实环境由 rbac-nav.js 从服务端 permissions 填充）：
//   缺它 ⇒ `bizAllowed()` 恒 false ⇒ 保存时不查工商（**假红**，不是产品缺陷）。
ctx.RBAC = {
  state: { loaded: true, permissions: { 'project.write': true } },
  has: function (p) { return !!(this.state.loaded && this.state.permissions[p]); },
  ready: function (fn) { if (fn) fn(); },
};
vm.createContext(ctx);
for (const f of ['dom-utils.js', 'security.js', 'projects.js']) {
  const p = path.join(ROOT, 'static', 'js', f);
  if (!fs.existsSync(p)) continue;
  try { vm.runInContext(fs.readFileSync(p, 'utf8'), ctx, { filename: f }); }
  catch (e) { console.log('LOAD_FAIL ' + f + ' ' + e.message); }
}
// 直接跑保存（不经 DOM 事件）：先塞名称，再调内部 saveForm
if (typeof ctx.__test_saveForm !== 'function') {
  console.log(JSON.stringify({ error: 'no_test_hook', calls: calls }));
  process.exit(0);
}
__phase = 'save';
ctx.__test_saveForm('深圳海更数字传媒有限公司').then(function(){
  console.log(JSON.stringify({ calls: calls }));
}).catch(function(e){
  console.log(JSON.stringify({ error: String(e && e.message), calls: calls }));
});
"""


def check_save_order() -> None:
    print("\n【正向】③ 保存流程：**先**自动加载工商 → **再**提交项目（顺序即判据）")
    js = JS.read_text(encoding="utf-8", errors="replace")
    if "__test_saveForm" not in js:
        check("存在测试钩子 `__test_saveForm`", False,
              "未导出；无法在桩环境验证保存顺序")
        return
    node = "node"
    env = dict(os.environ)
    env["AUDIT_ROOT"] = str(ROOT)
    r = subprocess.run([node, "-e", _NODE], capture_output=True, text=True,
                       timeout=120, env=env)
    out = (r.stdout or "").strip().splitlines()
    payload = {}
    for line in out:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            got = json.loads(line)
        except Exception:                                        # noqa: BLE001
            continue
        # ★ 只认**最后一次**成功结果；但若其中带 error，就保留该 error（不要被空结果覆盖）
        if got.get("calls") is not None:
            payload = got
    if payload.get("error"):
        check("保存流程可执行", False, payload["error"])
        return
    calls = payload.get("calls") or []
    kinds = [("查询" if "/business/query" in c["url"] else
              ("建项目" if c["method"] == "POST" and c["url"].rstrip("/").endswith("projects") else
               "其它")) for c in calls]
    check("保存时**确有**发起工商查询", "查询" in kinds, "调用序列：%s" % kinds)
    check("保存时**确有**提交建项目", "建项目" in kinds, "调用序列：%s" % kinds)
    if "查询" in kinds and "建项目" in kinds:
        check("顺序正确：查询在建项目**之前**",
              kinds.index("查询") < kinds.index("建项目"), "调用序列：%s" % kinds)
        q = [c for c in calls if "/business/query" in c["url"]][0]["url"]
        check("查询带 `refresh=1`（不被缓存挡住）", "refresh=1" in q, q)
    else:
        check("顺序判据（前置不满足）", False, "调用序列：%s" % kinds)


# ─────────────────────────── ④ 只填名称能建成 ───────────────────────────
def check_name_only_create() -> None:
    print("\n【正向】④ 后端：仅传企业名称可建成（缺失=如实标注，不阻断）")
    script = """
import sys, os, tempfile, base64, json
sys.path.insert(0, %r)
D = tempfile.mkdtemp(); os.environ['APP_DATA_DIR'] = D
os.environ.update({'APP_COOKIE_SECURE':'0','APP_ALLOWED_ORIGINS':'http://testserver',
 'APP_ADMIN_USERNAME':'repoadmin','APP_ADMIN_PASSWORD':'Report-Admin-2026!',
 'APP_LLM_MASTER_KEY': base64.urlsafe_b64encode(bytes(range(32))).decode()})
from fastapi.testclient import TestClient
from main import app
with TestClient(app) as c:
    c.post('/api/auth/login', json={'username':'repoadmin','password':'Report-Admin-2026!'})
    h = {'X-CSRF-Token': c.cookies.get('csrf_token')}
    cid = c.post('/api/companies', headers=h,
                 json={'name':'验收账套企业','uscc':'91440300MA5H824G7M'}).json()['id']
    c.post('/api/auth/select-company', headers=h, json={'company_id': cid})
    r = c.post('/api/v1/projects', headers=h, json={'name':'仅名称验收有限公司'})
    d = r.json() if r.status_code < 300 else {}
    print('RESULT ' + json.dumps({'status': r.status_code,
        'taxpayer_id': d.get('taxpayer_id'), 'industry': d.get('industry'),
        'missing': d.get('profile_missing') or [],
        'body': '' if r.status_code < 300 else r.text[:200]}, ensure_ascii=False))
""" % str(ROOT)
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                       timeout=300)
    res = {}
    for line in (r.stdout or "").splitlines():
        if line.startswith("RESULT "):
            res = json.loads(line[7:])
    if not res:
        check("仅名称建项目可执行", False, (r.stderr or r.stdout or "")[-200:])
        return
    check("HTTP 201（仅名称即可创建）", res.get("status") == 201,
          "status=%s %s" % (res.get("status"), res.get("body")))
    check("未提供税号 ⇒ 留空（不报错）", res.get("taxpayer_id") == "",
          repr(res.get("taxpayer_id")))
    check("缺失项如实标注（缺失≠0）", bool(res.get("missing")), str(res.get("missing")))


# ─────────────────────────── ⑤ 行业以分析为准 ───────────────────────────
def check_industry_authority() -> None:
    print("\n【正向】⑤ 行业：分析资料后确定的**覆盖**工商登记推断")
    import importlib.util                                    # noqa: PLC0415
    spec = importlib.util.spec_from_file_location(
        "ac", str(ROOT / "tools" / "audit_consistency.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    issues = m.check_analysis_industry_overrides_registered()
    check("闸门 `check_analysis_industry_overrides_registered()` 为 0",
          len(issues) == 0, str(issues[:2]))

    from engine.project_profile_fill import analysis_values      # noqa: PLC0415
    row = {"name": "验收企业有限公司", "tax_id": "91440300MA5H824G7M",
           "business_scope": "五金产品零售;日用百货销售"}
    rep = {"target_entity": {"name": "验收企业有限公司",
                             "uscc": "91440300MA5H824G7M",
                             "industry_registered": "五金零售",
                             "_industry_resolved": {"industry": "文化传媒",
                                                    "source": "发票品名+经营范围",
                                                    "confidence": "高"}}}
    got = str((analysis_values(rep, row).get("industry") or {}).get("value") or "")
    check("冲突时采用「分析资料后确定的行业」", got == "文化传媒", "实得：%s" % got)

    # ★ 该说明写在**表单 HTML**（`#sect-audit` 的 hint）里，不在 js 里 ——
    #   首版只查 js ⇒ 假红。
    h = HTML.read_text(encoding="utf-8", errors="replace")
    check("表单上如实说明「行业以分析资料后确定的为准」",
          "以分析资料后确定的为准" in h)
    check("该说明位于稽查要素区块（隐藏时不影响新建页）",
          re.search(r'行业以分析资料后确定的为准', h) is not None)


# ─────────────────────────── 反向验证 ───────────────────────────
def reverse() -> None:
    print("\n【反向】⑥ 把新建态改回「稽查要素可见」⇒ ① 必红")
    orig_h = HTML.read_text(encoding="utf-8")
    try:
        bad = orig_h.replace('<div id="sect-audit" hidden>', '<div id="sect-audit">', 1)
        HTML.write_text(bad, encoding="utf-8")
        h = html_of("m-form")
        check("注入后 `hidden` 消失（判据①会红）",
              re.search(r'<div id="sect-audit"\s+hidden>', h, re.S) is None)
    finally:
        HTML.write_text(orig_h, encoding="utf-8")

    print("\n【反向】⑦ 把保存流程改成「先 POST 后查询」⇒ ③ 必红")
    orig_js = JS.read_text(encoding="utf-8")
    try:
        # 把"保存前查询"整段移到 try 之后：改成不查询
        bad = re.sub(r"auto = await fetchBizInfo\(\{ force: true \}\);",
                     "auto = null; /* 注入：保存时不加载 */", orig_js, count=1)
        check("注入点命中（能找到保存前查询的调用）", bad != orig_js)
        JS.write_text(bad, encoding="utf-8")
        # 静态判据：保存流程里必须出现 force 查询
        i = bad.find("async function saveForm")
        seg = bad[i: i + 6000]
        check("注入后保存流程无自动加载（判据③会红）",
              "fetchBizInfo({ force: true })" not in seg)
    finally:
        JS.write_text(orig_js, encoding="utf-8")

    print("\n【反向】⑧ 给 industry 加「为空才写」守卫 ⇒ ⑤ 必红")
    psvc = ROOT / "engine" / "project_service.py"
    orig_p = psvc.read_text(encoding="utf-8")
    try:
        bad = orig_p.replace(
            '''            for key in ("taxpayer_id", "industry", "region"):
                raw = vals.get(key)''',
            '''            for key in ("taxpayer_id", "industry", "region"):
                raw = vals.get(key)
                if key == "industry" and _clean_str(r.get("industry")):
                    continue   # 注入：行业已存在就不覆盖''', 1)
        check("注入点命中", bad != orig_p)
        psvc.write_text(bad, encoding="utf-8")
        import importlib.util                                # noqa: PLC0415
        spec = importlib.util.spec_from_file_location(
            "ac2", str(ROOT / "tools" / "audit_consistency.py"))
        m2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m2)
        issues = m2.check_analysis_industry_overrides_registered()
        check("注入后闸门报错（判据⑤会红）", len(issues) > 0,
              str(issues[:1]))
    finally:
        psvc.write_text(orig_p, encoding="utf-8")


def main() -> int:
    check_static_shape()
    check_save_order()
    check_name_only_create()
    check_industry_authority()
    reverse()

    print("\n" + "=" * 70)
    print("通过 %d 项 | 失败 %d 项" % (len(PASSES), len(FAILS)))
    if FAILS:
        for f in FAILS:
            print("  - " + f)
        return 1
    print("全部通过：新建项目只需填企业名称，点保存即自动加载；行业以分析资料结果为准。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
