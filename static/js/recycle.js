/* 回收站页（H-04，2026-10-17）
 *
 * 后端能力一直存在（`move_to_trash`），但前端没有入口 ⇒ 用户删错了只能找 IT。
 * 本页只调 `/api/v1/system/trash*`，不自己实现移动/删除。
 */
(function () {
  'use strict';

  var API = '/api/v1/system/trash';

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
    var u = ['B', 'KB', 'MB', 'GB'], i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i += 1; }
    return (i === 0 ? n : n.toFixed(1)) + ' ' + u[i];
  }
  function fmtTime(ts) {
    if (!ts) { return '—'; }
    var d = new Date(ts * 1000);
    function p(x) { return (x < 10 ? '0' : '') + x; }
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate())
      + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  function say(kind, t) {
    document.getElementById('msg').innerHTML =
      t ? '<div class="msg ' + kind + '">' + esc(t) + '</div>' : '';
  }

  function render(d) {
    document.getElementById('kpis').innerHTML =
      '<div><b>' + (d.count || 0) + '</b>文件数</div>'
      + '<div><b>' + fmtBytes(d.total_bytes) + '</b>占用空间</div>'
      + '<div><b>' + esc(d.dir || '') + '</b>存放目录</div>';

    var items = d.items || [];
    if (!items.length) {
      document.getElementById('tb').innerHTML =
        '<tr><td colspan="5" class="muted">回收站是空的</td></tr>';
      return;
    }
    document.getElementById('tb').innerHTML = items.map(function (it) {
      return '<tr>'
        + '<td>' + esc(it.name) + '</td>'
        + '<td>' + fmtBytes(it.bytes) + '</td>'
        + '<td>' + fmtTime(it.mtime) + '</td>'
        + '<td><code>' + esc(it.restore_to) + '</code></td>'
        + '<td><button class="btn ghost" data-restore="' + esc(it.name) + '">还原</button></td>'
        + '</tr>';
    }).join('');
  }

  function load() {
    fetch(API, { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) {
        if (r.status === 403) { throw new Error('仅管理员可查看回收站'); }
        if (r.status === 401) { location.href = '/login'; throw new Error('未登录'); }
        if (!r.ok) { throw new Error('HTTP ' + r.status); }
        return r.json();
      })
      .then(render)
      .catch(function (e) {
        document.getElementById('kpis').innerHTML = '<div><b>—</b>取不到</div>';
        document.getElementById('tb').innerHTML = '<tr><td colspan="5" class="muted">—</td></tr>';
        say('err', '读取回收站失败：' + e.message);
      });
  }

  function restore(name) {
    fetch(API + '/restore', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
      body: JSON.stringify({ name: name })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) { throw new Error(res.j.detail || 'HTTP'); }
        say('ok', '已还原「' + res.j.name + '」→ ' + res.j.restored_to + '。' + (res.j.note || ''));
        load();
      })
      .catch(function (e) { say('err', '还原失败：' + e.message); });
  }

  function emptyBatch() {
    if (!window.confirm('清空回收站中的一批文件（最多 20 个），此操作不可撤销。继续？')) { return; }
    var btn = document.getElementById('btn-empty');
    btn.disabled = true;
    fetch(API + '/empty', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf() },
      body: JSON.stringify({ confirm: true, max_files: 20 })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok) { throw new Error(res.j.detail || 'HTTP'); }
        say('ok', '已清理 ' + res.j.removed + ' 个，剩余 ' + res.j.left + ' 个。' + (res.j.note || ''));
        load();
      })
      .catch(function (e) { say('err', '清空失败：' + e.message); })
      .finally(function () { btn.disabled = false; });
  }

  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.getAttribute) { return; }
    if (t.id === 'btn-refresh') { load(); return; }
    if (t.id === 'btn-empty') { emptyBatch(); return; }
    var name = t.getAttribute('data-restore');
    if (name) { restore(name); }
  });

  document.addEventListener('DOMContentLoaded', load);
})();
