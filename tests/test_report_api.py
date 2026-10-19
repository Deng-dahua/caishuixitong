# -*- coding: utf-8 -*-
"""P0-7 报告生成与导出 —— 四类测试 + 反向验证。

| 类 | 覆盖 |
|---|---|
| `ReportRenderUnitTests` | **模板渲染**：文档模型 → 4 格式；块类型；视图-章节映射；名称合规（不含禁用别名） |
| `ReportIntegrationTests` | **生成 → 导出**端到端：接口 + 落盘 + 版本台账登记/回读 + 审计 |
| `ReportFormatTests` | **各格式导出**：4 格式均可解析、媒体类型正确、登记表与文件一致 |
| `ReportWatermarkDisclaimerTests` | **水印与免责声明**：4 格式均**真嵌入**、含复核标识；缺声明/自写声明**必须被拒** |
| `ReportPerformanceTests` | 生成耗时 **< 180 秒**（任务书验收标准；同时给出实测值） |
| `ReportReverseVerification` | 停用免责声明校验 ⇒ 缺声明的报告**必须被产出**（证明判据在判）；还原后恢复 |

★ 每个用例都在**隔离的 `APP_DATA_DIR`** 子进程里跑，并复制真实产物载荷
  `scripts/four_reports/company_1_full.json` ⇒ 在**真实数据**上验证（而非构造假载荷）。
"""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ADMIN_USER = "reportadmin"
ADMIN_PASS = "Report-Admin-2026!"
USCC = "91440300MA5H824G7M"

_BOOT = """
import base64, glob, io, json, os, shutil, sqlite3, sys, tempfile, time
D = tempfile.mkdtemp()
os.environ['APP_DATA_DIR'] = D
os.environ.update({
    'APP_COOKIE_SECURE': '0', 'APP_ALLOWED_ORIGINS': 'http://testserver',
    'APP_ADMIN_USERNAME': %(admin_user)r, 'APP_ADMIN_PASSWORD': %(admin_pass)r,
    'APP_LLM_MASTER_KEY': base64.urlsafe_b64encode(bytes(range(32))).decode('ascii'),
})
sys.path.insert(0, %(root)r)
os.makedirs(os.path.join(D, 'offline_reports'), exist_ok=True)
shutil.copy(os.path.join(%(root)r, 'scripts', 'four_reports', 'company_1_full.json'),
            os.path.join(D, 'offline_reports', 'company_1_full.json'))
from fastapi.testclient import TestClient
import security
from main import app
BASE = '/api/v1'
USCC = %(uscc)r
ADMIN_USER = %(admin_user)r
ADMIN_PASS = %(admin_pass)r
from security import SessionContext


def sess(uid=1, uname='t', role='admin', cids=(1,)):
    return SessionContext(user_id=uid, username=uname, role=role,
                          allowed_company_ids=frozenset(cids), selected_company_id=1,
                          csrf_hash='', expires_at=0)


def make_project(client=None, headers=None):
    '''建账套 + 项目；返回 (company_id, project_id)。client 为空 ⇒ 直接用 Service 层。'''
    from engine import project_service as P
    if client is None:
        p = P.create_project({'name': '报告项目', 'company_id': 1, 'taxpayer_id': USCC,
                             'period_start': '2025-01', 'period_end': '2025-12',
                             'tax_scopes': ['增值税']}, sess())
        return 1, p['id']
    cid = client.post('/api/companies', headers=headers,
                      json={'name': '报告企业', 'uscc': USCC}).json()['id']
    client.post('/api/auth/select-company', headers=headers, json={'company_id': cid})
    pid = client.post('/api/v1/projects', headers=headers,
                      json={'name': '报告项目', 'company_id': cid, 'taxpayer_id': USCC,
                            'period_start': '2025-01', 'period_end': '2025-12'}).json()['id']
    return cid, pid
"""


def _boot() -> str:
    return _BOOT % {"admin_user": ADMIN_USER, "admin_pass": ADMIN_PASS,
                    "root": str(ROOT), "uscc": USCC}


