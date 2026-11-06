(() => {
  "use strict";
  const path = document.currentScript?.dataset.redirectTo;
  if (path !== "/legal/privacidade/" && path !== "/legal/termos/") return;
  const current = new URL(location.href);
  const explicit = /^(pt|en)(?:-[a-z0-9]{2,8})?$/i.exec(current.searchParams.get("lang") || "");
  const language = explicit ? explicit[1].toLowerCase() : (window.HARA_I18N?.getLanguage() || "pt");
  const target = new URL(path, location.origin);
  target.search = current.search;
  target.searchParams.set("lang", language);
  target.hash = current.hash;
  location.replace(target.pathname + target.search + target.hash);
})();
