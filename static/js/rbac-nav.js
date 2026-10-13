/* 权限前端门控（P0-8）—— 菜单 / 按钮 / 数据可见性的**唯一**前端判据。
 *
 * 口径：**权限由后端给出**（`GET /api/auth/me` 的 `permissions` 数组，其唯一权威是
 * `engine/rbac.rbac_allows()`）。本脚本**不推断角色**，只消费服务端下发的权限集合；
 * 前端隐藏按钮只是**体验**，真正的拦截在服务端（`require_permission`）——
 * 任何"前端藏了就等于安全"的想法都是错的。
 *
 * 用法：
 *   <script src="/static/js/rbac-nav.js?v=HASH"></script>
 *   <div class="nav-item" data-perm="user.view">用户管理</div>      // 无权限 ⇒ 隐藏
 *   <button data-perm="user.manage">新建用户</button>               // 无权限 ⇒ 隐藏
 *   <button data-perm-btn="user.manage">停用</button>               // 无权限 ⇒ 禁用
 *   window.RBAC.has('audit.view')   // 主动判断（返回 false 时 me 未就绪也安全）
 *   window.RBAC.ready(fn)           // me 取回后回调
 */
(function () {
  "use strict";

  var state = { loaded: false, permissions: [], roles: [], username: "", tenantId: null };
  var waiters = [];

  function apply() {
    var nodes = document.querySelectorAll("[data-perm]");
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var need = String(node.getAttribute("data-perm") || "").trim();
      if (!need) continue;
      if (!has(need)) node.style.display = "none";
    }
    var btns = document.querySelectorAll("[data-perm-btn]");
    for (var j = 0; j < btns.length; j++) {
      var b = btns[j];
      if (!has(String(b.getAttribute("data-perm-btn") || "").trim())) {
        b.disabled = true;
        b.title = "当前角色无此权限";
        b.style.opacity = ".5";
        b.style.cursor = "not-allowed";
      }
    }
  }

  function has(perm) {
    return state.permissions.indexOf(String(perm || "")) >= 0;
  }

  function ready(fn) {
    if (state.loaded) { try { fn(state); } catch (e) { /* 回调异常不阻断 */ } return; }
    waiters.push(fn);
  }

  function flush() {
    var list = waiters.slice();
    waiters.length = 0;
    for (var i = 0; i < list.length; i++) {
      try { list[i](state); } catch (e) { /* 单个回调异常不得影响其他 */ }
    }
  }

  function load() {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data && data.ok !== false) {
          state.permissions = data.permissions || [];
          state.roles = data.roles || [];
          state.username = data.username || "";
          state.tenantId = (data.tenant_id === undefined ? null : data.tenant_id);
        }
        state.loaded = true;
        apply();
        flush();
      })
      .catch(function () {
        /* 取不到 ⇒ 权限视为空（**更严**，绝不默认放行） */
        state.loaded = true;
        apply();
        flush();
      });
  }

  window.RBAC = { state: state, has: has, ready: ready, refresh: load };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
