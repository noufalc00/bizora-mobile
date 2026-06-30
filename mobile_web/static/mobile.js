(() => {
  "use strict";

  const THEME_KEY = "bizora_mobile_theme";
  const SESSION_KEY = "bizora_mobile_session";
  const LAST_NORMAL_COMPANY_KEY = "bizora_mobile_last_normal_company";
  const FETCH_TIMEOUT_MS = 60000;
  const LOGO_LONG_PRESS_MS = 800;

  const storage = {
    get(key, fallback) {
      try {
        const value = localStorage.getItem(key);
        return value == null ? fallback : value;
      } catch (error) {
        return fallback;
      }
    },
    set(key, value) {
      try {
        localStorage.setItem(key, value);
      } catch (error) {
        /* Safari private mode — ignore */
      }
    },
  };

  function resolveApiBase() {
    const meta = document.querySelector('meta[name="mobile-api-base"]');
    const configured = meta ? String(meta.getAttribute("content") || "").replace(/\/$/, "") : "";
    if (!configured) {
      return "";
    }
    try {
      const target = new URL(configured, window.location.origin);
      if (target.host === window.location.host) {
        return "";
      }
      return configured;
    } catch (error) {
      return "";
    }
  }

  const API_BASE = resolveApiBase();

  const state = {
    theme: storage.get(THEME_KEY, "dark"),
    colors: {},
    currency: "₹",
    view: "login",
    reportSlug: null,
    reportTitle: "",
    navigation: null,
    dashboard: null,
    session: null,
    selectedCompany: null,
    isSecretSession: false,
    companyModalVisibility: "normal",
  };

  function loadSession() {
    try {
      const raw = storage.get(SESSION_KEY, "");
      if (!raw) {
        return null;
      }
      const parsed = JSON.parse(raw);
      if (parsed && parsed.company_id) {
        return parsed;
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function saveSession(session) {
    state.session = session;
    storage.set(SESSION_KEY, JSON.stringify(session || {}));
  }

  function clearSession() {
    state.session = null;
    storage.set(SESSION_KEY, "");
  }

  function apiHeaders(extraHeaders) {
    const headers = Object.assign({}, extraHeaders || {});
    if (state.session && state.session.company_id) {
      headers["X-Bizora-Company-Id"] = String(state.session.company_id);
    }
    return headers;
  }

  const el = {
    loginScreen: document.getElementById("loginScreen"),
    appShell: document.getElementById("app"),
    fileMenuBtn: document.getElementById("fileMenuBtn"),
    fileMenuPanel: document.getElementById("fileMenuPanel"),
    openCompaniesBtn: document.getElementById("openCompaniesBtn"),
    loginLogoBox: document.getElementById("loginLogoBox"),
    secretFileBtn: document.getElementById("secretFileBtn"),
    loginCompanyName: document.getElementById("loginCompanyName"),
    loginCompanyHint: document.getElementById("loginCompanyHint"),
    loginForm: document.getElementById("loginForm"),
    loginUsername: document.getElementById("loginUsername"),
    loginPassword: document.getElementById("loginPassword"),
    loginDate: document.getElementById("loginDate"),
    loginSubmitBtn: document.getElementById("loginSubmitBtn"),
    companyModal: document.getElementById("companyModal"),
    companyModalTitle: document.getElementById("companyModalTitle"),
    companyModalList: document.getElementById("companyModalList"),
    companyModalClose: document.getElementById("companyModalClose"),
    logoutBtn: document.getElementById("logoutBtn"),
    loginThemeBtn: document.getElementById("loginThemeToggleBtn"),
    brandCompanyName: document.getElementById("brandCompanyName"),
    main: document.getElementById("mainContent"),
    subtitle: document.getElementById("pageSubtitle"),
    backBtn: document.getElementById("navBackBtn"),
    themeBtn: document.getElementById("themeToggleBtn"),
    toast: document.getElementById("toast"),
    tabs: Array.from(document.querySelectorAll(".tab-btn")),
  };

  function showToast(message) {
    el.toast.textContent = message;
    el.toast.classList.remove("hidden");
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(() => el.toast.classList.add("hidden"), 2600);
  }

  function apiPath(path) {
    if (!path) {
      return API_BASE || "/";
    }
    if (path.charAt(0) === "/") {
      return `${API_BASE}${path}`;
    }
    return `${API_BASE}/${path}`;
  }

  function isCloudHost() {
    return window.location.hostname.indexOf("onrender.com") >= 0;
  }

  function showLoadingMessage(message) {
    el.main.innerHTML = `<div class="empty-state loading-state">${message}</div>`;
  }

  function startLoadingProgress(baseMessage) {
    let seconds = 0;
    showLoadingMessage(baseMessage);
    const timer = window.setInterval(() => {
      seconds += 1;
      if (seconds >= 8 && isCloudHost()) {
        showLoadingMessage(
          `${baseMessage}<br><br>Waking up cloud server (Render free tier). This can take up to 60 seconds on phone networks.`,
        );
      }
    }, 1000);
    return function stopLoadingProgress() {
      window.clearInterval(timer);
    };
  }

  async function fetchWithTimeout(url, options) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    try {
      return await fetch(url, Object.assign({}, options || {}, { signal: controller.signal }));
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw new Error(
          "Request timed out. On Render free tier, wait 60 seconds and tap refresh. "
          + "Use Wi-Fi or strong mobile data.",
        );
      }
      throw error;
    } finally {
      window.clearTimeout(timer);
    }
  }

  function formatFetchError(error) {
    const raw = (error && error.message) ? String(error.message) : "Unknown error";
    if (raw === "Failed to fetch" || raw.indexOf("NetworkError") >= 0) {
      const host = window.location.hostname;
      if (host === "127.0.0.1" || host === "localhost") {
        return (
          "API server is not running on this PC. Open PowerShell in the project folder and run: "
          + "python start_cloud_mobile.py"
        );
      }
      if (/^10\.|^192\.168\.|^172\.(1[6-9]|2\d|3[0-1])\./.test(host)) {
        return (
          "Cannot reach the API on your PC. Keep start_cloud_mobile.py running, use the same "
          + "LAN address on phone and PC, and allow port 8080 in Windows Firewall."
        );
      }
      return (
        "Cannot reach the API server. On Render free tier, wait up to 60 seconds and refresh. "
        + "Clear browser cache on phone if the page stays on Loading."
      );
    }
    return raw;
  }

  function connectionHelpMessage() {
    return formatFetchError({ message: "Failed to fetch" });
  }

  async function apiGet(path) {
    let response;
    try {
      response = await fetchWithTimeout(apiPath(path), {
        cache: "no-store",
        headers: apiHeaders(),
      });
    } catch (error) {
      throw new Error(formatFetchError(error));
    }
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  }

  async function apiPost(path, body) {
    let response;
    try {
      response = await fetchWithTimeout(apiPath(path), {
        method: "POST",
        headers: apiHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify(body),
      });
    } catch (error) {
      throw new Error(formatFetchError(error));
    }
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  }

  function applyThemeTokens(payload) {
    state.theme = payload.theme || state.theme;
    state.colors = payload.colors || {};
    state.currency = payload.currency_symbol || "₹";
    const root = document.documentElement;
    Object.entries(state.colors).forEach(([key, value]) => {
      root.style.setProperty(`--${key.replace(/_/g, "-")}`, value);
    });
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    if (themeMeta) {
      themeMeta.setAttribute("content", state.colors.app_bg || "#121212");
    }
    el.themeBtn.textContent = state.theme === "dark" ? "☀" : "☾";
    if (el.loginThemeBtn) {
      el.loginThemeBtn.textContent = state.theme === "dark" ? "☀" : "☾";
    }
    storage.set(THEME_KEY, state.theme);
  }

  function saveLastNormalCompany(company) {
    if (!company || company.id == null || state.isSecretSession) {
      return;
    }
    const visibility = String(company.visibility || "normal").toLowerCase();
    if (visibility === "secret") {
      return;
    }
    storage.set(LAST_NORMAL_COMPANY_KEY, String(company.id));
  }

  function refreshTopbarCompany() {
    if (!el.brandCompanyName) {
      return;
    }
    const name = (state.session && state.session.company_name)
      || (state.selectedCompany && state.selectedCompany.business_name)
      || "";
    el.brandCompanyName.textContent = name;
  }

  async function loadTheme() {
    const payload = await apiGet(`/api/theme?theme=${encodeURIComponent(state.theme)}`);
    applyThemeTokens(payload);
  }

  function formatMoney(value) {
    const amount = Number(value || 0);
    return `${state.currency}${amount.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }

  function setSubtitle(text) {
    el.subtitle.textContent = text;
    refreshTopbarCompany();
  }

  function setActiveTab(view) {
    el.tabs.forEach((button) => {
      button.classList.toggle("active", button.dataset.view === view);
    });
  }

  function renderChart(title, rows, colorToken) {
    const color = state.colors[colorToken] || state.colors.button_primary || "#2196f3";
    const maxValue = Math.max(...rows.map((row) => Number(row.total || 0)), 1);
    const bars = rows
      .map((row) => {
        const total = Number(row.total || 0);
        const height = Math.max(6, Math.round((total / maxValue) * 110));
        const label = row.label || row.month || "";
        return `
          <div class="chart-col">
            <div class="chart-bar" style="height:${height}px;background:${color}"></div>
            <div class="chart-label">${label}</div>
          </div>
        `;
      })
      .join("");
    return `
      <section class="panel">
        <div class="panel-title">${title}</div>
        <div class="chart-bars">${bars || '<div class="empty-state">No chart data</div>'}</div>
      </section>
    `;
  }

  function todayIsoDate() {
    return new Date().toISOString().slice(0, 10);
  }

  function showLoginScreen() {
    state.view = "login";
    el.loginScreen.classList.remove("hidden");
    el.appShell.classList.add("hidden");
    el.fileMenuPanel.classList.add("hidden");
    hideSecretFileButton();
  }

  function showAppShell() {
    el.loginScreen.classList.add("hidden");
    el.appShell.classList.remove("hidden");
  }

  function hideSecretFileButton() {
    el.secretFileBtn.classList.add("hidden");
  }

  function revealSecretFileButton() {
    el.secretFileBtn.classList.remove("hidden");
    showToast("Secret file unlocked");
  }

  function refreshLoginCompanyDisplay() {
    const company = state.selectedCompany;
    if (!company) {
      el.loginCompanyName.textContent = "No active company selected";
      el.loginCompanyHint.textContent = "Use File > Open Companies to select a company.";
      el.loginSubmitBtn.disabled = true;
      return;
    }
    const gstin = company.gstin || "No GSTIN";
    const companyState = company.state || "State not set";
    el.loginCompanyName.textContent = company.business_name || "Selected company";
    el.loginCompanyHint.textContent = `${gstin} | ${companyState}`;
    el.loginSubmitBtn.disabled = false;
  }

  function populateUsernameOptions(usernames) {
    const options = (usernames && usernames.length ? usernames : ["admin"])
      .map((name) => `<option value="${name}">${name}</option>`)
      .join("");
    el.loginUsername.innerHTML = options;
  }

  async function loadLoginBootstrap() {
    const savedId = storage.get(LAST_NORMAL_COMPANY_KEY, "").trim();
    const query = savedId ? `?last_company_id=${encodeURIComponent(savedId)}` : "";
    const payload = await apiGet(`/api/auth/bootstrap${query}`);
    if (payload.company) {
      state.selectedCompany = payload.company;
      state.isSecretSession = false;
      saveLastNormalCompany(payload.company);
    } else {
      state.selectedCompany = null;
      state.isSecretSession = false;
    }
    if (state.selectedCompany && state.selectedCompany.id) {
      await loadCompanyUsers(Number(state.selectedCompany.id));
    } else {
      populateUsernameOptions(payload.usernames || []);
    }
    refreshLoginCompanyDisplay();
  }

  async function loadCompanyUsers(companyId) {
    try {
      const payload = await apiGet(`/api/companies/${companyId}/users`);
      populateUsernameOptions(payload.usernames || []);
    } catch (error) {
      populateUsernameOptions(["admin"]);
    }
  }

  function closeCompanyModal() {
    el.companyModal.classList.add("hidden");
  }

  async function openCompanyModal(visibility) {
    state.companyModalVisibility = visibility || "normal";
    el.companyModalTitle.textContent = visibility === "secret"
      ? "Open Secret Companies"
      : "Open Companies";
    el.companyModal.classList.remove("hidden");
    el.companyModalList.innerHTML = '<div class="empty-state">Loading companies...</div>';
    try {
      const payload = await apiGet(`/api/companies?visibility=${encodeURIComponent(state.companyModalVisibility)}`);
      if (!payload.success) {
        el.companyModalList.innerHTML = `<div class="error-state">${payload.message || "Could not load companies."}</div>`;
        return;
      }
      const companies = payload.companies || [];
      if (!companies.length) {
        const emptyText = state.companyModalVisibility === "secret"
          ? "No secret companies found."
          : "No companies found.";
        el.companyModalList.innerHTML = `<div class="empty-state">${emptyText}</div>`;
        return;
      }
      el.companyModalList.innerHTML = companies.map((company) => `
        <button class="company-item" type="button" data-company-id="${company.id}">
          <div class="company-item-name">${company.business_name || "Unnamed company"}</div>
          <div class="company-item-meta">${company.gstin || "No GSTIN"} | ${company.state || "State not set"}</div>
        </button>
      `).join("");
      el.companyModalList.querySelectorAll(".company-item").forEach((button) => {
        button.addEventListener("click", async () => {
          const companyId = Number(button.dataset.companyId);
          const selected = companies.find((row) => Number(row.id) === companyId);
          if (!selected) {
            return;
          }
          state.selectedCompany = selected;
          state.isSecretSession = state.companyModalVisibility === "secret";
          if (!state.isSecretSession) {
            saveLastNormalCompany(selected);
          }
          el.loginPassword.value = "";
          await loadCompanyUsers(companyId);
          refreshLoginCompanyDisplay();
          closeCompanyModal();
          showToast(`${selected.business_name || "Company"} selected`);
        });
      });
    } catch (error) {
      el.companyModalList.innerHTML = `<div class="error-state">${formatFetchError(error)}</div>`;
    }
  }

  async function submitLogin(event) {
    event.preventDefault();
    if (!state.selectedCompany || !state.selectedCompany.id) {
      showToast("Select a company first");
      return;
    }
    el.loginSubmitBtn.disabled = true;
    el.loginSubmitBtn.textContent = "Logging in...";
    try {
      const payload = await apiPost("/api/auth/login", {
        company_id: Number(state.selectedCompany.id),
        username: el.loginUsername.value,
        password: el.loginPassword.value,
        is_secret: state.isSecretSession,
      });
      if (!payload.success) {
        showToast(payload.message || "Login failed");
        return;
      }
      saveSession(payload.session || null);
      if (!state.isSecretSession && payload.company) {
        saveLastNormalCompany(payload.company);
      }
      state.navigation = null;
      showAppShell();
      refreshTopbarCompany();
      await renderDashboard();
      showToast(`Welcome, ${payload.session.username}`);
    } catch (error) {
      showToast(formatFetchError(error));
    } finally {
      el.loginSubmitBtn.disabled = !state.selectedCompany;
      el.loginSubmitBtn.textContent = "Login";
    }
  }

  function logoutToLogin() {
    clearSession();
    state.navigation = null;
    state.dashboard = null;
    state.isSecretSession = false;
    el.loginPassword.value = "";
    hideSecretFileButton();
    showLoginScreen();
    loadLoginBootstrap().catch((error) => {
      showToast(formatFetchError(error));
    });
  }

  function installLogoSecretHandlers() {
    let pressTimer = null;
    let lastTap = 0;
    let longPressTriggered = false;

    const clearPress = () => {
      if (pressTimer) {
        window.clearTimeout(pressTimer);
        pressTimer = null;
      }
    };

    const startPress = () => {
      longPressTriggered = false;
      clearPress();
      pressTimer = window.setTimeout(() => {
        longPressTriggered = true;
        revealSecretFileButton();
      }, LOGO_LONG_PRESS_MS);
    };

    const closeSecretIfVisible = () => {
      if (!el.secretFileBtn.classList.contains("hidden")) {
        hideSecretFileButton();
      }
    };

    el.loginLogoBox.addEventListener("dblclick", (event) => {
      event.preventDefault();
      closeSecretIfVisible();
    });

    el.loginLogoBox.addEventListener("click", () => {
      if (longPressTriggered) {
        longPressTriggered = false;
        return;
      }
      const now = Date.now();
      if (now - lastTap < 400) {
        closeSecretIfVisible();
        lastTap = 0;
        return;
      }
      lastTap = now;
    });

    el.loginLogoBox.addEventListener("touchstart", (event) => {
      if (event.target.closest(".login-logo-box")) {
        startPress();
      }
    }, { passive: true });
    el.loginLogoBox.addEventListener("touchend", clearPress);
    el.loginLogoBox.addEventListener("touchmove", clearPress);
    el.loginLogoBox.addEventListener("touchcancel", clearPress);
    el.loginLogoBox.addEventListener("mousedown", startPress);
    el.loginLogoBox.addEventListener("mouseup", clearPress);
    el.loginLogoBox.addEventListener("mouseleave", clearPress);
  }

  async function renderLoginScreen() {
    showLoginScreen();
    el.loginDate.value = todayIsoDate();
    try {
      await loadLoginBootstrap();
    } catch (error) {
      showToast(formatFetchError(error));
    }
  }

  async function renderDashboard() {
    state.view = "dashboard";
    state.reportSlug = null;
    setActiveTab("dashboard");
    setSubtitle("Dashboard");
    el.backBtn.classList.add("hidden");
    const stopLoading = startLoadingProgress("Loading dashboard...");

    try {
      const payload = await apiGet("/api/dashboard");
      stopLoading();
      state.dashboard = payload;
      if (!payload.success) {
        const source = payload.data_source ? ` (${payload.data_source})` : "";
        el.main.innerHTML = `<div class="error-state">${payload.message || "No active company."}${source}</div>`;
        return;
      }

      const summary = payload.summary || {};
      const labels = payload.summary_labels || {};
      const colors = payload.summary_colors || {};
      const cards = Object.keys(labels)
        .map((key) => {
          const accent = state.colors[colors[key]] || state.colors.button_primary;
          return `
            <article class="summary-card" style="border-left-color:${accent}">
              <div class="label">${labels[key]}</div>
              <div class="value">${formatMoney(summary[key])}</div>
            </article>
          `;
        })
        .join("");

      const activity = (payload.recent_activity || [])
        .map((line) => `<div class="activity-item">${line}</div>`)
        .join("");

      const syncHint = payload.sync_hint
        ? `<div class="empty-state">${payload.sync_hint}</div>`
        : "";

      el.main.innerHTML = `
        <section class="summary-grid">${cards}</section>
        ${renderChart("Monthly Sales", payload.sales_chart || [], "button_success")}
        ${renderChart("Monthly Purchase", payload.purchase_chart || [], "button_primary")}
        <section class="panel">
          <div class="panel-title">Recent Activity</div>
          <div class="activity-list">${activity || '<div class="empty-state">No recent activity</div>'}</div>
        </section>
        ${syncHint}
      `;
    } catch (error) {
      stopLoading();
      el.main.innerHTML = `<div class="error-state">${formatFetchError(error)}</div>`;
    }
  }

  function renderNavigationSection(sectionName) {
    const sections = (state.navigation && state.navigation.sections) || {};
    const items = (sections[sectionName] || [])
      .map((entry) => {
        if (entry.type === "divider") {
          return `<div class="menu-divider">${entry.title}</div>`;
        }
        return `<button class="menu-item" data-slug="${entry.slug}" type="button">${entry.title}</button>`;
      })
      .join("");

    return `
      <section>
        <div class="menu-section-title">${sectionName}</div>
        ${items || '<div class="empty-state">No routes found</div>'}
      </section>
    `;
  }

  async function renderNavigation(view) {
    state.view = view;
    state.reportSlug = null;
    setActiveTab(view);
    setSubtitle(view === "books" ? "Books" : "Reports");
    el.backBtn.classList.add("hidden");
    el.main.innerHTML = '<div class="empty-state">Loading menu...</div>';

    try {
      if (!state.navigation) {
        state.navigation = await apiGet("/api/navigation");
      }
      const sectionName = view === "books" ? "Books" : "Reports";
      el.main.innerHTML = renderNavigationSection(sectionName);
      el.main.querySelectorAll(".menu-item").forEach((button) => {
        button.addEventListener("click", () => openReport(button.dataset.slug, button.textContent));
      });
    } catch (error) {
      el.main.innerHTML = `<div class="error-state">${formatFetchError(error)}</div>`;
    }
  }

  function defaultValueForFilter(filter) {
    if (filter.default !== undefined && filter.default !== null) {
      return filter.default;
    }
    if (filter.type === "date") {
      return new Date().toISOString().slice(0, 10);
    }
    if (filter.type === "boolean") {
      return Boolean(filter.default);
    }
    return "";
  }

  function resolveLedgerSearchOptions(lookups, ledgerView) {
    const view = ledgerView || "General";
    if (view === "Debtors") {
      return lookups.ledger_debtors || [];
    }
    if (view === "Creditors") {
      return lookups.ledger_creditors || [];
    }
    if (view === "Cash/Bank") {
      return lookups.ledger_cash_bank || [];
    }
    return lookups.ledger_general || [];
  }

  function buildLookupSelect(filter, options, labelKey, emptyLabel) {
    const fieldId = `filter-${filter.key}`;
    const optionRows = (options || [])
      .map((option) => {
        const label = typeof option === "string" ? option : option[labelKey];
        const value = typeof option === "string" ? option : (option.value != null ? option.value : label);
        if (!label) {
          return "";
        }
        return `<option value="${value}">${label}</option>`;
      })
      .join("");
    return `
      <div class="field" data-filter-key="${filter.key}">
        <label for="${fieldId}">${filter.label}</label>
        <select id="${fieldId}" data-key="${filter.key}">
          <option value="">${emptyLabel}</option>
          ${optionRows}
        </select>
      </div>
    `;
  }

  function buildFilterField(filter, lookups, slug) {
    const fieldId = `filter-${filter.key}`;
    if (filter.key === "party" && (lookups.parties || []).length) {
      return buildLookupSelect(filter, lookups.parties, "name", "All Parties");
    }
    if (filter.key === "product" && (lookups.products || []).length) {
      return buildLookupSelect(filter, lookups.products, "name", "All Products");
    }
    if (filter.key === "category" && (lookups.categories || []).length) {
      return buildLookupSelect(
        filter,
        lookups.categories.map((name) => ({ name })),
        "name",
        "All Categories",
      );
    }
    if (filter.key === "gst" && (lookups.gst_options || []).length) {
      return buildLookupSelect(filter, lookups.gst_options, "label", "All GST");
    }
    if (slug === "ledger" && filter.key === "search") {
      const ledgerView = (document.getElementById("filter-ledger_view") || {}).value || "General";
      const options = resolveLedgerSearchOptions(lookups, ledgerView);
      return buildLookupSelect(filter, options, "name", "All Accounts");
    }
    if (slug === "purchase-order-book" && filter.key === "search" && (lookups.creditors_po || []).length) {
      return buildLookupSelect(
        filter,
        lookups.creditors_po.map((name) => ({ name })),
        "name",
        "All Creditors",
      );
    }
    if (filter.type === "select") {
      const options = (filter.options || [])
        .map((option) => `<option value="${option}">${option}</option>`)
        .join("");
      return `
        <div class="field">
          <label for="${fieldId}">${filter.label}</label>
          <select id="${fieldId}" data-key="${filter.key}">${options}</select>
        </div>
      `;
    }
    if (filter.type === "account") {
      const accounts = lookups.accounts || [];
      const options = accounts
        .map((account) => `<option value="${account.id}">${account.account_name}</option>`)
        .join("");
      return `
        <div class="field">
          <label for="${fieldId}">${filter.label}</label>
          <select id="${fieldId}" data-key="${filter.key}">
            <option value="">Select account</option>
            ${options}
          </select>
        </div>
      `;
    }
    if (filter.type === "boolean") {
      const checked = defaultValueForFilter(filter) ? "checked" : "";
      return `
        <div class="field">
          <label for="${fieldId}">${filter.label}</label>
          <input id="${fieldId}" data-key="${filter.key}" type="checkbox" ${checked}>
        </div>
      `;
    }
    const inputType = filter.type === "number" ? "number" : filter.type === "date" ? "date" : "text";
    return `
      <div class="field" data-filter-key="${filter.key}">
        <label for="${fieldId}">${filter.label}</label>
        <input id="${fieldId}" data-key="${filter.key}" type="${inputType}" value="${defaultValueForFilter(filter)}">
      </div>
    `;
  }

  function replaceLedgerSearchField(formRoot, lookups) {
    const ledgerViewInput = formRoot.querySelector('[data-key="ledger_view"]');
    const ledgerView = ledgerViewInput ? ledgerViewInput.value : "General";
    const searchField = formRoot.querySelector('[data-filter-key="search"]');
    if (!searchField) {
      return;
    }
    const previousValue = (searchField.querySelector("[data-key]") || {}).value || "";
    const searchFilter = { key: "search", label: "Search", type: "text", required: false };
    const replacement = document.createElement("div");
    replacement.innerHTML = buildFilterField(searchFilter, lookups, "ledger");
    const newField = replacement.firstElementChild;
    if (!newField) {
      return;
    }
    searchField.replaceWith(newField);
    const select = newField.querySelector("[data-key]");
    if (select && previousValue) {
      select.value = previousValue;
    }
  }

  function wireDynamicFilters(slug, lookups) {
    const formRoot = document.getElementById("reportForm");
    if (!formRoot || slug !== "ledger") {
      return;
    }
    const ledgerViewInput = formRoot.querySelector('[data-key="ledger_view"]');
    if (!ledgerViewInput) {
      return;
    }
    const refresh = () => replaceLedgerSearchField(formRoot, lookups);
    ledgerViewInput.addEventListener("change", refresh);
    refresh();
  }

  function collectFilters(formRoot) {
    const filters = {};
    formRoot.querySelectorAll("[data-key]").forEach((input) => {
      const key = input.dataset.key;
      if (input.type === "checkbox") {
        filters[key] = input.checked;
      } else {
        filters[key] = input.value;
      }
    });
    return filters;
  }

  function renderResultTable(rows) {
    if (!rows || !rows.length) {
      return '<div class="empty-state">No records found for the selected filters.</div>';
    }
    const columns = Array.from(
      rows.reduce((set, row) => {
        Object.keys(row || {}).forEach((key) => set.add(key));
        return set;
      }, new Set()),
    ).slice(0, 8);

    const head = columns.map((column) => `<th>${column}</th>`).join("");
    const body = rows
      .map((row) => {
        const cells = columns
          .map((column) => `<td>${row[column] != null ? row[column] : ""}</td>`)
          .join("");
        return `<tr>${cells}</tr>`;
      })
      .join("");

    return `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>${head}</tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    `;
  }

  async function runReport(slug) {
    const formRoot = document.getElementById("reportForm");
    const resultRoot = document.getElementById("reportResult");
    resultRoot.innerHTML = '<div class="empty-state">Running report...</div>';
    try {
      const payload = await apiPost(`/api/reports/${slug}/run`, {
        filters: collectFilters(formRoot),
      });
      if (!payload.success) {
        resultRoot.innerHTML = `<div class="error-state">${payload.message || "Report failed."}</div>`;
        return;
      }
      resultRoot.innerHTML = renderResultTable(payload.rows || []);
    } catch (error) {
      resultRoot.innerHTML = `<div class="error-state">${formatFetchError(error)}</div>`;
    }
  }

  async function openReport(slug, title) {
    state.view = "report";
    state.reportSlug = slug;
    state.reportTitle = title;
    setSubtitle(title);
    el.backBtn.classList.remove("hidden");
    el.main.innerHTML = '<div class="empty-state">Loading report...</div>';

    try {
      const meta = await apiGet(`/api/reports/${slug}/meta`);
      const route = meta.route || {};
      const filters = route.filters || [];
      const fields = filters.map((filter) => buildFilterField(filter, meta.lookups || {}, slug)).join("");
      el.main.innerHTML = `
        <section class="panel">
          <div class="panel-title">${route.title || title}</div>
          <form id="reportForm" class="filter-grid">${fields}</form>
          <button id="runReportBtn" class="primary-btn" type="button">Open Report</button>
          <div id="reportResult"></div>
        </section>
      `;
      wireDynamicFilters(slug, meta.lookups || {});
      document.getElementById("runReportBtn").addEventListener("click", () => runReport(slug));
    } catch (error) {
      el.main.innerHTML = `<div class="error-state">${formatFetchError(error)}</div>`;
    }
  }

  function bindEvents() {
    installLogoSecretHandlers();

    el.fileMenuBtn.addEventListener("click", () => {
      el.fileMenuPanel.classList.toggle("hidden");
    });

    el.openCompaniesBtn.addEventListener("click", () => {
      el.fileMenuPanel.classList.add("hidden");
      openCompanyModal("normal");
    });

    el.secretFileBtn.addEventListener("click", () => {
      openCompanyModal("secret");
    });

    el.companyModalClose.addEventListener("click", closeCompanyModal);
    el.companyModal.addEventListener("click", (event) => {
      if (event.target === el.companyModal) {
        closeCompanyModal();
      }
    });

    el.loginForm.addEventListener("submit", submitLogin);

    el.logoutBtn.addEventListener("click", logoutToLogin);

    el.tabs.forEach((button) => {
      button.addEventListener("click", () => {
        const view = button.dataset.view;
        if (view === "dashboard") {
          renderDashboard();
          return;
        }
        renderNavigation(view);
      });
    });

    el.themeBtn.addEventListener("click", async () => {
      state.theme = state.theme === "dark" ? "light" : "dark";
      await loadTheme();
      if (state.view === "dashboard") {
        renderDashboard();
      } else if (state.view === "books" || state.view === "reports") {
        renderNavigation(state.view);
      } else if (state.reportSlug) {
        openReport(state.reportSlug, state.reportTitle);
      }
      showToast(`${state.theme === "dark" ? "Dark" : "Light"} mode applied`);
    });

    if (el.loginThemeBtn) {
      el.loginThemeBtn.addEventListener("click", async () => {
        state.theme = state.theme === "dark" ? "light" : "dark";
        await loadTheme();
        showToast(`${state.theme === "dark" ? "Dark" : "Light"} mode applied`);
      });
    }

    el.backBtn.addEventListener("click", () => {
      if (state.view === "report") {
        const section = state.reportTitle && state.navigation
          ? (state.navigation.sections.Books || []).some((item) => item.slug === state.reportSlug)
            ? "books"
            : "reports"
          : "books";
        renderNavigation(section);
      }
    });
  }

  async function boot() {
    bindEvents();
    state.session = loadSession();
    const stopLoading = startLoadingProgress("Connecting...");
    try {
      await loadTheme();
      stopLoading();
      if (state.session && state.session.company_id) {
        showAppShell();
        refreshTopbarCompany();
        await renderDashboard();
        return;
      }
      await renderLoginScreen();
    } catch (error) {
      stopLoading();
      showLoginScreen();
      el.loginCompanyHint.textContent = formatFetchError(error);
    }
  }

  boot();
})();
