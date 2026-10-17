/**
 * 阶段 3 UX 探针 —— 用户视角 8 维度的**可回读证据采集**（2026-10-17）。
 *
 * 设计原则：
 *   · **只采集客观量**（元素数、文案长度、耗时、状态码），评分由人在报告里给并写理由；
 *   · 每项指标都能回读（写进 `_ux/UX_EVIDENCE.json`），不接受"看代码觉得应该行"；
 *   · 每页 try/catch，单页异常不中断整轮（并记录异常＝问题线索，而非脚本失败）。
 *
 * 8 维度 ↔ 指标映射：
 *   1 可发现性：侧栏入口可见 / 页内主流程入口数
 *   2 可理解性：说明性文案字数（h3 hint / .muted / .hint）、标题是否与入口名对应
 *   3 可操作性：可交互控件数、被禁用控件数、必填标记数
 *   4 可反馈性：反馈载体（#msg/#alert/status 类）数量、加载态文案、空态文案
 *   5 可恢复性：取消/关闭/重置/回滚/回收站 类入口数
 *   6 可学习性：placeholder 数、title 提示数、示例/帮助入口数
 *   7 效率：首屏可交互耗时(ms)、页面主流程控件集中度
 *   8 满意度：页面体积(KB)、控制台错误数、中文错误提示可得性
 */
const fs = require('fs');
const path = require('path');
const L = require(path.join(__dirname, 'metaq2_sim', 'lib.js'));
const { chromium } = require('playwright');

const ROOT = path.join(__dirname, '..');
const OUT_DIR = path.join(ROOT, 'docs', '元质量_20261016', '_ux');

/** 19 个模块（与侧边栏可见项一一对应） */
const MODULES = [
  { key: 'home', name: '首页/总览', route: '/' },
  { key: 'projects', name: '稽查项目', route: '/projects' },
  { key: 'documents', name: '资料上传与管理', route: '/documents' },
  { key: 'extract', name: '资料解析与校正', route: '/extract' },
  { key: 'analysis', name: '一键稽查分析任务', route: '/analysis' },
  { key: 'rules', name: '规则库与风险发现', route: '/rules' },
  { key: 'risks', name: '风险结果与复核', route: '/risks' },
  { key: 'reports', name: '报告生成与导出', route: '/reports' },
  { key: 'templates', name: '报告模板', route: '/report-templates' },
  { key: 'rule_versions', name: '规则版本', route: '/rule-versions' },
  { key: 'legal_library', name: '法规库', route: '/legal-library' },
  { key: 'legal_topics', name: '法规专题', route: '/legal-topics' },
  { key: 'legal_materials', name: '案例·解读·问答', route: '/legal-materials' },
  { key: 'industry', name: '行业指标库', route: '/industry-indicators' },
  { key: 'dashboard', name: '数据大屏', route: '/dashboard' },
  { key: 'users', name: '用户管理', route: '/users' },
  { key: 'roles', name: '角色管理', route: '/roles' },
  { key: 'audit_logs', name: '审计日志', route: '/audit-logs' },
  { key: 'ai_assist', name: 'AI 辅助', route: '/ai-assist' },
];

