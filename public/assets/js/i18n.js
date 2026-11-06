(() => {
  "use strict";

  const STORAGE_KEY = "hara-language";
  const locales = Object.freeze({ pt: "pt-BR", en: "en-US" });
  const catalog = window.HARA_I18N_CATALOG || { pt: {}, en: {} };
  const englishAvailable = Boolean(catalog.en && Object.keys(catalog.en).length);
  const root = document.documentElement;
  const attributes = ["title", "aria-label", "aria-description", "placeholder", "alt", "content"];
  const selector = ["[data-i18n]", ...attributes.map(name => `[data-i18n-${name}]`)].join(",");
  const originalLinks = new WeakMap();
  const siteHosts = new Set([location.hostname, "haralabs.com.br", "www.haralabs.com.br"]);
  const sitePaths = new Set(["/", "/404", "/404/", "/arquitetura/", "/commander/", "/contato/", "/empresa/", "/legal/", "/legal/privacidade/", "/legal/termos/", "/observabilidade/", "/privacy/", "/produtos/", "/seguranca/", "/solucoes/", "/support/", "/terms/"]);

  function normalize(value) {
    const candidate = String(value || "").trim().toLowerCase();
    const match = /^(pt|en)(?:-[a-z0-9]{2,8})?$/.exec(candidate);
    return match ? match[1] : null;
  }

  function initialLanguage() {
    let selected = null;
    try { selected = normalize(new URL(location.href).searchParams.get("lang")); }
    catch (_error) { /* The default still works without a URL context. */ }
    if (selected) {
      try { localStorage.setItem(STORAGE_KEY, selected); }
      catch (_error) { /* An explicit URL preference still works without storage. */ }
      return selected;
    }
    try { selected = normalize(localStorage.getItem(STORAGE_KEY)); }
    catch (_error) { /* Storage can be disabled or unavailable in private mode. */ }
    if (selected) return selected;
    const preferred = navigator.languages && navigator.languages.length
      ? navigator.languages : [navigator.language];
    for (const value of preferred) {
      selected = normalize(value);
      if (selected) return selected;
    }
    return "pt";
  }

  let language = englishAvailable ? initialLanguage() : "pt";

  function hasMessage(key) {
    return Object.prototype.hasOwnProperty.call(catalog[language] || {}, key)
      || Object.prototype.hasOwnProperty.call(catalog.pt || {}, key);
  }

  function t(key, values = {}) {
    const source = String(key == null ? "" : key);
    const messages = catalog[language] || {};
    const original = catalog.pt || {};
    const translated = Object.prototype.hasOwnProperty.call(messages, source)
      ? messages[source]
      : (Object.prototype.hasOwnProperty.call(original, source) ? original[source] : source);
    return String(translated).replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (match, name) => (
      Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : match
    ));
  }

  function apply(scope = document) {
    if (!scope || typeof scope.querySelectorAll !== "function") return;
    const nodes = [...scope.querySelectorAll(selector)];
    if (typeof scope.matches === "function" && scope.matches(selector)) nodes.unshift(scope);
    for (const node of nodes) {
      if (node.closest && node.closest("[data-i18n-ignore]")) continue;
      const key = node.getAttribute("data-i18n");
      if (key && hasMessage(key)) node.textContent = t(key);
      for (const attribute of attributes) {
        const attributeKey = node.getAttribute(`data-i18n-${attribute}`);
        if (attributeKey && hasMessage(attributeKey)) node.setAttribute(attribute, t(attributeKey));
      }
    }
    // Template contents are separate DOM fragments; sidebar copies retain the keys.
    for (const template of scope.querySelectorAll("template")) apply(template.content);
  }

  function syncSelector() {
    document.querySelectorAll("[data-set-language]").forEach(button => {
      button.setAttribute("aria-pressed", String(button.dataset.setLanguage === language));
      if (button.dataset.setLanguage === "en" && !englishAvailable) {
        button.disabled = true;
        button.title = "English is temporarily unavailable. Please reload the page.";
      }
    });
  }

  function syncNavigationLinks() {
    document.querySelectorAll("a[href]").forEach(link => {
      const original = originalLinks.get(link) || link.getAttribute("href");
      if (!original || original.startsWith("#")) return;
      try {
        const url = new URL(original, location.href);
        if (url.protocol !== "https:" && url.protocol !== "http:") return;
        const path = url.pathname.replace(/\/index\.html$/, "/");
        const sitePage = siteHosts.has(url.hostname) && sitePaths.has(path);
        const commanderHome = url.hostname === "commander.haralabs.com.br" && path === "/";
        if (!sitePage && !commanderHome) return;
        originalLinks.set(link, original);
        url.searchParams.set("lang", language);
        link.setAttribute("href", url.origin === location.origin
          ? url.pathname + url.search + url.hash : url.href);
      } catch (_error) { /* Preserve links that are not ordinary site navigation. */ }
    });
    const localeMeta = document.querySelector('meta[property="og:locale"]');
    if (localeMeta) localeMeta.content = language === "en" ? "en_US" : "pt_BR";
    const titleKey = root.getAttribute("data-i18n-page-title");
    if (titleKey && hasMessage(titleKey)) document.title = t(titleKey);
  }

  function persistLanguage() {
    try { localStorage.setItem(STORAGE_KEY, language); }
    catch (_error) { /* Switching remains available even if persistence is blocked. */ }
    try {
      const url = new URL(location.href);
      url.searchParams.set("lang", language);
      history.replaceState(history.state, "", url.pathname + url.search + url.hash);
    } catch (_error) { /* Do not navigate or interrupt a session to save a preference. */ }
  }

  function setLanguage(value, options = {}) {
    const next = normalize(value);
    if (!next) return false;
    if (next === "en" && !englishAvailable) return false;
    const changed = language !== next;
    language = next;
    root.lang = locales[language];
    root.dataset.language = language;
    if (options.persist !== false) persistLanguage();
    apply();
    syncSelector();
    syncNavigationLinks();
    if (changed) {
      // Consumers render their cached UI; changing language must not submit a form.
      window.dispatchEvent(new CustomEvent("hara:languagechange", {
        detail: { language, locale: locales[language] },
      }));
      const announcement = document.getElementById("languageAnnouncement");
      if (announcement) announcement.textContent = language === "en"
        ? "Language changed to English." : "Idioma alterado para português.";
    }
    return true;
  }

  root.lang = locales[language];
  root.dataset.language = language;
  window.HARA_I18N = Object.freeze({
    t,
    apply,
    setLanguage,
    getLanguage: () => language,
    getLocale: () => locales[language],
  });

  document.addEventListener("click", event => {
    const button = event.target.closest && event.target.closest("[data-set-language]");
    if (!button) return;
    event.preventDefault();
    setLanguage(button.dataset.setLanguage);
  });

  function initialize() {
    apply();
    syncSelector();
    syncNavigationLinks();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", initialize, { once: true });
  else initialize();
})();
