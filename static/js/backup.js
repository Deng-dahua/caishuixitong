/* 备份与恢复页（S-10 / D-02，2026-10-17）
 *
 * 只调 `/api/v1/system/backups*`（唯一实现 engine/backup.py）。
 * 恢复是**停服后**的命令行动作 —— 这里给命令，不给假按钮（运行中恢复会损坏库）。
 */
(function () {
  'use strict';

  var API = '/api/v1/system';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }
  function fmtBytes(n) {
    n = Number(n || 0);
    var u = ['B', 'KB', 'MB', 'GB'];
    var i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i += 1; }
    return (i === 0 ? n : n.toFixed(1)) + ' ' + u[i];
  }
  function say(kind, text) {
    var box = document.getElementById('msg');
    box.innerHTML = text ? '<div class="msg ' + kind + '">' + esc(text) + '</div>' : '';
  }
  function el(id) { return document.getElementById(id); }

  function render(d) {
    var s = d.summary || {};
    var latest = s.latest || null;
    var parts = [
      ['备份份数', s.count == null ? '—' : s.count],
      ['最近一份', s.age_hours == null ? '从未备份' : (s.age_hours.toFixed(1) + ' 小时前')],
      ['占用空间', fmtBytes(s.total_bytes)],
      ['自动间隔', (s.interval_hours || 0) + ' 小时'],
      ['保留份数', s.keep == null ? '—' : s.keep],
      ['当前状态', s.due ? '需要备份' : '已是最新']
    ];
    el('kpis').innerHTML = parts.map(function (p) {
      return '<div><b>' + esc(p[1]) + '</b>' + esc(p[0]) + '</div>';
    }).join('');
    el('hint').textContent = latest ? ('备份目录：' + (s.dir || '')) : '还没有任何备份';
    if (s.due) {
      el('msg').innerHTML = '<div class="msg warn">当前<b>没有可用备份</b>或已超过间隔，'
        + '建议立即备份一份（服务启动时也会自动补一次）。</div>';
    }

    var howto = d.restore_howto || [];
    el('howto').innerHTML = howto.map(function (x) {
      return '<li>' + x.replace(/`([^`]+)`/g, '<code>$1</code>') + '</li>';
    }).join('');

    var items = d.items || [];
    if (!items.length) {
      el('tb').innerHTML = '<tr><td colspan="5" class="muted">还没有备份</td></tr>';
      return;
    }
    el('tb').innerHTML = items.map(function (m) {
      var kind = m.kind || 'unknown';
      var cls = kind === 'daily' ? 'daily' : (kind === 'pre-restore' ? 'pre' : 'manual');
      return '<tr>'
        + '<td><code>' + esc(m.folder) + '</code>'
        + (m.damaged ? ' <span class="tag" style="background:#fee2e2;color:#b91c1c">不完整</span>' : '')
        + '</td>'
        + '<td><span class="tag ' + cls + '">' + esc(kind) + '</span></td>'
        + '<td>' + esc(m.created_at || '—') + '</td>'
        + '<td>' + fmtBytes(m.bytes) + '</td>'
        + '<td>'
        + '<button class="btn ghost" data-verify="' + esc(m.folder) + '">校验</button> '
        + '<button class="btn ghost" data-restore="' + esc(m.folder) + '">恢复…</button>'
        + '</td></tr>';
    }).join('');
  }

  function load() {
    fetch(API + '/backups', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) {
        if (r.status === 403) { throw new Error('仅管理员可查看备份（当前账号无权限）'); }
        if (!r.ok) { throw new Error('HTTP ' + r.status); }
        return r.json();
      })
      .then(render)
      .catch(function (e) {
        el('kpis').innerHTML = '<div><b>—</b>取不到</div>';
        el('tb').innerHTML = '<tr><td colspan="5" class="muted">—</td></tr>';
        say('err', '读取备份状态失败：' + e.message);
      });
  }

  function create() {
    var btn = el('btn-create');
    btn.disabled = true;
    btn.textContent = '备份中…';
    fetch(API + '/backups', { method: 'POST', credentials: 'same-origin',
      headers: { 'X-CSRF-Token': csrf() } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) { throw new Error(res.j.detail || 'HTTP'); }
        say('ok', '已生成备份 ' + res.j.folder + '（' + res.j.files.length + ' 个文件，'
          + fmtBytes(res.j.bytes) + '；完整性 '
          + JSON.stringify(res.j.integrity || {}) + '）');
        load();
      })
      .catch(function (e) { say('err', '备份失败：' + e.message); })
      .finally(function () { btn.disabled = false; btn.textContent = '立即备份一份'; });
  }

  function verify(folder) {
    say('', '');
    fetch(API + '/backups/' + encodeURIComponent(folder) + '/verify',
      { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf() } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (res.j.ok) {
          say('ok', folder + '：校验通过（SHA-256 与完整性检查均 OK）');
        } else {
          say('err', folder + '：校验未通过 —— ' + (res.j.problems || [res.j.detail]).join('；'));
        }
      })
      .catch(function (e) { say('err', '校验失败：' + e.message); });
  }

  function restore(folder) {
    fetch(API + '/backups/' + encodeURIComponent(folder) + '/restore',
      { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': csrf() } })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        var j = res.j || {};
        if (j.detail) { say('err', j.detail); return; }
        if (j.need_restart) {
          el('msg').innerHTML = '<div class="msg warn"><b>' + esc(j.reason)
            + '</b><br>请执行：<code>' + esc(j.command) + '</code></div>';
          var ol = el('howto');
          ol.innerHTML = (j.howto || []).map(function (x) {
            return '<li>' + x.replace(/`([^`]+)`/g, '<code>$1</code>') + '</li>';
          }).join('');
        }
      })
      .catch(function (e) { say('err', '恢复请求失败：' + e.message); });
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.getAttribute) { return; }
    if (t.id === 'btn-create') { create(); return; }
    if (t.id === 'btn-refresh') { load(); return; }
    var v = t.getAttribute('data-verify');
    if (v) { verify(v); return; }
    var r = t.getAttribute('data-restore');
    if (r) { restore(r); }
  });

  document.addEventListener('DOMContentLoaded', load);
})();
