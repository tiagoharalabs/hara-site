(() => {
  const views = [...document.querySelectorAll("[data-view]")];
  const toast = document.getElementById("toast");
  const sidebarTemplate = document.getElementById("sidebarTemplate");
  const banner = document.getElementById("systemBanner");
  const bannerTitle = document.getElementById("systemBannerTitle");
  const bannerMessage = document.getElementById("systemBannerMessage");
  const bannerAction = document.getElementById("systemBannerAction");
  const appViews = new Set(["dashboard", "devices", "usage", "plans", "connections", "security"]);
  const publicViews = new Set(["landing", "login", "signup", ...appViews]);
  const params = new URLSearchParams(location.search);
  const root = document.documentElement;
  const themeBtn = document.querySelector(".theme-toggle");
  const themeMeta = document.querySelector('meta[name="theme-color"]');
  const brandLink = document.querySelector(".brand");
  const guestActions = document.querySelector("[data-auth-guest]");
  const sessionActions = document.querySelector("[data-auth-session]");
  const localHost = location.hostname === "127.0.0.1" || location.hostname === "localhost";
  const scenario = String(params.get("scenario") || "").trim().toLowerCase();
  const authError = String(params.get("auth_error") || "").trim().toUpperCase();
  const remotePortal = !localHost;
  let retryAction = null;
  let authProviderConfigured = false;

  function currentTheme() {
    return root.dataset.theme === "dark" ? "dark" : "light";
  }

  function syncThemeUi() {
    const dark = currentTheme() === "dark";
    if (themeBtn) {
      themeBtn.setAttribute("aria-pressed", String(dark));
      themeBtn.setAttribute("aria-label", dark ? "Ativar modo claro" : "Ativar modo escuro");
      themeBtn.title = dark ? "Modo claro" : "Modo escuro";
    }
    if (themeMeta) themeMeta.setAttribute("content", dark ? "#061721" : "#eef8fd");
    root.style.colorScheme = dark ? "dark" : "light";
  }

  syncThemeUi();
  themeBtn?.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try { localStorage.setItem("hara-theme", next); } catch (_error) {}
    syncThemeUi();
  });

  function validApiBase(value) {
    if (!value) return null;
    try {
      const url = new URL(value);
      if (url.protocol === "https:") return url.origin;
      if (url.protocol === "http:" && (url.hostname === "127.0.0.1" || url.hostname === "localhost")) return url.origin;
    } catch (_error) {}
    return null;
  }

  const apiBase = validApiBase(params.get("api")) || (localHost ? "http://127.0.0.1:9192" : location.origin);
  const dashboardPath = localHost ? "/api/dev/dashboard" : "/api/portal/dashboard";

  function startRemoteAuth(signup = false, forceLogin = false) {
    if (!remotePortal) {
      route(signup ? "signup" : "login");
      return;
    }
    if (!authProviderConfigured) {
      showToast("O HARA Identity ainda não está disponível para autenticação.");
      return;
    }
    const target = "/auth/login?return_to=" + encodeURIComponent("/#dashboard")
      + (signup ? "&screen_hint=signup" : "")
      + (forceLogin ? "&force_login=1" : "");
    location.assign(target);
  }

  async function configureAuthUi() {
    if (!remotePortal) return;
    try {
      const response = await fetch("/api/portal/auth-config", { cache: "no-store" });
      const config = await response.json();
      authProviderConfigured = Boolean(response.ok && config.configured);

      document.querySelectorAll("[data-auth-form]").forEach((form) => {
        form.querySelectorAll("input").forEach((input) => {
          input.disabled = true;
          input.setAttribute("aria-disabled", "true");
        });
        const submit = form.querySelector('button[type="submit"]');
        if (submit) {
          submit.disabled = !authProviderConfigured;
          submit.textContent = form.dataset.authForm === "signup"
            ? "Continuar para cadastro seguro"
            : "Continuar para login seguro";
        }
      });

      document.querySelectorAll(".auth-note").forEach((node) => {
        node.textContent = authProviderConfigured
          ? "A autenticação acontece no HARA Identity. O H.A.R.A. não recebe nem armazena sua senha."
          : "O provedor de identidade está temporariamente indisponível.";
      });
    } catch (_error) {
      authProviderConfigured = false;
    }
  }

  function setGuestHeader() {
    if (guestActions) guestActions.hidden = false;
    if (sessionActions) sessionActions.hidden = true;
    if (brandLink) brandLink.href = "#landing";
    document.body.classList.remove("session-authenticated");
  }

  function setAuthenticatedHeader(payload) {
    if (guestActions) guestActions.hidden = true;
    if (sessionActions) sessionActions.hidden = false;
    if (brandLink) brandLink.href = "#dashboard";
    document.body.classList.add("session-authenticated");
    applyIdentityFields(payload);
  }

  async function logoutRemote() {
    if (remotePortal) {
      await fetch("/auth/logout", { method: "POST", cache: "no-store" }).catch(() => null);
    }
    setGuestHeader();
    route("landing");
  }

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

  function initials(value) {
    const parts = String(value || "").trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return "HA";
    return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
  }

  function applyIdentityFields(payload) {
    const tenantName = String(payload?.tenant?.display_name || "HARA Labs");
    const userName = String(payload?.subject?.display_name || "Conta HARA");
    const userRole = String(payload?.subject?.role || "Owner");
    document.querySelectorAll("[data-tenant-name]").forEach((node) => { node.textContent = tenantName; });
    document.querySelectorAll("[data-user-name]").forEach((node) => { node.textContent = userName; });
    const subjectId = String(payload?.subject?.subject_id || "—");
    const tenantId = String(payload?.tenant?.tenant_id || "—");
    document.querySelectorAll("[data-user-role]").forEach((node) => { node.textContent = userRole; });
    document.querySelectorAll("[data-user-initials]").forEach((node) => { node.textContent = initials(userName); });
    document.querySelectorAll("[data-security-subject]").forEach((node) => { node.textContent = subjectId; });
    document.querySelectorAll("[data-security-tenant]").forEach((node) => { node.textContent = tenantId; });
    document.querySelectorAll("[data-security-role]").forEach((node) => { node.textContent = userRole.toUpperCase(); });
  }

  function applyIdentity(payload) {
    applyIdentityFields(payload);
    setAuthenticatedHeader(payload);
  }

  function applyDashboard(payload) {
    if (!payload?.entitlement || !payload?.usage) return;
    applyIdentity(payload);
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
    const activeConnections = Number(payload?.connections?.active_count || 0);
    setText("dashboardConnections", activeConnections + (activeConnections === 1 ? " conectado" : " conectados"));
    setText("dashboardConnectionsDetail", activeConnections ? "Commander Agent online" : "Instale o Commander Agent");
    setText("landingConnections", number(activeConnections));
    setText("landingConnectionsDetail", activeConnections ? "Commander Agent online" : "Nenhum computador conectado");
    setText("usageConsumed", number(consumed));
    setText("usageLimit", limit == null ? "sem limite" : "de " + number(limit));
    setText("usageRemaining", remaining == null ? "Capacidade sem limite definido" : number(remaining) + " unidades disponíveis");
    setText("usagePeriod", payload.usage.period_key || "—");
    setState(
      activeConnections ? "Pronto" : "Aguardando",
      activeConnections ? "Computador conectado" : "Conecte seu computador"
    );

    const bar = document.getElementById("usageProgress");
    if (bar) bar.style.width = (limit == null ? 0 : percent) + "%";
    renderActivity(payload?.activity || []);
  }

  async function hydrateSessionHeader() {
    if (!remotePortal) return;
    try {
      const response = await fetch("/api/portal/session", { cache: "no-store", credentials: "same-origin" });
      if (!response.ok) {
        if (response.status === 401) setGuestHeader();
        return;
      }
      const payload = await response.json();
      applyIdentity(payload);
    } catch (_error) {
      // Session chrome must never depend on quota/telemetry availability.
    }
  }

  function formatDeviceSeen(value) {
    if (!value) return "Ainda não conectado";
    const date = new Date(String(value));
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",
      timeStyle: "medium",
    }).format(date);
  }

  function renderDevices(payload) {
    const list = document.getElementById("deviceList");
    const devices = Array.isArray(payload?.devices) ? payload.devices : [];
    const onlineCount = Number(payload?.online_count || 0);

    setText("dashboardConnections", onlineCount + (onlineCount === 1 ? " conectado" : " conectados"));
    setText("dashboardConnectionsDetail", onlineCount ? "Commander Agent online" : "Instale o Commander Agent");
    setState(
      onlineCount ? "Pronto" : "Aguardando",
      onlineCount ? "Computador conectado" : "Conecte seu computador"
    );

    if (!list) return;
    list.replaceChildren();

    if (!devices.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "Nenhum computador conectado";
      empty.append(title, document.createTextNode("Instale o Commander Agent para começar."));
      list.append(empty);
      return;
    }

    devices.forEach((device) => {
      const row = document.createElement("div");
      row.className = "device-row";

      const icon = document.createElement("span");
      icon.className = "device-platform";
      icon.textContent = device.platform === "WINDOWS" ? "WIN" : "LIN";

      const body = document.createElement("div");
      body.className = "device-copy";
      const name = document.createElement("b");
      name.textContent = String(device.device_name || "Computador");
      const meta = document.createElement("small");
      const arch = device.architecture ? " · " + String(device.architecture) : "";
      meta.textContent = String(device.platform || "—") + arch + " · " + formatDeviceSeen(device.last_seen_at_utc);
      body.append(name, meta);

      const state = document.createElement("span");
      state.className = "device-state " + (device.online ? "online" : device.state === "REVOKED" ? "revoked" : "offline");
      state.textContent = device.state === "REVOKED" ? "Revogado" : device.online ? "Online" : "Offline";

      row.append(icon, body, state);

      if (device.state === "ACTIVE") {
        const revoke = document.createElement("button");
        revoke.className = "link-button";
        revoke.type = "button";
        revoke.dataset.revokeDevice = String(device.device_id);
        revoke.textContent = "Revogar";
        row.append(revoke);
      }
      list.append(row);
    });
  }

  async function loadDevices() {
    if (!remotePortal) return;
    try {
      const response = await fetch("/api/portal/devices", { cache: "no-store", credentials: "same-origin" });
      if (response.status === 401) {
        setGuestHeader();
        return;
      }
      if (!response.ok) throw new Error("HTTP_" + response.status);
      renderDevices(await response.json());
    } catch (_error) {
      const list = document.getElementById("deviceList");
      if (list) {
        list.replaceChildren();
        const empty = document.createElement("div");
        empty.className = "empty-state";
        const title = document.createElement("strong");
        title.textContent = "Não foi possível atualizar agora";
        empty.append(title, document.createTextNode("Sua conta continua ativa. Tente novamente."));
        list.append(empty);
      }
    }
  }

  async function createPairing() {
    const button = document.querySelector("[data-create-pairing]");
    if (button) button.disabled = true;
    try {
      const response = await fetch("/api/portal/devices/pairing", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("HTTP_" + response.status);
      const payload = await response.json();
      const token = String(payload?.pairing_token || "");
      if (!token) throw new Error("PAIRING_TOKEN_MISSING");
      setText("pairingToken", token);
      const panel = document.getElementById("pairingPanel");
      if (panel) panel.hidden = false;
      const expiry = document.getElementById("pairingExpiry");
      if (expiry) {
        const when = new Date(payload.expires_at_utc);
        expiry.textContent = Number.isNaN(when.getTime())
          ? "Expira em 10 minutos"
          : "Expira às " + new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(when);
      }
      showToast("Código de pareamento criado. Ele funciona uma única vez.");
    } catch (_error) {
      showToast("Não foi possível gerar o código de pareamento.");
    } finally {
      if (button) button.disabled = false;
    }
  }

  async function revokeDevice(deviceId) {
    try {
      const response = await fetch("/api/portal/devices/revoke", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ device_id: deviceId }),
      });
      if (!response.ok) throw new Error("HTTP_" + response.status);
      showToast("Computador revogado.");
      await loadDevices();
    } catch (_error) {
      showToast("Não foi possível revogar o computador.");
    }
  }

  async function copyText(value, successMessage) {
    try {
      await navigator.clipboard.writeText(String(value || ""));
      showToast(successMessage);
    } catch (_error) {
      showToast("Não foi possível copiar automaticamente.");
    }
  }

  function formatActivityTime(value) {
    const date = new Date(String(value || ""));
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(date);
  }

  function shortReceipt(value) {
    const receipt = String(value || "").trim();
    if (!receipt) return "—";
    if (receipt.length <= 14) return receipt;
    return receipt.slice(0, 7) + "…" + receipt.slice(-5);
  }

  function renderEmptyActivity() {
    const activity = document.getElementById("activityList");
    if (activity) {
      activity.replaceChildren();
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "Nenhuma execução ainda";
      empty.append(title, document.createTextNode("As operações reais deste workspace aparecerão aqui."));
      activity.append(empty);
    }

    const ledger = document.getElementById("usageLedger");
    if (ledger) {
      [...ledger.querySelectorAll(".tr:not(.head), .empty-state")].forEach((node) => node.remove());
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const title = document.createElement("strong");
      title.textContent = "Nenhum evento de uso";
      empty.append(title, document.createTextNode("O ledger será preenchido por operações reais do workspace."));
      ledger.append(empty);
    }
  }

  function renderActivity(rows) {
    const activityRows = Array.isArray(rows) ? rows : [];
    if (!activityRows.length) {
      renderEmptyActivity();
      return;
    }

    const activity = document.getElementById("activityList");
    if (activity) {
      activity.replaceChildren();
      activityRows.slice(0, 6).forEach((row) => {
        const state = String(row?.state || "UNKNOWN").toUpperCase();
        const item = document.createElement("div");
        const dot = document.createElement("i");
        dot.className = state === "COMMITTED" ? "ok" : state === "DENIED" ? "deny" : "";
        const text = document.createElement("span");
        const fn = document.createElement("b");
        fn.textContent = String(row?.function_id || "—");
        const meta = document.createElement("small");
        meta.textContent = state + " · " + formatActivityTime(row?.updated_at_utc);
        text.append(fn, meta);
        const status = document.createElement("strong");
        status.textContent = state;
        item.append(dot, text, status);
        activity.append(item);
      });
    }

    const ledger = document.getElementById("usageLedger");
    if (ledger) {
      [...ledger.querySelectorAll(".tr:not(.head), .empty-state")].forEach((node) => node.remove());
      activityRows.forEach((row) => {
        const state = String(row?.state || "UNKNOWN").toUpperCase();
        const line = document.createElement("div");
        line.className = "tr";

        const time = document.createElement("span");
        time.textContent = formatActivityTime(row?.updated_at_utc);
        const fn = document.createElement("span");
        fn.textContent = String(row?.function_id || "—");
        const stateCell = document.createElement("span");
        stateCell.className = "tag " + state.toLowerCase();
        stateCell.textContent = state;
        const units = document.createElement("span");
        units.textContent = number(row?.units || 0);
        const receipt = document.createElement("span");
        receipt.textContent = shortReceipt(row?.receipt_sha256);

        line.append(time, fn, stateCell, units, receipt);
        ledger.append(line);
      });
    }
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
      showBanner("danger", "Sessão expirada", "Sua sessão expirou. Entre novamente para continuar.", "Entrar novamente", () => startRemoteAuth(false));
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
      setState("Aguardando", "Cliente MCP ainda não conectado");
      showBanner("info", "Conexão ainda não disponível", "Conecte o HARA Commander Agent e depois autorize ChatGPT ou Codex.", "Atualizar", loadProductDashboard);
      return;
    }
    if (name === "receipt-unavailable") {
      showBanner("warning", "Receipt indisponível", "A execução foi registrada, mas o receipt solicitado ainda não pôde ser recuperado.", "Tentar novamente", loadProductDashboard);
      return;
    }
    if (name === "billing-disconnected") {
      showBanner("info", "Cobrança ainda não conectada", "Este workspace ainda não possui um provedor de pagamento conectado.");
      return;
    }
    if (name === "degraded") {
      setState("Aguardando", "Dados de conta temporariamente indisponíveis");
      showBanner("info", "Dados ainda não atualizados", "Sua conta continua autenticada. Tente atualizar os dados do Commander.", "Atualizar", loadProductDashboard);
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
      showBanner("warning", "Serviço de produto não configurado", "Não foi possível localizar um endpoint válido para os dados do produto.");
      return;
    }

    try {
      const response = await fetch(apiBase + dashboardPath, { cache: "no-store", credentials: "same-origin" });
      if (response.status === 401) {
        setGuestHeader();
        applyScenario("auth-expired", null);
        return;
      }
      if (!response.ok) throw new Error("HTTP_" + response.status);
      const payload = await response.json();
      applyDashboard(payload);
      applyScenario(scenario, payload);
    } catch (_error) {
      setState("Aguardando", "Dados da conta ainda não carregados");
      showBanner("info", "Dados da conta não atualizados", "O login continua válido. Atualize para carregar plano e uso quando o serviço responder.", "Atualizar", loadProductDashboard);
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
    if (next === "devices") {
      hydrateSessionHeader();
      loadDevices();
    } else if (appViews.has(next) || (next === "landing" && localHost)) {
      loadProductDashboard();
      if (next === "dashboard") loadDevices();
    }
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
      if (remotePortal && go.dataset.go === "login") {
        startRemoteAuth(false);
        return;
      }
      if (remotePortal && go.dataset.go === "signup") {
        startRemoteAuth(true);
        return;
      }
      if (remotePortal && go.dataset.go === "other-account") {
        startRemoteAuth(false, true);
        return;
      }
      route(go.dataset.go);
      return;
    }

    const appGo = event.target.closest("[data-app-go]");
    if (appGo) {
      event.preventDefault();
      route(appGo.dataset.appGo);
      return;
    }

    const logout = event.target.closest("[data-logout]");
    if (logout) {
      event.preventDefault();
      logoutRemote();
      return;
    }

    const pairing = event.target.closest("[data-create-pairing]");
    if (pairing) {
      event.preventDefault();
      createPairing();
      return;
    }

    const refreshDevices = event.target.closest("[data-refresh-devices]");
    if (refreshDevices) {
      event.preventDefault();
      loadDevices();
      return;
    }

    const copyLinux = event.target.closest("[data-copy-linux]");
    if (copyLinux) {
      event.preventDefault();
      copyText(
        "curl -fsSL https://hara-commander-dev-v2.tiago-sartori.workers.dev/install/linux.sh | bash",
        "Comando Linux copiado."
      );
      return;
    }

    const copyWindows = event.target.closest("[data-copy-windows]");
    if (copyWindows) {
      event.preventDefault();
      copyText(
        "irm https://hara-commander-dev-v2.tiago-sartori.workers.dev/install/windows.ps1 | iex",
        "Comando Windows copiado."
      );
      return;
    }

    const copyPairing = event.target.closest("[data-copy-pairing]");
    if (copyPairing) {
      event.preventDefault();
      copyText(document.getElementById("pairingToken")?.textContent || "", "Código de pareamento copiado.");
      return;
    }

    const revokeDeviceButton = event.target.closest("[data-revoke-device]");
    if (revokeDeviceButton) {
      event.preventDefault();
      revokeDevice(revokeDeviceButton.dataset.revokeDevice);
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
      if (remotePortal) {
        startRemoteAuth(form.dataset.authForm === "signup");
        return;
      }
      const label = form.dataset.authForm === "signup"
        ? "Prévia local carregada. Nenhuma credencial foi persistida."
        : "Prévia local carregada. Nenhuma credencial foi enviada.";
      showToast(label);
      route("dashboard");
      form.reset();
    });
  });

  window.addEventListener("popstate", () => route(location.hash.slice(1) || "landing", false));
  window.addEventListener("hashchange", () => route(location.hash.slice(1) || "landing", false));

  configureAuthUi();
  const initialRoute = location.hash.slice(1) || "landing";
  setGuestHeader();
  route(initialRoute, false);
  if (!appViews.has(initialRoute)) hydrateSessionHeader();

  if (authError) {
    const authMessages = {
      IDENTITY_NOT_PROVISIONED: "A conta escolhida foi autenticada, mas não tem acesso a este workspace. Use outra conta HARA Identity autorizada.",
      IDENTITY_INACTIVE: "Esta identidade está inativa no Commander.",
      IDENTITY_INVITE_EXPIRED: "O convite desta identidade expirou.",
      OIDC_STATE_EXPIRED: "A tentativa de login expirou. Inicie o login novamente.",
      OIDC_STATE_INVALID: "A validação de segurança do login falhou. Inicie o login novamente.",
      OIDC_STATE_REPLAYED: "Esta tentativa de login já foi utilizada. Inicie uma nova.",
      OIDC_PROVIDER_ERROR: "O provedor de identidade recusou ou cancelou o login.",
      AUTH_CALLBACK_FAILED: "Não foi possível concluir o login seguro.",
    };
    const useAnotherAccount = authError === "IDENTITY_NOT_PROVISIONED";
    showBanner(
      "warning",
      "Login não concluído",
      authMessages[authError] || "Não foi possível concluir o login seguro.",
      useAnotherAccount ? "Usar outra conta" : "Tentar novamente",
      () => startRemoteAuth(false, useAnotherAccount),
    );
    history.replaceState(null, "", location.pathname + "#login");
  }

  if (localHost) loadProductDashboard();
})();
