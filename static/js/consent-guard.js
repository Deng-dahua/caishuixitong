/* 知情同意引导（E-01，2026-10-17）
 *
 * 只做一件事：进首页时问一次 `/api/auth/me`，若 `consent_required` 为真，
 * 跳到 `/consent` 让用户看到《数据处理告知与免责声明》。
 *
 * ★ 四条纪律
 *   ① **不阻断业务**：跳转只发生一次（sessionStorage 记标记），用户不接受也能继续用；
 *   ② 不推断角色、不读 localStorage 里的身份（服务端 `consent_required` 是唯一依据）；
 *   ③ 接口失败**静默放过**（告知不该把系统变成不可用）；
 *   ④ 只在首页加载，不在每个内页重复请求。
 */
(function () {
  'use strict';

  var KEY = 'consentPrompted';

  function alreadyPrompted() {
    try { return sessionStorage.getItem(KEY) === '1'; } catch (e) { return false; }
  }
  function mark() {
    try { sessionStorage.setItem(KEY, '1'); } catch (e) { /* 忽略 */ }
  }

  function check() {
    if (location.pathname !== '/' && location.pathname !== '/index.html') { return; }
    if (alreadyPrompted()) { return; }
    fetch('/api/auth/me', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (!d || !d.ok) { return; }
        if (d.consent_required) {
          mark();
          location.href = '/consent';
        }
      })
      .catch(function () { /* 静默：告知不能变成可用性故障 */ });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', check);
  } else {
    check();
  }
})();
