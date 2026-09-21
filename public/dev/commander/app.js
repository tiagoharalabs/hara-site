(() => {
  const views = [...document.querySelectorAll("[data-view]")];
  const toast = document.getElementById("toast");
  const sidebarTemplate = document.getElementById("sidebarTemplate");
  const appViews = new Set(["dashboard", "usage", "plans", "connections", "security"]);
  const publicViews = new Set(["landing", "login", "signup", ...appViews]);
  const localHost = location.hostname === "127.0.0.1" || location.hostname === "localhost";
  const apiBase = localHost ? "http://127.0.0.1:9192" : null;

  function number(value) {
    return new Intl.NumberFormat("pt-BR").format(Number(value || 0));
  }

  function applyDashboard(payload) {
    if (!payload?.entitlement || !payload?.usage) return;
    const plan = payload.entitlement.plan_name || payload.entitlement.plan_code || "—";
    const consumed = Number(payload.usage.consumed_units || 0);
    const limit = payload.usage.limit == null ? null : Number(payload.usage.limit);
    const remaining = payload.usage.remaining_units;
    const percent = limit ? Math.min(100, (consumed / limit) * 100) : 0;

    const set = (id, value) => {
      const node = document.getElementById(id);
      if (node) node.textContent = value;
    };

    set("landingPlan", plan);
    set("landingUsage", number(consumed));
    set("landingLimit", limit == null ? "sem limite" : "de " + number(limit));
    set("dashboardPlan", plan);
    set("dashboardConsumed", number(consumed));
    set("dashboardLimit", limit == null ? "/ sem limite" : "/ " + number(limit));
    set("dashboardPercent", limit == null ? "Plano sem limite definido" : percent.toFixed(2).replace(".", ",") + "% utilizado");
    set("dashboardInvokes", number(consumed));
    set("usageConsumed", number(consumed));
    set("usageLimit", limit == null ? "sem limite" : "de " + number(limit));
    set("usageRemaining", remaining == null ? "Capacidade sem limite definido" : number(remaining) + " unidades disponíveis");
    set("usagePeriod", payload.usage.period_key || "—");

    const bar = document.getElementById("usageProgress");
    if (bar) bar.style.width = (limit == null ? 0 : percent) + "%";
  }

  async function loadProductDashboard() {
    if (!apiBase) return;
    try {
      const response = await fetch(apiBase + "/api/dev/dashboard", { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP_" + response.status);
      applyDashboard(await response.json());
    } catch (_error) {
      showToast("Backend DEV do Commander indisponível; mantendo valores de fallback.");
    }
  }

  function copySidebars() {
    document.querySelectorAll("[data-sidebar]").forEach((node) => {
      node.innerHTML = sidebarTemplate.innerHTML;
    });
  }

  function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    clearTimeout(showToast.timer);
    showToast.timer = setTimeout(() => toast.classList.remove("show"), 3200);
  }

  function route(target, push = true) {
    const next = publicViews.has(target) ? target : "landing";
    views.forEach((view) => view.classList.toggle("active", view.dataset.view === next));

    document.querySelectorAll("[data-app-go]").forEach((button) => {
      button.classList.toggle("active", button.dataset.appGo === next);
    });
    document.querySelectorAll("[data-nav]").forEach((link) => {
      link.classList.toggle("active", link.dataset.nav === next);
    });

    document.body.classList.toggle("workspace-mode", appViews.has(next));
    if (push && location.hash !== "#" + next) history.pushState(null, "", "#" + next);
    window.scrollTo({ top: 0, behavior: "instant" });
    if (next === "landing" || next === "dashboard" || next === "usage") {
      loadProductDashboard();
    }
  }

  copySidebars();

  document.addEventListener("click", (event) => {
    const go = event.target.closest("[data-go]");
    if (go) {
      event.preventDefault();
      route(go.dataset.go);
      return;
    }

    const appGo = event.target.closest("[data-app-go]");
    if (appGo) {
      event.preventDefault();
      route(appGo.dataset.appGo);
      return;
    }

    const demo = event.target.closest("[data-demo-toast]");
    if (demo) {
      event.preventDefault();
      showToast(demo.dataset.demoToast);
    }
  });

  document.querySelectorAll("[data-auth-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const label = form.dataset.authForm === "signup"
        ? "Workspace DEV criado localmente. Nenhuma credencial foi persistida."
        : "Login DEV simulado. Nenhuma credencial foi enviada.";
      showToast(label);
      route("dashboard");
      form.reset();
    });
  });

  window.addEventListener("popstate", () => route(location.hash.slice(1) || "landing", false));
  window.addEventListener("hashchange", () => route(location.hash.slice(1) || "landing", false));

  route(location.hash.slice(1) || "landing", false);
  loadProductDashboard();
})();
