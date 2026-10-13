# -*- coding: utf-8 -*-
"""P0-6 风险结果展示与复核 —— 四类测试 + 反向验证。

| 类 | 覆盖 |
|---|---|
| `RiskUnitTests` | 筛选（税种/等级/金额/期间/状态/关键词）· 排序 · **状态机合法性** · 理由必填 · 幂等 · 缺失≠0 · 统计口径 |
| `RiskIntegrationTests` | 端到端：列表 → 详情（规则/计算/证据/法规/建议）→ 复核 → 批注 → 整改台账 → 审计 → 列表状态可见 → 前端契约 |
| `RiskPermissionTests` | 跨租户不可见（列表/详情/复核/批注/台账）· 不同角色可见范围 |
| `RiskAuditTests` | 3 个审计动作落库 · 操作人可追溯 · 被拒动作**不虚记** |
| `RiskReverseVerification` | 停用状态迁移校验 ⇒ 非法迁移必须被放行（证明判据在判）；还原后恢复 |

★ 每个用例都在**隔离的 `APP_DATA_DIR`** 子进程里跑，并把真实产物载荷
  `scripts/four_reports/company_1_full.json` 复制成 `offline_reports/company_{cid}_full.json`，
  以便在**真实数据**上验证（而非构造的假载荷）。
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

ADMIN_USER = "riskadmin"
ADMIN_PASS = "Risk-Admin-2026!"
#: 与真实产物载荷内编号一致（`company_1_full.json` 的 risk_no 含此统一社会信用代码）
USCC = "91440300MA5H824G7M"

_BOOT = """
import base64, os, shutil, sqlite3, tempfile, sys
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
        "脚本失败（exit=%s）\n--- stderr 头部（定位失败行）---\n%s\n"
        "--- stdout 尾部 ---\n%s\n--- stderr 尾部 ---\n%s"
        % (result.returncode, result.stderr[:1500], result.stdout[-1200:],
           result.stderr[-800:]))
    assert marker in result.stdout, (
        "未见通过标记 %r\n--- stdout ---\n%s" % (marker, result.stdout[-3000:]))


