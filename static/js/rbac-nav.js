/* 权限前端门控（P0-8）—— 菜单 / 按钮 / 数据可见性的**唯一**前端判据。
 *
 * 口径：**权限由后端给出**（`GET /api/auth/me` 的 `permissions` / `is_admin`，其唯一权威是
 * `engine/rbac.rbac_allows()` 与 `session.is_admin`）。本脚本**不推断角色**，只消费服务端
 * 下发的权限集合 —— 任何"前端藏了就等于安全"的想法都是错的，真正的拦截在服务端。
 *
 * 用法：
 *   <script src="/static/js/rbac-nav.js?v=HASH"></script>
 *   <div class="nav-item" data-perm="user.view">用户管理</div>        // 无权限 ⇒ 隐藏
 *   <button data-perm="user.manage">新建用户</button>                 // 无权限 ⇒ 隐藏
 *   <button data-perm-btn="user.manage">停用</button>                 // 无权限 ⇒ 禁用
 *   <div data-perm-admin>新建账套</div>                               // 非管理员 ⇒ 隐藏
 *   window.RBAC.has('audit.view')   // 主动判断（返回 false 时 me 未就绪也安全）
 *   window.RBAC.isAdmin()           // 是否管理员（服务端下发，不推断）
 *   window.RBAC.ready(fn)           // me 取回后回调
 *   window.RBAC.reapply()           // 动态渲染了新节点后，重新套用一次
 *
 * `data-perm-admin` 为什么必要：服务端有若干**仅管理员**端点（`security_web._LEGACY_ADMIN_ONLY`，
 * 如新建/删除账套、全局巡检配置），它们**不对应任何权限点**，故无法用 `data-perm="<权限码>"`
 * 表达。管理员标识由 `/api/auth/me` 的 `is_admin` 下发（服务端是唯一权威）。
 *
 * ★ 2026-10-17（O8）**失败重试 + 自愈**：此前 `/api/auth/me` 一旦非 200，权限即按空处理并
 *   **永久隐藏**（无重试），表现为"管理员也看不到按钮"。现改为：失败仍**从严隐藏**（fail-closed），
 *   但会**退避重试**；一旦成功，`apply()` 会**恢复**本应可见的元素（含此前被误隐藏的）。
 */
(function () {
  "use strict";

  var ORIG_DISPLAY = "data-rbac-orig-display";
  var ORIG_DISABLED = "data-rbac-orig-disabled";

  //: 失败重试的退避毫秒（首项对应第 1 次失败后）。总计 4 次尝试。
  var BACKOFF_MS = [400, 1200, 3000];

  var state = { loaded: false, permissions: [], roles: [], isAdmin: false,
                username: "", tenantId: null, attempts: 0 };
  var waiters = [];

  function has(perm) {
    return state.permissions.indexOf(String(perm || "")) >= 0;
  }

  function isAdmin() {
    return !!state.isAdmin;
  }

  /** 记录原值后隐藏（幂等：不覆盖已记录的原值）。 */
  function hide(node) {
    if (node.getAttribute(ORIG_DISPLAY) === null) {
      node.setAttribute(ORIG_DISPLAY, node.style.display || "");
    }
    node.style.display = "none";
  }

  /** 恢复可见性（仅当此前被本脚本隐藏过；否则不动用户自己的行内样式）。 */
  function restore(node) {
    var orig = node.getAttribute(ORIG_DISPLAY);
    if (orig === null) return;
    node.style.display = orig;
    node.removeAttribute(ORIG_DISPLAY);
  }

  function disable(node, why) {
    if (node.getAttribute(ORIG_DISABLED) === null) {
      node.setAttribute(ORIG_DISABLED, node.disabled ? "1" : "0");
    }
    node.disabled = true;
    node.title = why;
    node.style.opacity = ".5";
    node.style.cursor = "not-allowed";
  }

  function restoreBtn(node) {
    var orig = node.getAttribute(ORIG_DISABLED);
    if (orig === null) return;
    node.disabled = (orig === "1");
    node.style.opacity = "";
    node.style.cursor = "";
    node.removeAttribute(ORIG_DISABLED);
  }

  /** 把当前权限态套用到 DOM（**可重复调用**：既可隐藏，也可恢复）。 */
  function apply() {
    var nodes = document.querySelectorAll("[data-perm],[data-perm-admin]");
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      var adminOnly = node.hasAttribute("data-perm-admin");
      var need = String(node.getAttribute("data-perm") || "").trim();
      var allowed;
      if (adminOnly) {
        allowed = isAdmin();
      } else if (need) {
        allowed = has(need);
      } else {
        continue;
      }
      if (allowed) { restore(node); } else { hide(node); }
    }
    var btns = document.querySelectorAll("[data-perm-btn]");
    for (var j = 0; j < btns.length; j++) {
      var b = btns[j];
      var need2 = String(b.getAttribute("data-perm-btn") || "").trim();
      if (!need2) continue;
      if (has(need2)) { restoreBtn(b); }
      else { disable(b, "当前角色无此权限"); }
    }
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

  function _absorb(data) {
    if (data && data.ok !== false) {
      state.permissions = data.permissions || [];
      state.roles = data.roles || [];
      state.isAdmin = !!data.is_admin;
      state.username = data.username || "";
      state.tenantId = (data.tenant_id === undefined ? null : data.tenant_id);
    }
  }

  function _settle() {
    state.loaded = true;
    apply();
    flush();
  }

  function load() {
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (data) {
          _absorb(data);
          state.attempts = 0;
          _settle();
          return;
        }
        _onFailure();          // 非 2xx：按失败处理（可能只是瞬时故障）
      })
      .catch(function () {
        /* 网络异常 / 解析失败：同上 */
        _onFailure();
      });
  }

  function _onFailure() {
    // ★ fail-closed：取不到就**按无权限**处理（宁严勿松，绝不默认放行）
    state.permissions = [];
    state.roles = [];
    state.isAdmin = false;
    apply();
    if (state.attempts < BACKOFF_MS.length) {
      var delay = BACKOFF_MS[state.attempts];
      state.attempts += 1;
      setTimeout(load, delay);
      return;
    }
    // 重试用尽：落到"空权限"终态，并放行 ready 回调（避免调用方永久等待）
    _settle();
  }

  window.RBAC = {
    state: state, has: has, isAdmin: isAdmin, ready: ready, refresh: load, reapply: apply,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
