(function () {
  "use strict";
  if (window.__secureFetchInstalled) return;
  window.__secureFetchInstalled = true;

  function cookie(name) {
    var prefix = name + "=";
    var item = document.cookie.split("; ").find(function (value) {
      return value.startsWith(prefix);
    });
    return item ? decodeURIComponent(item.slice(prefix.length)) : "";
  }

  var originalFetch = window.fetch.bind(window);
  window.fetch = function (resource, init) {
    var options = init ? Object.assign({}, init) : {};
    var method = String(options.method || "GET").toUpperCase();
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      var headers = new Headers(options.headers || {});
      var csrf = cookie("csrf_token");
      if (csrf) headers.set("X-CSRF-Token", csrf);
      options.headers = headers;
    }
    return originalFetch(resource, options).then(function (response) {
      if (response.status === 401 && location.pathname !== "/login") {
        location.assign("/login");
      }
      return response;
    });
  };
})();