# ══════════════════════════════════════════════════════════════════════════
class RiskUnitTests(unittest.TestCase):
    """单元：筛选 / 排序 / 状态机 / 校验 / 统计口径。"""

    def test_filters_sort_and_state_machine(self):
        script = _boot() + textwrap.dedent("""
            from engine import risk_review as R, risk_service as S
            from security import SessionContext
            sess = SessionContext(user_id=1, username='t', role='admin',
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash='', expires_at=0)

            # 1) 列表可用
            lst = S.list_risks(1, sess, page=1, page_size=5)
            assert lst['available'] is True, lst
            total = lst['total']
            assert total > 0, '载荷应含风险事项'
            assert len(lst['items']) == 5 and lst['pages'] >= 1, lst
            for x in lst['items']:
                assert x['review_state_cn'] and x['risk_no'], x

            # 2) 筛选：税种 / 等级 / 状态 / 关键词 / 期间
            tax = S.list_risks(1, sess, tax='增值税', page_size=100)['total']
            assert 0 < tax <= total, tax
            assert S.list_risks(1, sess, level='高风险', page_size=100)['total'] == 0
            assert S.list_risks(1, sess, state='pending', page_size=100)['total'] == total
            assert S.list_risks(1, sess, reviewed='no', page_size=100)['total'] == total
            assert S.list_risks(1, sess, reviewed='yes', page_size=100)['total'] == 0
            kw = S.list_risks(1, sess, q='发票', page_size=100)['total']
            assert 0 < kw < total, kw
            pd = S.list_risks(1, sess, period='202501', page_size=100)['total']
            assert pd == total, ('期间筛选应命中全部（载荷期间为 202501）', pd)

            # 3) ★ 缺失≠0：金额筛选把"金额取不到"的条目**排除并计数**，不按 0 元处理
            am = S.list_risks(1, sess, amount_min=1, page_size=100)
            assert am['filter_stats']['excluded_unknown_amount'] > 0, am['filter_stats']
            # 命中 + 因"金额未知"被排除 ≤ 全量（其余差额为"金额已知但低于下限"，属正常筛选）
            assert (am['total'] + am['filter_stats']['excluded_unknown_amount']
                    <= total), (am['total'], am['filter_stats'], total)
            assert am['total'] < total, '金额下限筛选应真的筛掉一些'
            # 金额由后端给出（唯一权威），前端不再求和
            assert 'tax_impact_amount' in am['items'][0] and 'amount_known' in am['items'][0]

            # 4) 排序 + 非法参数明确报错（不静默退回默认）
            by_seq = S.list_risks(1, sess, sort='seq', order='asc', page_size=100)['items']
            assert [x['seq'] for x in by_seq] == sorted(x['seq'] for x in by_seq), 'seq 升序'
            for bad_kw in ({'sort': '乱写'}, {'amount_min': 'abc'}, {'amount_max': 'x'}):
                try:
                    S.list_risks(1, sess, **bad_kw)
                    raise AssertionError('非法参数应报错：%r' % (bad_kw,))
                except S.RiskServiceError as exc:
                    assert exc.status == 400, (bad_kw, exc.status)

            # 5) 状态机：合法链 + 非法迁移被拒（含"未确认不能整改"）
            rn = lst['items'][0]['risk_no']
            assert R.get(rn, 1)['state'] == 'pending'
            assert R.review(rn, 'to_manual', sess, company_id=1)['manual_required'] is True
            try:
                R.review(rn, 'rectify', sess, company_id=1, note='x')
                raise AssertionError('pending→rectified 应被拒（须先确认）')
            except R.RiskReviewError as exc:
                assert exc.status == 400 and '非法迁移' in exc.message, exc.message
            assert R.review(rn, 'confirm', sess, company_id=1)['state'] == 'confirmed'
            r3 = R.review(rn, 'rectify', sess, company_id=1, note='已补申报并缴款')
            assert r3['state'] == 'rectified', r3
            assert r3['rectification_no'].startswith('WB-RC-'), r3['rectification_no']
            try:
                R.review(rn, 'confirm', sess, company_id=1)
                raise AssertionError('rectified→confirmed 应被拒')
            except R.RiskReviewError as exc:
                assert '非法迁移' in exc.message
            assert R.review(rn, 'reopen', sess, company_id=1,
                            note='复核有误')['state'] == 'pending'
            # 重开后**历史与批注保留**（不因重开抹掉留痕）
            assert len(R.get(rn, 1)['history']) >= 4, R.get(rn, 1)['history']

            # 6) 理由必填（不生成无理由的处置）
            for act in ('exclude', 'false_positive', 'rectify', 'reopen'):
                try:
                    R.review(rn + '-x', act, sess, company_id=1)
                    raise AssertionError('%s 应要求理由' % act)
                except R.RiskReviewError as exc:
                    assert '必须填写理由' in exc.message, exc.message

            # 7) 未知动作 / 空编号 / 空批注 ⇒ 400
            for call, label in ((lambda: R.review(rn, '乱写动作', sess, company_id=1), '未知动作'),
                                (lambda: R.review('', 'confirm', sess, company_id=1), '空编号'),
                                (lambda: R.comment(rn, '   ', sess, company_id=1), '空批注')):
                try:
                    call()
                    raise AssertionError('%s 应报错' % label)
                except R.RiskReviewError as exc:
                    assert exc.status == 400, (label, exc.status)

            # 8) 幂等：同动作重复 ⇒ noop，不重复写历史
            n_before = len(R.get(rn, 1)['history'])
            got = R.review(rn, 'reopen', sess, company_id=1, note='again')
            assert got.get('noop') is True, got
            assert len(R.get(rn, 1)['history']) == n_before, '幂等不应新增历史'

            # 9) 统计口径：合计 = 各状态之和；金额未知条数被如实报出
            st = S.stats(1, sess)
            assert sum(st['by_state'].values()) == st['total'], st['by_state']
            assert sum(st['by_level'].values()) == st['total'], st['by_level']
            assert st['amount_unknown_count'] + st['pending_amount_unknown_count'] > 0
            assert st['by_amount_band'], st['by_amount_band']
            assert '未按 0 元计入' in st['notes']['amount_unknown'], st['notes']

            # 10) 元数据取权威（不硬编码）
            md = S.metadata()
            assert [a['value'] for a in md['review']['actions']] == list(R.REVIEW_ACTIONS)
            assert len(md['levels']) == 6, md['levels']

            print("P06 UNIT TESTS PASSED")
            """)
        _assert_ok(_run(script), "P06 UNIT TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class RiskIntegrationTests(unittest.TestCase):
    """集成：端到端链路（接口 + 存储 + 审计 + 前端契约）。"""

    def test_end_to_end(self):
        script = _boot() + textwrap.dedent("""
            with TestClient(app) as c:
                c.post('/api/auth/login',
                       json={'username': ADMIN_USER, 'password': ADMIN_PASS})
                h = {'X-CSRF-Token': c.cookies.get('csrf_token')}
                cid = c.post('/api/companies', headers=h,
                             json={'name': '复核测试企业', 'uscc': USCC}).json()['id']
                c.post('/api/auth/select-company', headers=h, json={'company_id': cid})
                pid = c.post('/api/v1/projects', headers=h,
                             json={'name': '复核项目', 'company_id': cid}).json()['id']

                # 1) 字典
                m = c.get(BASE + '/risks/meta').json()
                assert len(m['review']['states']) == 5, m['review']['states']
                assert len(m['review']['actions']) == 6, m['review']['actions']

                # 2) 列表（项目视角）
                r = c.get(BASE + '/projects/%d/risks' % pid, params={'page_size': 5})
                assert r.status_code == 200, r.text
                j = r.json()
                assert j['available'] and j['total'] > 0, j
                assert j['project_id'] == pid and j['company_id'] == cid
                assert 'tax_impact_amount' in j['items'][0], '金额须由后端给出'
                assert j['items'][0]['amount_known'] in (True, False)

                # 3) 统计
                st = c.get(BASE + '/projects/%d/risks/stats' % pid).json()
                assert st['available'] and st['total'] == j['total'], st

                # 4) 详情（编号）——规则/计算/证据/法规/建议齐备
                rn = j['items'][0]['risk_no']
                det = c.get(BASE + '/risks/' + rn).json()
                assert det['risk_no'] == rn and det['rule_found'] is True, det
                assert det['evidences'], '应有证据链'
                assert det['scoring']['factors'], '应有评分因子（计算过程）'
                assert det['trace']['detail_table'], '应有明细表'
                for k in ('trigger_determination', 'child_item_audit'):
                    assert k in det['trace'], k
                assert 'self_doubt' in det and 'suggestion' in det
                assert det['rule']['legal_basis_ref'], '应有法规依据'
                # 数字序号亦可取（须带 company_id；不带 ⇒ 400）
                d2 = c.get(BASE + '/risks/%d' % j['items'][0]['seq'],
                           params={'company_id': cid})
                assert d2.status_code == 200, d2.text
                assert c.get(BASE + '/risks/%d' % j['items'][0]['seq']).status_code == 400
                assert c.get(BASE + '/risks/WB-R-NOSUCH-202501-999').status_code == 404

                # 5) 复核链路
                assert c.post(BASE + '/risks/%s/review' % rn, headers=h,
                              json={'action': 'exclude'}).status_code == 400
                r1 = c.post(BASE + '/risks/%s/review' % rn, headers=h,
                            json={'action': 'confirm', 'note': '经核对成立'}).json()
                assert r1['state'] == 'confirmed', r1
                r2 = c.post(BASE + '/risks/%s/review' % rn, headers=h,
                            json={'action': 'rectify', 'note': '已补申报并缴款'}).json()
                assert r2['state'] == 'rectified' and r2['rectification_no'], r2
                c3 = c.post(BASE + '/risks/%s/comment' % rn, headers=h,
                            json={'text': '请补充银行流水'}).json()
                assert c3['comment_count'] == 1 and c3['state'] == 'rectified', c3

                # 6) 详情复核态与历史（可追溯）
                det2 = c.get(BASE + '/risks/' + rn).json()
                assert det2['review']['state'] == 'rectified', det2['review']
                assert det2['review']['comments'][0]['text'] == '请补充银行流水'
                assert len(det2['review']['history']) >= 2

                # 7) 列表按复核状态可筛（状态已生效）
                assert c.get(BASE + '/projects/%d/risks' % pid,
                             params={'state': 'rectified'}).json()['total'] == 1
                assert c.get(BASE + '/projects/%d/risks' % pid,
                             params={'reviewed': 'yes'}).json()['total'] == 1
                assert c.get(BASE + '/projects/%d/risks' % pid,
                             params={'reviewed': 'no'}).json()['total'] == j['total'] - 1

                # 8) 整改台账
                rl = c.get(BASE + '/rectifications', params={'company_id': cid}).json()
                assert rl['total'] == 1, rl
                assert rl['items'][0]['rectification_no'] == r2['rectification_no']
                assert rl['items'][0]['measure'] == '已补申报并缴款'

                # 9) 审计落库（3 动作；被拒动作不得留痕）
                conn = sqlite3.connect(os.path.join(D, 'accounting.db'))
                acts = dict(conn.execute(
                    'select action, count(*) from audit_logs group by action'))
                assert acts.get('risk.review') == 1, acts
                assert acts.get('risk.rectify') == 1, acts
                assert acts.get('risk.comment') == 1, acts
                assert 'finding.review' not in acts, (
                    '★ 复核不得落成既有 finding.review（两个概念）', acts)

                # 10) 前端契约（结果级）
                page = c.get('/risks')
                assert page.status_code == 200 and '风险结果与复核' in page.text
                for kw in ('/static/js/risks.js', 'tb-risks', 'chart', 'tb-rect'):
                    assert kw in page.text, kw
                assert c.get('/static/js/risks.js').status_code == 200
                assert '/risks' in c.get('/').text, '主界面应有入口'

                print("P06 INTEGRATION TESTS PASSED")
            """)
        _assert_ok(_run(script), "P06 INTEGRATION TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class RiskPermissionTests(unittest.TestCase):
    """权限：跨租户不可见 + 不同角色可见范围。"""

    def test_cross_tenant_invisible(self):
        script = _boot() + textwrap.dedent("""
            with TestClient(app) as c:
                c.post('/api/auth/login',
                       json={'username': ADMIN_USER, 'password': ADMIN_PASS})
                h = {'X-CSRF-Token': c.cookies.get('csrf_token')}
                a = c.post('/api/companies', headers=h,
                           json={'name': '租户A', 'uscc': USCC}).json()['id']
                b = c.post('/api/companies', headers=h,
                           json={'name': '租户B', 'uscc': '91440300MA5TB00001'}).json()['id']
                pa = c.post('/api/v1/projects', headers=h,
                            json={'name': 'A项目', 'company_id': a}).json()['id']
                rn = c.get(BASE + '/projects/%d/risks' % pa,
                           params={'page_size': 1}).json()['items'][0]['risk_no']

                # 普通用户，**只**授权账套 B（不是 A）
                uid = security.create_user('riskuser', 'Risk-User-2026!', role='user')
                security.grant_company_to_user(uid, b)
                with TestClient(app) as u:
                    u.post('/api/auth/login',
                           json={'username': 'riskuser', 'password': 'Risk-User-2026!'})
                    uh = {'X-CSRF-Token': u.cookies.get('csrf_token')}
                    codes = {
                        '项目列表': u.get(BASE + '/projects/%d/risks' % pa,
                                     params={'page_size': 1}).status_code,
                        '项目统计': u.get(BASE + '/projects/%d/risks/stats' % pa).status_code,
                        '详情(编号)': u.get(BASE + '/risks/' + rn).status_code,
                        '详情(数字+company_id)': u.get(BASE + '/risks/1',
                                                  params={'company_id': a}).status_code,
                        '复核': u.post(BASE + '/risks/%s/review' % rn, headers=uh,
                                     json={'action': 'confirm', 'company_id': a}).status_code,
                        '批注': u.post(BASE + '/risks/%s/comment' % rn, headers=uh,
                                     json={'text': 'x', 'company_id': a}).status_code,
                        '整改台账': u.get(BASE + '/rectifications',
                                      params={'company_id': a}).status_code,
                        '规则发现': u.get(BASE + '/risk-findings',
                                     params={'company_id': a}).status_code,
                    }
                    print('跨租户状态码:', codes)
                    bad = {k: v for k, v in codes.items() if v == 200}
                    assert not bad, ('以下入口越权成功：%s' % bad)
                    # ★ 不得泄露存在性：详情类一律 404
                    assert codes['详情(编号)'] == 404, codes
                    # 自己的账套仍应可用（隔离不等于全体失效）
                    ok = u.get(BASE + '/rectifications',
                               params={'company_id': b}).status_code
                    assert ok == 200, ('授权账套应可访问', ok)
                print("P06 PERMISSION TESTS PASSED")
            """)
        _assert_ok(_run(script), "P06 PERMISSION TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class RiskAuditTests(unittest.TestCase):
    """审计：动作名/内容/操作人正确；与既有 finding.review 分离。"""

    def test_audit_content(self):
        script = _boot() + textwrap.dedent("""
            from engine.audit_trail import ACTION_CN, ACTIONS
            from security import SessionContext
            from engine import risk_review as R

            for a in ('risk.review', 'risk.comment', 'risk.rectify'):
                assert a in ACTIONS, a
                assert ACTION_CN.get(a), a
            # ★ 与既有 `finding.review`（引擎数据一致性复核）是**两个概念**
            assert 'finding.review' in ACTIONS
            assert ACTION_CN['finding.review'] != ACTION_CN['risk.review']

            sess = SessionContext(user_id=7, username='审计员', role='admin',
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash='', expires_at=0)
            rn = 'WB-R-91440300MA5H824G7M-202501-001'
            R.review(rn, 'confirm', sess, company_id=1, note='确认成立')
            R.comment(rn, '补充说明', sess, company_id=1)
            R.review(rn, 'rectify', sess, company_id=1, note='已整改完毕')
            # 被拒动作（无理由的 exclude）**不得留痕**
            try:
                R.review(rn, 'exclude', sess, company_id=1)
            except R.RiskReviewError:
                pass

            conn = sqlite3.connect(os.path.join(D, 'accounting.db'))
            rows = list(conn.execute(
                'select action, target, detail, user_name from audit_logs order by id'))
            assert len(rows) == 3, ('被拒动作不应留痕', rows)
            assert [x[0] for x in rows] == ['risk.review', 'risk.comment', 'risk.rectify'], rows
            assert all(x[1] == rn for x in rows), rows
            assert all('审计员' in str(x[3]) for x in rows), rows
            assert '已确认' in rows[0][2], rows[0]
            assert '整改台账' in rows[2][2] and 'WB-RC-' in rows[2][2], rows[2]
            print("P06 AUDIT TESTS PASSED")
            """)
        _assert_ok(_run(script), "P06 AUDIT TESTS PASSED")


# ══════════════════════════════════════════════════════════════════════════
class RiskReverseVerification(unittest.TestCase):
    """反向验证：停用状态迁移校验 ⇒ 非法迁移必须被放行（证明判据在判）。"""

    def test_broken_state_machine_lets_illegal_pass(self):
        target = ROOT / "engine" / "risk_review.py"
        backup = target.with_suffix(".py.rvtmp")
        shutil.copy(target, backup)
        broken = None
        try:
            text = target.read_text(encoding="utf-8")
            old = ("    if target is not None and target != now_state:\n"
                   "        allowed = STATE_FLOW.get(now_state, ())\n"
                   "        if target not in allowed:")
            new = ("    if target is not None and target != now_state:\n"
                   "        allowed = STATE_FLOW.get(now_state, ())\n"
                   "        if False and target not in allowed:  # 反向验证注入")
            assert old in text, "锚点未命中（状态迁移校验）"
            target.write_text(text.replace(old, new, 1), encoding="utf-8")

            script = _boot() + textwrap.dedent("""
                from security import SessionContext
                from engine import risk_review as R
                sess = SessionContext(user_id=1, username='t', role='admin',
                                      allowed_company_ids=frozenset({1}),
                                      selected_company_id=1, csrf_hash='', expires_at=0)
                rn = 'WB-R-91440300MA5H824G7M-202501-001'
                got = R.review(rn, 'rectify', sess, company_id=1, note='跳级')
                print('非法迁移结果:', got['state'])
                print("RV ILLEGAL PASSED")
                """)
            broken = _run(script)
            print("注入后 stdout:", broken.stdout[-300:])
        finally:
            shutil.copy(backup, target)
            os.remove(backup)

        self.assertFalse(backup.exists(), "残留 .rvtmp 未清理")
        self.assertIn("RV ILLEGAL PASSED", broken.stdout,
                      "★ 判据失效：停用迁移校验后非法迁移仍被拒 ⇒ 该断言是假的\n%s"
                      % broken.stdout[-1500:])

        # 还原后再跑：非法迁移必须被拒
        script2 = _boot() + textwrap.dedent("""
            from security import SessionContext
            from engine import risk_review as R
            sess = SessionContext(user_id=1, username='t', role='admin',
                                  allowed_company_ids=frozenset({1}),
                                  selected_company_id=1, csrf_hash='', expires_at=0)
            rn = 'WB-R-91440300MA5H824G7M-202501-001'
            try:
                R.review(rn, 'rectify', sess, company_id=1, note='跳级')
                raise AssertionError('还原后非法迁移仍被放行 ⇒ 判据无效')
            except R.RiskReviewError as exc:
                assert '非法迁移' in exc.message, exc.message
            print("RV RESTORED OK")
            """)
        _assert_ok(_run(script2), "RV RESTORED OK")


if __name__ == "__main__":
    unittest.main()