const PROBE = () => {
  const q = (s) => Array.from(document.querySelectorAll(s));
  const vis = (el) => !!el && el.offsetParent !== null;
  const txt = (s) => {
    const el = document.querySelector(s);
    return el ? (el.innerText || '').trim() : '';
  };
  const body = document.body ? (document.body.innerText || '') : '';

  // 可交互控件（真实可点的）
  // ★ 含 div[onclick]：本项目大量入口是 <div class="nav-item" onclick=...>（只算 button/a 会低估）
  const controls = q('button, a[href], input:not([type=hidden]), select, textarea, [onclick]').filter(vis);
  const disabled = controls.filter((el) => el.disabled === true);
  const required = q('[required], .req, [data-required]').length;

  // 说明性文案：h3 内 hint / .hint / .muted / .note-box / small
  // ★ 2026-10-17 口径修正：原选择器只认 `.hint/.muted/.note-box/small`，
  //   于是首页「口径说明」区块（用 .kpi-sub 排版正文）被算成"0 字"——
  //   这是**探针漏项**，不是页面没说明（实测该区块有 200+ 字）。
  //   现补上 `.kpi-sub`、`.section-card-body`，并把纯数字标签排除（只统计解释性文字）。
  const hints = q('h3 .hint, .hint, .muted, .note-box, small, .kpi-sub, .section-card-body')
    .filter(vis)
    .filter((el) => !/^[\s\d.%—\-]*$/.test((el.innerText || '').trim()));
  const hintChars = hints.reduce((n, el) => n + ((el.innerText || '').trim().length), 0);

  // 反馈载体
  const feedback = ['#msg', '#alert', '#flash', '#gen-status', '.msg', '[id*=status]', '[id*=tip]']
    .reduce((n, s) => n + q(s).filter(vis).length, 0);
  const loadingText = /加载中|正在|请稍候|处理中/.test(body);
  // ★ 2026-10-17 新增：**数据来源/口径标注**数（"来源：…"、"口径"字样）。
  //   展示型页面（首页/大屏）不承载操作，其"可反馈性"体现在用户能否知道
  //   "这个数字从哪来、算的是什么"——仅统计有写操作的页面会系统性低估它们。
  const sourceNotes = (body.match(/来源：|口径|取自/g) || []).length;

  // 恢复性入口
  const RECOVER = /取消|关闭|重置|回滚|回收站|撤销|还原|恢复|重试|返回/;
  const recover = controls.filter((el) => RECOVER.test((el.innerText || '').trim())).length;

  // 学习性
  const placeholders = q('[placeholder]').filter(vis).length;
  const titles = q('[title]').filter(vis).length;
  const helps = controls.filter((el) => /示例|帮助|说明|指引|教程|演示/.test((el.innerText || '').trim())).length;

  // 标题
  const h1 = txt('h1');
  const titleTags = q('h2, h3').filter(vis).map((el) => (el.innerText || '').trim().slice(0, 24));

  // 空态
  const empty = txt('.empty');

  const navItems = q('.nav-item').filter(vis);
  const navVisible = navItems.length;
  const navTotal = q('.nav-item').length;
  // 顶栏可导航入口（非首页页面的"横向可达性"）
  const topLinks = q('.topbar a, .topbar button, header a, header button').filter(vis).length;

  return {
    url: location.pathname,
    h1,
    controls: controls.length,
    disabled: disabled.length,
    required,
    hintBlocks: hints.length,
    hintChars,
    feedback,
    sourceNotes,
    loadingText,
    recover,
    placeholders,
    titles,
    helps,
    titleTags: titleTags.slice(0, 6),
    empty: empty.slice(0, 60),
    navVisible,
    navTotal,
    topLinks,
    bodyChars: body.length,
    bodyKB: Math.round(body.length / 1024 * 10) / 10,
  };
};

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const out = { generated_at: new Date().toISOString(), base: L.BASE, modules: [] };

  for (const m of MODULES) {
    const rec = { key: m.key, name: m.name, route: m.route };
    const { page, ctx } = await L.newPage(browser, null);
    const consoleErrors = [];
    page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 120)); });
    page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e.message).slice(0, 120)));
    try {
      await L.login(page, 'sim_admin', L.PW, null);
      const t0 = Date.now();
      const resp = await page.goto(L.BASE + m.route, { waitUntil: 'domcontentloaded', timeout: 30000 });
      rec.httpStatus = resp ? resp.status() : null;
      rec.loadMs = Date.now() - t0;
      // ★ 2026-10-17 修正采样纪律：原先固定等 2600ms —— 用户管理页要 3s+ 才加载完，
      //   于是采样时抓到的是「加载中…」（bodyChars=109、0 条数据），
      //   把「说明字数」判成 0、把「满意度」误判为 3（假数据）。
      //   现改为**等真实渲染信号**：`.empty` 不再是"加载中"，且已有表格行/卡片。
      // ★ 采样纪律（2026-10-17 三次返工后的定稿）：
      //   ① 等**网络空闲**（页面自身的数据请求全部落地）—— 比"猜毫秒"可靠；
      //   ② 再等一个固定缓冲（图表/表格收尾渲染）；
      //   ③ 连续两次采样**稳定**才采纳（避免渲染中途采到半成品）；
      //   ④ 把两次的控件数都记下来，若差异大就标记 `unstable=true`（报告里如实说明）。
      await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(2000);
      let m1 = await page.evaluate(PROBE);
      await page.waitForTimeout(1200);
      let m2 = await page.evaluate(PROBE);
      // 取"控件更多"的那次（渲染更完整），并记录稳定性
      rec.metrics = (m2.controls >= m1.controls) ? m2 : m1;
      rec.unstable = Math.abs(m2.controls - m1.controls) > 3;
      rec.stillLoading = /加载中|正在|请稍候/.test((rec.metrics.empty || ''));
      rec.consoleErrors = consoleErrors.slice(0, 5);
      rec.ok = true;
    } catch (e) {
      rec.ok = false;
      rec.error = String(e.message).slice(0, 200);
      rec.consoleErrors = consoleErrors.slice(0, 5);
    } finally {
      await ctx.close();
    }
    console.log(`[${rec.ok ? 'OK ' : 'ERR'}] ${m.name.padEnd(18)} `
      + `控件=${rec.metrics ? rec.metrics.controls : '-'} 说明字数=${rec.metrics ? rec.metrics.hintChars : '-'} `
      + `反馈=${rec.metrics ? rec.metrics.feedback : '-'} 恢复=${rec.metrics ? rec.metrics.recover : '-'} `
      + `占位=${rec.metrics ? rec.metrics.placeholders : '-'} 耗时=${rec.loadMs}ms `
      + `体积=${rec.metrics ? rec.metrics.bodyKB + 'KB' : '-'} 控制台错误=${rec.consoleErrors.length}`);
    out.modules.push(rec);
  }

  // 侧栏清单（只有首页有 .nav-item）—— 可发现性的唯一口径
  {
    const { page, ctx } = await L.newPage(browser, null);
    await L.login(page, 'sim_admin', L.PW, null);
    await page.goto(L.BASE + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2600);
    out.sidebar = await page.evaluate(() => {
      const all = Array.from(document.querySelectorAll('.nav-item'));
      const vis = all.filter((e) => e.offsetParent !== null);
      return {
        total: all.length,
        visible: vis.length,
        items: vis.map((e) => (e.innerText || '').trim().replace(/\s+/g, '')),
        hidden: all.filter((e) => e.offsetParent === null)
          .map((e) => (e.innerText || '').trim().replace(/\s+/g, '')),
      };
    });
    console.log(`\n侧栏：DOM ${out.sidebar.total} 项 / 可见 ${out.sidebar.visible} 项`
      + (out.sidebar.hidden.length ? ` / 隐藏=${out.sidebar.hidden.join(',')}` : ''));
    await ctx.close();
  }

  const file = path.join(OUT_DIR, 'UX_EVIDENCE.json');
  fs.writeFileSync(file, JSON.stringify(out, null, 2), 'utf-8');
  console.log('\n证据已写入', file);
  const bad = out.modules.filter((x) => !x.ok).length;
  console.log(bad === 0 ? '✅ 19 个模块全部采集成功' : `⚠ ${bad} 个模块采集异常（见 JSON）`);
  await browser.close();
  process.exit(bad === 0 ? 0 : 1);
})().catch((e) => { console.error('ERR', e.message); process.exit(3); });
