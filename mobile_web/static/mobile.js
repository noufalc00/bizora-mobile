(() => {
  "use strict";

  const THEME_KEY = "bizora_mobile_theme";
  const apiBaseMeta = document.querySelector('meta[name="mobile-api-base"]');
  const API_BASE = apiBaseMeta && apiBaseMeta.getAttribute("content")
    ? apiBaseMeta.getAttribute("content").replace(/\/$/, "")
    : "";

  const state = {
    theme: localStorage.getItem(THEME_KEY) || "dark",
    colors: {},
    currency: "₹",
    view: "dashboard",
    reportSlug: null,
    reportTitle: "",
    navigation: null,
    dashboard: null,
  };

  const el = {
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
    return `${API_BASE}${path}`;
  }

  function connectionHelpMessage() {
    if (window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost") {
      return (
        "Cannot reach API. On a phone, open your PC LAN address from start_mobile_web.py "
        "(for example http://192.168.1.10:8080), not 127.0.0.1."
      );
    }
    return "Cannot reach API. Check that start_mobile_web.py is running and Windows Firewall allows the port.";
  }

  async function apiGet(path) {
    let response;
    try {
      response = await fetch(apiPath(path), { cache: "no-store" });
    } catch (error) {
      throw new Error(connectionHelpMessage());
    }
    if (!response.ok) {
      throw new Error(`Request failed: ${response.status}`);
    }
    return response.json();
  }

  async function apiPost(path, body) {
    let response;
    try {
      response = await fetch(apiPath(path), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (error) {
      throw new Error(connectionHelpMessage());
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
    localStorage.setItem(THEME_KEY, state.theme);
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

  async function renderDashboard() {
    state.view = "dashboard";
    state.reportSlug = null;
    setActiveTab("dashboard");
    setSubtitle("Dashboard");
    el.backBtn.classList.add("hidden");
    el.main.innerHTML = '<div class="empty-state">Loading dashboard...</div>';

    try {
      const payload = await apiGet("/api/dashboard");
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

      el.main.innerHTML = `
        <section class="summary-grid">${cards}</section>
        ${renderChart("Monthly Sales", payload.sales_chart || [], "button_success")}
        ${renderChart("Monthly Purchase", payload.purchase_chart || [], "button_primary")}
        <section class="panel">
          <div class="panel-title">Recent Activity</div>
          <div class="activity-list">${activity || '<div class="empty-state">No recent activity</div>'}</div>
        </section>
      `;
    } catch (error) {
      el.main.innerHTML = `<div class="error-state">${error.message}</div>`;
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
      el.main.innerHTML = `<div class="error-state">${error.message}</div>`;
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

  function buildFilterField(filter, lookups) {
    const fieldId = `filter-${filter.key}`;
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
      <div class="field">
        <label for="${fieldId}">${filter.label}</label>
        <input id="${fieldId}" data-key="${filter.key}" type="${inputType}" value="${defaultValueForFilter(filter)}">
      </div>
    `;
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
      resultRoot.innerHTML = `<div class="error-state">${error.message}</div>`;
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
      const fields = filters.map((filter) => buildFilterField(filter, meta.lookups || {})).join("");
      el.main.innerHTML = `
        <section class="panel">
          <div class="panel-title">${route.title || title}</div>
          <form id="reportForm" class="filter-grid">${fields}</form>
          <button id="runReportBtn" class="primary-btn" type="button">Open Report</button>
          <div id="reportResult"></div>
        </section>
      `;
      document.getElementById("runReportBtn").addEventListener("click", () => runReport(slug));
    } catch (error) {
      el.main.innerHTML = `<div class="error-state">${error.message}</div>`;
    }
  }

  function bindEvents() {
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
    try {
      await loadTheme();
      await renderDashboard();
    } catch (error) {
      el.main.innerHTML = `<div class="error-state">${error.message}</div>`;
    }
  }

  boot();
})();