def _run(script: str, *, timeout: int = 900):
    """在隔离的 `APP_DATA_DIR` 临时目录里跑一段脚本（脚本自带完整缩进）。"""
    with tempfile.TemporaryDirectory() as directory:
        environment = os.environ.copy()
        environment.update({
            "APP_DATA_DIR": directory,
            "APP_COOKIE_SECURE": "0",
            "APP_ALLOWED_ORIGINS": "http://testserver",
            "APP_ADMIN_USERNAME": ADMIN_USER,
            "APP_ADMIN_PASSWORD": ADMIN_PASS,
            "APP_LLM_MASTER_KEY": base64.urlsafe_b64encode(bytes(range(32))).decode("ascii"),
        })
        return subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                              env=environment, capture_output=True, text=True,
                              timeout=timeout)


def _assert_ok(result, marker: str) -> None:
    assert result.returncode == 0, (
        "脚本失败（exit=%s）\n--- stderr 头部 ---\n%s\n--- stdout 尾部 ---\n%s"
        % (result.returncode, result.stderr[:1500], result.stdout[-1200:]))
    assert marker in result.stdout, (
        "未见通过标记 %r\n--- stdout ---\n%s" % (marker, result.stdout[-3000:]))


# ══════════════════════════════════════════════════════════════════════════
class ReportRenderUnitTests(unittest.TestCase):
    """单元：文档模型渲染 / 视图-章节映射 / 名称合规。"""

    def test_model_render_and_view_mapping(self):
        script = _boot() + textwrap.dedent("""
            from engine import report_render as R, report_service as RS, report_views as V

            # 1) 视图与格式权威
            assert list(V.VIEWS) == ['full', 'tax_specific', 'management', 'self_check']
            assert list(V.FORMATS) == ['pdf', 'docx', 'xlsx', 'html']
            assert len(V.SECTIONS) == 12, '任务书要求 12 个章节'
            for s in V.SECTIONS:
                assert V.SECTION_CN.get(s), s
            # 2) 名称合规：以唯一名称开头且不含禁用别名
            assert V.verify_view_names() == [], V.verify_view_names()
            # 2b) ★ 2026-10-19：视图之间必须**真的不同**（tax_specific 曾与 full 完全重复）
            assert V.verify_view_focus() == [], V.verify_view_focus()
            assert V.focus_of('tax_specific') == 'tax'
            assert V.focus_of('full') == 'severity'
            from engine.report_identity import canonical_name
            cn = canonical_name()
            for v in V.VIEWS:
                nm = V.name_of(v)
                assert nm.startswith(cn + '（') and nm.endswith('）'), nm
            # 3) 视图-章节映射与"如实登记被裁章节"
            assert set(V.sections_of('full')) == set(V.SECTIONS)
            assert V.omitted_sections_of('full') == []
            for v in ('tax_specific', 'management', 'self_check'):
                keep, omit = set(V.sections_of(v)), set(V.omitted_sections_of(v))
                assert keep & omit == set(), (v, keep & omit)
                assert keep | omit == set(V.SECTIONS), (v, keep | omit)
            # 4) 格式校验
            assert V.validate_formats(None) == list(V.FORMATS)
            assert V.validate_formats('PDF, xlsx') == ['pdf', 'xlsx']
            for bad in ('csv', 'ppt', 'doc'):
                try:
                    V.validate_format(bad)
                    raise AssertionError('非法格式应报错：%s' % bad)
                except V.ReportViewError as exc:
                    assert exc.status == 400

            # 5) 文档模型（真实数据）四格式渲染
            cid, pid = make_project()
            doc = RS.build_document(pid, sess(), view='full')
            assert doc['sections'] and doc['disclaimer']['identity_line']
            keys = [s['key'] for s in doc['sections']]
            assert keys == list(V.sections_of('full')), keys
            types = {b.get('type') for s in doc['sections'] for b in s['blocks']}
            assert types <= {'paragraph', 'kv', 'table', 'list', 'note'}, types
            # 表格行必须是 list（构造处已归一；曾因元组导致 PDF AttributeError）
            for s in doc['sections']:
                for b in s['blocks']:
                    if b.get('type') == 'table':
                        for row in b['rows']:
                            assert isinstance(row, list), (s['key'], type(row))
            for f in V.FORMATS:
                data, mode = R.render(doc, f)
                assert data and mode == 'embedded'
            # 6) 文件名：无路径分隔符（防越界写）
            for f in V.FORMATS:
                nm = R.filename_of(doc, f)
                assert '/' not in nm and '\\\\' not in nm, nm

            print("P07 RENDER UNIT TESTS PASSED")
            """)
        _assert_ok(_run(script), "P07 RENDER UNIT TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class ReportIntegrationTests(unittest.TestCase):
    """集成：生成 → 导出（接口 + 落盘 + 版本台账 + 审计）。"""

    def test_generate_export_end_to_end(self):
        script = _boot() + textwrap.dedent("""
            with TestClient(app) as c:
                c.post('/api/auth/login',
                       json={'username': ADMIN_USER, 'password': ADMIN_PASS})
                h = {'X-CSRF-Token': c.cookies.get('csrf_token')}
                cid, pid = make_project(c, h)

                # 1) 字典
                m = c.get(BASE + '/reports/meta').json()
                assert len(m['views']) == 4 and len(m['formats']) == 4, m
                assert len(m['sections']) == 12
                assert m['audit']['generate'].startswith('report.export')

                # 2) 生成（4 格式）
                r = c.post(BASE + '/projects/%d/reports' % pid, headers=h,
                           json={'view': 'full'})
                assert r.status_code == 200, r.text
                out = r.json()
                assert out['doc_no'] and out['version'] == 'V1', out
                assert set(out['files']) == {'pdf', 'docx', 'xlsx', 'html'}, out['files']
                assert out['reviewed'] is False, '无处置记录 ⇒ 必须标为未复核'
                assert out['section_count'] == 12 and out['finding_count'] > 0
                assert out['omitted_sections'] == []

                # 3) 落盘（隔离目录内）+ 登记表
                from runtime_storage import report_output_root
                root = report_output_root()
                assert root.startswith(D), (root, D)
                for f, rel in out['files'].items():
                    assert os.path.exists(os.path.join(root, rel)), rel
                conn = sqlite3.connect(os.path.join(D, 'accounting.db'))
                row = conn.execute('select doc_no, version, view, reviewed, '
                                   'section_count, finding_count from reports').fetchone()
                assert row[0] == out['doc_no'] and row[1] == out['version'], row
                assert row[2] == 'full' and row[3] == 0 and row[4] == 12, row

                # 4) 版本台账（隔离目录内的台账，**唯一权威**）
                from engine import report_compliance as RC
                assert str(RC.ledger_path()).startswith(D), RC.ledger_path()
                led = RC.change_log(cid, limit=50)
                assert len(led) == 1 and led[0]['doc_no'] == out['doc_no'], led
                assert led[0]['edition_kind'] == 'internal_working_paper', led[0]
                assert led[0]['reviewed'] is False

                # 5) 详情（台账回读）
                det = c.get(BASE + '/reports/' + out['doc_no']).json()
                assert det['version_in_ledger'] is True, det
                assert det['available_formats'] == ['pdf', 'docx', 'xlsx', 'html']
                assert det['version_record']['doc_no'] == out['doc_no']
                assert det['version_record']['change_note'].startswith('生成报告')

                # 6) 列表与版本台账接口
                assert c.get(BASE + '/reports', params={'project_id': pid}).json()['total'] == 1
                assert c.get(BASE + '/reports', params={'project_id': pid,
                                                        'view': 'full'}).json()['total'] == 1
                assert c.get(BASE + '/reports', params={'project_id': pid,
                                                        'view': 'management'}).json()['total'] == 0
                assert len(c.get(BASE + '/reports/versions',
                                 params={'company_id': cid}).json()['items']) == 1

                # 7) 再生成 ⇒ 版本递增（V2），且**不复用**旧文件
                out2 = c.post(BASE + '/projects/%d/reports' % pid, headers=h,
                              json={'view': 'management', 'formats': 'pdf'}).json()
                assert out2['version'] == 'V2', out2
                assert set(out2['files']) == {'pdf'}, out2['files']
                assert out2['omitted_sections'], '摘要视图必须如实登记未含章节'
                assert out2['doc_no'] != out['doc_no']
                assert len(c.get(BASE + '/reports/versions',
                                 params={'company_id': cid}).json()['items']) == 2

                # 8) 审计（生成 + 下载；复用既有动作，不新增）
                acts = dict(conn.execute(
                    'select action, count(*) from audit_logs group by action'))
                assert acts.get('report.export') == 2, acts
                assert not any(k.startswith('report.generate') for k in acts), acts

                # 9) 未产出格式 ⇒ 明确 404（不静默用别的格式顶替）
                miss = c.get(BASE + '/reports/%s/download' % out2['doc_no'],
                             params={'format': 'docx'})
                assert miss.status_code == 404 and '未产出' in miss.json()['detail'], miss.text

                # 10) 非法参数
                assert c.post(BASE + '/projects/%d/reports' % pid, headers=h,
                              json={'view': 'xx'}).status_code == 400
                assert c.post(BASE + '/projects/%d/reports' % pid, headers=h,
                              json={'view': 'full', 'formats': 'csv'}).status_code == 400
                assert c.get(BASE + '/reports/NOPE-000000').status_code == 404

                # 11) 跨租户不可见（一律 404，不泄露存在性）
                uid = security.create_user('repuser', 'Rep-User-2026!', role='user')
                security.grant_company_to_user(uid, 999)
                with TestClient(app) as u:
                    u.post('/api/auth/login',
                           json={'username': 'repuser', 'password': 'Rep-User-2026!'})
                    uh = {'X-CSRF-Token': u.cookies.get('csrf_token')}
                    codes = {
                        '列表': u.get(BASE + '/reports',
                                    params={'company_id': cid}).status_code,
                        '详情': u.get(BASE + '/reports/' + out['doc_no']).status_code,
                        '下载': u.get(BASE + '/reports/%s/download' % out['doc_no'],
                                    params={'format': 'pdf'}).status_code,
                        '版本': u.get(BASE + '/reports/versions',
                                    params={'company_id': cid}).status_code,
                        '生成': u.post(BASE + '/projects/%d/reports' % pid, headers=uh,
                                     json={'view': 'full'}).status_code,
                    }
                    print('跨租户状态码:', codes)
                    assert not {k: v for k, v in codes.items() if v == 200}, codes

                # 12) 前端契约
                page = c.get('/reports')
                assert page.status_code == 200 and '报告生成与导出' in page.text
                assert '/static/js/reports.js' in page.text
                assert c.get('/static/js/reports.js').status_code == 200
                assert '/reports' in c.get('/').text

                print("P07 INTEGRATION TESTS PASSED")
            """)
        _assert_ok(_run(script), "P07 INTEGRATION TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class ReportFormatTests(unittest.TestCase):
    """各格式导出：可解析、媒体类型正确、与登记表一致。"""

    def test_all_formats_exportable(self):
        script = _boot() + textwrap.dedent("""
            import docx as _docx, openpyxl
            from pypdf import PdfReader
            from engine import report_views as V

            with TestClient(app) as c:
                c.post('/api/auth/login',
                       json={'username': ADMIN_USER, 'password': ADMIN_PASS})
                h = {'X-CSRF-Token': c.cookies.get('csrf_token')}
                cid, pid = make_project(c, h)
                out = c.post(BASE + '/projects/%d/reports' % pid, headers=h,
                             json={'view': 'full'}).json()
                assert set(out['files']) == set(V.FORMATS)

                got = {}
                for f in V.FORMATS:
                    r = c.get(BASE + '/reports/%s/download' % out['doc_no'],
                              params={'format': f})
                    assert r.status_code == 200, (f, r.text[:200])
                    b = r.content
                    assert b, f
                    got[f] = b
                    # 媒体类型按权威表
                    assert r.headers['content-type'].startswith(
                        V.FORMAT_MEDIA[f].split(';')[0]), (f, r.headers['content-type'])
                    # 水印方式与复核状态如实回执
                    assert r.headers['X-Watermark-Mode'] == 'embedded', f
                    assert r.headers['X-Watermark-Method'] == V.WATERMARK_METHOD[f], f
                    assert r.headers['X-Review-Status'] == 'not_reviewed', f
                    assert r.headers['X-Report-No'] == out['doc_no'], f

                # 1) PDF：可解析、页数 ≥ 1、文字层含关键内容
                pdf = PdfReader(io.BytesIO(got['pdf']))
                assert len(pdf.pages) >= 1, len(pdf.pages)
                t = ''.join((p.extract_text() or '') for p in pdf.pages)
                for kw in ('内部辅助分析工作底稿', '免责声明', '风险总览', '证据链'):
                    assert kw in t, ('PDF 缺 %s' % kw)
                # 2) DOCX：可解析、有段落与表格
                dx = _docx.Document(io.BytesIO(got['docx']))
                assert len(dx.paragraphs) > 5 and len(dx.tables) >= 3, (
                    len(dx.paragraphs), len(dx.tables))
                body = ' '.join(p.text for p in dx.paragraphs)
                for kw in ('免责声明', '风险总览'):
                    assert kw in body, ('DOCX 缺 %s' % kw)
                # 3) XLSX：可解析、多工作表、含 12 章节名
                wb = openpyxl.load_workbook(io.BytesIO(got['xlsx']))
                assert len(wb.sheetnames) >= 5, wb.sheetnames
                joined = '|'.join(wb.sheetnames)
                for kw in ('免责声明', '风险总览', '证据链', '法规依据'):
                    assert kw in joined, ('XLSX 缺工作表 %s' % kw)
                # 4) HTML：可解析、含 12 个 h2 章节标题
                html = got['html'].decode('utf-8')
                for s in V.SECTIONS:
                    assert ('<h2>%s</h2>' % V.SECTION_CN[s]) in html, (
                        'HTML 缺章节 %s' % V.SECTION_CN[s])
                assert html.count('<h2>') >= 12, html.count('<h2>')

                # 5) 登记表 files 与磁盘一致
                from runtime_storage import report_output_root
                for f, rel in out['files'].items():
                    p = os.path.join(report_output_root(), rel)
                    assert os.path.exists(p), p
                    assert os.path.getsize(p) == len(got[f]), (f, os.path.getsize(p))

                # 6) 摘要视图：被裁章节必须在报告内**如实标注**
                out2 = c.post(BASE + '/projects/%d/reports' % pid, headers=h,
                              json={'view': 'management', 'formats': 'html'}).json()
                h2 = c.get(BASE + '/reports/%s/download' % out2['doc_no'],
                           params={'format': 'html'}).content.decode('utf-8')
                assert '本视图未包含的章节' in h2, '被裁章节必须如实标注'
                for key in out2['omitted_sections']:
                    assert V.SECTION_CN[key['key']] in h2, key
                print('管理摘要视图未含章节:', [x['title'] for x in out2['omitted_sections']])

                print("P07 FORMAT TESTS PASSED")
            """)
        _assert_ok(_run(script), "P07 FORMAT TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class ReportWatermarkDisclaimerTests(unittest.TestCase):
    """水印与免责声明：4 格式真嵌入 + 复核标识 + 缺声明必须被拒。"""

    def test_watermark_and_disclaimer_in_all_formats(self):
        script = _boot() + textwrap.dedent("""
            import docx as _docx, openpyxl
            from pypdf import PdfReader
            from engine import report_render as R, report_service as RS

            cid, pid = make_project()
            S = sess()

            def probe(doc):
                out = {}
                for f in ('pdf', 'docx', 'xlsx', 'html'):
                    out[f] = R.render(doc, f)[0]
                return out

            # ── 未复核 ──
            doc = RS.build_document(pid, S, view='full', reviewed=False)
            got = probe(doc)
            wm = doc['watermark_text']
            assert '未经人工复核' in wm, wm
            t = ''.join((p.extract_text() or '') for p in PdfReader(io.BytesIO(got['pdf'])).pages)
            assert '内部使用' in t and '未经人工复核' in t, 'PDF 水印未嵌入'
            assert '不具有税务机关行政执法文书的效力' in t, 'PDF 缺免责声明'
            dx = _docx.Document(io.BytesIO(got['docx']))
            hdr = ' '.join(p.text for s in dx.sections for p in s.header.paragraphs)
            assert '内部使用' in hdr and '未经人工复核' in hdr, 'DOCX 页眉水印缺失'
            assert '不具有税务机关行政执法文书的效力' in hdr, 'DOCX 页眉缺免责声明'
            wb = openpyxl.load_workbook(io.BytesIO(got['xlsx']))
            ws = wb[wb.sheetnames[0]]
            assert '内部使用' in (ws.oddHeader.center.text or ''), 'XLSX 页眉水印缺失'
            assert '不具有税务机关' in (ws.oddFooter.left.text or ''), 'XLSX 页脚缺免责声明'
            h = got['html'].decode('utf-8')
            assert "class='wm'" in h and '未经人工复核' in h, 'HTML 水印层缺失'
            assert '不具有税务机关行政执法文书的效力' in h, 'HTML 缺免责声明'

            # ── 已复核（人工复核标识必须随水印与页眉走） ──
            doc2 = RS.build_document(pid, S, view='full', reviewed=True,
                                     reviewed_by='复核员甲')
            assert '已复核' in doc2['watermark_text'] and '复核员甲' in doc2['watermark_text']
            got2 = probe(doc2)
            t2 = ''.join((p.extract_text() or '') for p in PdfReader(io.BytesIO(got2['pdf'])).pages)
            assert '已复核' in t2 and '复核员甲' in t2, 'PDF 未体现已复核标识'
            h2 = got2['html'].decode('utf-8')
            assert '已复核' in h2, 'HTML 未体现已复核标识'

            # ── 缺免责声明章节 / 自写声明顶替 ⇒ **必须被拒**（不得产出无声明的报告） ──
            bad = dict(doc)
            bad['sections'] = [s for s in doc['sections'] if s['key'] != 'disclaimer']
            try:
                R.render(bad, 'html')
                raise AssertionError('缺免责声明章节仍被渲染 ⇒ 判据是假的')
            except R.ReportRenderError as exc:
                assert exc.status == 500 and '免责声明' in exc.message, exc.message
            bad2 = dict(doc)
            bad2['sections'] = [dict(s) for s in doc['sections']]
            for s in bad2['sections']:
                if s['key'] == 'disclaimer':
                    s['blocks'] = [{'type': 'paragraph', 'text': '本报告仅供参考。'}]
            try:
                R.render(bad2, 'docx')
                raise AssertionError('自写声明顶替仍被渲染 ⇒ 判据是假的')
            except R.ReportRenderError as exc:
                assert 'identity_line' in exc.message, exc.message

            # ── 生成回执必须自证：免责声明存在 + 水印方式为 embedded ──
            with TestClient(app) as c:
                c.post('/api/auth/login',
                       json={'username': ADMIN_USER, 'password': ADMIN_PASS})
                hh = {'X-CSRF-Token': c.cookies.get('csrf_token')}
                cid2, pid2 = make_project(c, hh)
                out = c.post(BASE + '/projects/%d/reports' % pid2, headers=hh,
                             json={'view': 'full', 'reviewed': True,
                                   'reviewed_by': '复核员乙'}).json()
                assert out['disclaimer_present'] is True
                assert out['reviewed'] is True
                assert set(out['watermark_mode'].values()) == {'embedded'}, out['watermark_mode']
                r1 = c.get(BASE + '/reports/%s/download' % out['doc_no'],
                           params={'format': 'pdf'})
                assert r1.headers['X-Review-Status'] == 'reviewed'
                print("P07 WATERMARK/DISCLAIMER TESTS PASSED")
            """)
        _assert_ok(_run(script), "P07 WATERMARK/DISCLAIMER TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class ReportPerformanceTests(unittest.TestCase):
    """生成耗时 < 180 秒（任务书验收标准）。"""

    def test_generation_under_three_minutes(self):
        script = _boot() + textwrap.dedent("""
            cid, pid = make_project()
            S = sess()
            from engine import report_service as RS
            t = []
            for view in ('full', 'management', 'self_check'):
                t0 = time.time()
                out = RS.generate(pid, S, view=view)
                dt = time.time() - t0
                t.append((view, out['elapsed_seconds'], dt))
                assert out['doc_no'] and out['version'], out
            for view, engine_s, wall_s in t:
                print('  %-12s 引擎计时 %.2fs / 实测 %.2fs' % (view, engine_s, wall_s))
                assert engine_s < 180, ('超过 3 分钟', view, engine_s)
                assert wall_s < 180, ('超过 3 分钟（实测）', view, wall_s)
            print('最慢一次：%.2fs（阈值 180s）' % max(x[2] for x in t))
            print("P07 PERFORMANCE TESTS PASSED")
            """)
        _assert_ok(_run(script), "P07 PERFORMANCE TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class ReportReverseVerification(unittest.TestCase):
    """反向验证：停用免责声明校验 ⇒ 缺声明的报告**必须被产出**（证明判据在判）。"""

    def test_broken_disclaimer_guard_lets_it_pass(self):
        target = ROOT / "engine" / "report_render.py"
        backup = target.with_suffix(".py.rvtmp")
        shutil.copy(target, backup)
        broken = None
        try:
            text = target.read_text(encoding="utf-8")
            old = ('    if hit is None:\n'
                   '        raise ReportRenderError(\n'
                   '            "报告缺少「免责声明」章节（`key=disclaimer`）—— 免责声明必须成节呈现，"\n'
                   '            "不得只放在元数据里", 500)')
            new = ('    if hit is None:\n'
                   '        return d   # 反向验证注入：停用"必须成节"校验')
            assert old in text, "锚点未命中（免责声明成节校验）"
            target.write_text(text.replace(old, new, 1), encoding="utf-8")

            script = _boot() + textwrap.dedent("""
                from engine import report_render as R, report_service as RS
                cid, pid = make_project()
                doc = RS.build_document(pid, sess(), view='full', reviewed=False)
                bad = dict(doc)
                bad['sections'] = [s for s in doc['sections'] if s['key'] != 'disclaimer']
                data, mode = R.render(bad, 'html')
                print('缺声明仍渲染成功，字节数:', len(data))
                print("RV ILLEGAL PASSED")
                """)
            broken = _run(script)
            print("注入后 stdout:", broken.stdout[-300:])
        finally:
            shutil.copy(backup, target)
            os.remove(backup)

        self.assertFalse(backup.exists(), "残留 .rvtmp 未清理")
        self.assertIn("RV ILLEGAL PASSED", broken.stdout,
                      "★ 判据失效：停用校验后缺声明的报告仍被拒 ⇒ 该断言是假的\n%s"
                      % broken.stdout[-1500:])

        script2 = _boot() + textwrap.dedent("""
            from engine import report_render as R, report_service as RS
            cid, pid = make_project()
            doc = RS.build_document(pid, sess(), view='full', reviewed=False)
            bad = dict(doc)
            bad['sections'] = [s for s in doc['sections'] if s['key'] != 'disclaimer']
            try:
                R.render(bad, 'html')
                raise AssertionError('还原后缺声明仍被放行 ⇒ 判据无效')
            except R.ReportRenderError as exc:
                assert '免责声明' in exc.message, exc.message
            print("RV RESTORED OK")
            """)
        _assert_ok(_run(script2), "RV RESTORED OK")


if __name__ == "__main__":
    unittest.main()
