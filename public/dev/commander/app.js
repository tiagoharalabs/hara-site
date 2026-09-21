(() => {
  const views = [...document.querySelectorAll("[data-view]")];
  const toast = document.getElementById("toast");
  const sidebarTemplate = document.getElementById("sidebarTemplate");
  const banner = document.getElementById("systemBanner");
  const bannerTitle = document.getElementById("systemBannerTitle");
  const bannerMessage = document.getElementById("systemBannerMessage");
  const bannerAction = document.getElementById("systemBannerAction");
  const appViews = new Set(["dashboard", "usage", "plans", "connections", "security"]);
  const publicViews = new Set(["landing", "login", "signup", ...appViews]);
  const params = new URLSearchParams(location.search);
  const localHost = location.hostname === "127.0.0.1" || location.hostname === "localhost";
  const scenario = String(params.get("scenario") || "").trim().toLowerCase();
  let retryAction = null;

  function validApiBase(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      if (url.protocol === "https:") return url.origin;
      if (url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost")) return url.origin;
    } catch (_error) {}
    return null;
  }

  const apiBase = validApiBase(params.get("api")) || (localHost ? "http://127.0.0.1:9192" : null);

  function number(value) {
    return new Intl.NumberFormat("pt-BR").format(Number(value || 0));
  }

  function setText(id, value) {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  }

  function setState(label, detail, healthy = false) {
    const node = document.getElementById("dashboardState");
    if (node) {
      node.textContent = label;
      node.classList.toggle("healthy", healthy);
    }
    setText("dashboardStateDetail", detail);
  }

  function hideBanner() {
    if (!banner) return;
    banner.hidden = true;
    banner.className = "system-banner";
    if (bannerAction) bannerAction.hidden = true;
    retryAction = null;
  }

  function showBanner(kind, title, message, actionLabel = null, action = null) {
    if (!banner) return;
    banner.hidden = false;
    banner.className = "system-banner show " + kind;
    bannerTitle.textContent = title;
    bannerMessage.textContent = message;
    retryAction = action;
    bannerAction.hidden = !actionLabel;
    if (actionLabel) bannerAction.textContent = actionLabel;
  }

  function setLoading(active) {
    document.body.classList.toggle("product-loading", active);
  }

  function applyDashboard(payload) {
    if (!payload?.entitlement || !payload?.usage) return;
    const plan = payload.entitlement.plan_name || payload.entitlement.plan_code || "—";
    const consumed = Number(payload.usage.consumed_units || 0);
    const limit = payload.usage.limit == null ? null : Number(payload.usage.limit);
    const remaining = payload.usage.remaining_units;
    const percent = limit ? Math.min(100, (consumed / limit) * 100) : 0;

    setText("landingPlan", plan);
    setText("landingUsage", number(consumed));
    setText("landingLimit", limit == null ? "sem limite" : "de " + number(limit));
    setText("dashboardPlan", plan);
    setText("dashboardConsumed", number(consumed));
    setText("dashboardLimit", limit == null ? "/ sem limite" : "/ " + number(limit));
    setText("dashboardPercent", limit == null ? "Plano sem limite definido" : percent.toFixed(2).replace(".", ",") + "% utilizado");
    setText("dashboardInvokes", number(consumed));
    setText("usageConsumed", number(consumed));
    setText("usageLimit", limit == null ? "sem limite" : "de " + number(limit));
    setText("usageRemaining", remaining == null ? "Capacidade sem limite definido" : number(remaining) + " unidades disponíveis");
    setText("usagePeriod", payload.usage.period_key || "—");
    setState("Saudável", "Entitlement ativo", true);

    const bar = document.getElementById("usageProgress");
    if (bar) bar.style.width = (limit == null ? 0 : percent) + "%";
  }

  function renderEmptyActivity() {
    const activity = document.getElementById("activityList");
    if (activity) activity.innerHTML = '<div class="empty-state"><strong>Nenhuma execução ainda</strong>Conecte um cliente MCP e faça a primeira operação governada.</div>';
  }

  function applyScenario(name, payload) {
    if (!name) return;
    const limit = Number(payload?.usage?.limit || payload?.entitlement?.unit_limit || 10000);
    const connections = document.querySelectorAll("#connectionList button:not([disabled])");

    if (name === "loading") {
      showBanner("info", "Carregando dados", "Consultando tenant, entitlement, quota e estado do Commander.");
      return;
    }
    if (name === "empty") {
      renderEmptyActivity();
      showBanner("info", "Workspace pronto", "Ainda não há execuções ou receipts neste workspace.");
      return;
    }
    if (name === "auth-expired") {
      setState("Sessão expirada", "Autenticação necessária");
      showBanner("danger", "Sessão expirada", "Sua sessão DEV expirou. Entre novamente para continuar.", "Entrar novamente", () => route("login"));
      return;
    }
    if (name === "entitlement-suspended") {
      setState("Suspenso", "Entitlement inativo");
      connections.forEach((node) => { node.disabled = true; });
      showBanner("warning", "Entitlement suspenso", "Operações governadas estão bloqueadas até a regularização do entitlement.");
      return;
    }
    if (name === "quota-exhausted") {
      setText("dashboardConsumed", number(limit));
      setText("dashboardLimit", "/ " + number(limit));
      setText("dashboardPercent", "100% utilizado");
      setText("dashboardInvokes", number(limit));
      setText("usageConsumed", number(limit));
      setText("usageLimit", "de " + number(limit));
      setText("usageRemaining", "0 unidades disponíveis");
      const bar = document.getElementById("usageProgress");
      if (bar) bar.style.width = "100%";
      showBanner("warning", "Quota esgotada", "O período atingiu o limite contratado. Novos invokes ficam bloqueados sem afetar receipts anteriores.");
      return;
    }
    if (name === "mcp-unavailable") {
      setState("Degradado", "MCP indisponível");
      showBanner("danger", "Commander temporariamente indisponível", "O Product Plane está ativo, mas o MCP não respondeu ao health check.", "Tentar novamente", loadProductDashboard);
      return;
    }
    if (name === "receipt-unavailable") {
      showBanner("warning", "Receipt indisponível", "A execução foi registrada, mas o receipt solicitado ainda não pôde ser recuperado.", "Tentar novamente", loadProductDashboard);
      return;
    }
    if (name === "billing-disconnected") {
      showBanner("info", "Cobrança ainda não conectada", "Este tenant DEV usa entitlement sintético e não possui provedor de pagamento real.");
      return;
    }
    if (name === "degraded") {
      setState("Degradado", "Uma dependência está instável");
      showBanner("warning", "Serviço degradado", "O Commander continua acessível, mas uma dependência DEV está apresentando instabilidade.", "Revalidar", loadProductDashboard);
    }
  }

  async function loadProductDashboard() {
    hideBanner();
    setLoading(true);

    if (scenario === "loading") {
      applyScenario("loading", null);
      setTimeout(() => setLoading(false), 900);
      return;
    }

    if (!apiBase) {
      setLoading(false);
      showBanner("warning", "Backend DEV não configurado", "Defina um endpoint DEV válido para carregar dados de produto.");
      return;
    }

    try {
      const response = await fetch(apiBase + "/api/dev/dashboard", { cache: "no-store" });
      if (response.status === 401) {
        applyScenario("auth-expired", null);
        return;
      }
      if (!response.ok) throw new Error("HTTP_" + response.status);
      const payload = await response.json();
      applyDashboard(payload);
      applyScenario(scenario, payload);
    } catch (_error) {
      setState("Degradado", "Product API indisponível");
      showBanner("danger", "Backend DEV indisponível", "Não foi possível carregar tenant, entitlement e quota.", "Tentar novamente", loadProductDashboard);
    } finally {
      setLoading(false);
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
    document.querySelectorAll("[data-app-go]").forEach((button) => button.classList.toggle("active", button.dataset.appGo === next));
    document.querySelectorAll("[data-nav]").forEach((link) => link.classList.toggle("active", link.dataset.nav === next));
    document.body.classList.toggle("workspace-mode", appViews.has(next));
    if (push && location.hash !== "#" + next) history.pushState(null, "", "#" + next);
    window.scrollTo({ top: 0, behavior: "instant" });
    if (next === "landing" || next === "dashboard" || next === "usage") loadProductDashboard();
  }

  copySidebars();

  if (bannerAction) {
    bannerAction.addEventListener("click", () => {
      if (retryAction) retryAction();
    });
  }

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
