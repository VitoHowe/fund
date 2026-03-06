(function () {
  const app = document.getElementById("app");
  const pagePath = document.body.dataset.pagePath || window.location.pathname;
  const pageQuery = new URLSearchParams(document.body.dataset.pageQuery || window.location.search.slice(1));

  const state = {
    session: null,
    message: null,
    currentModelId: null,
    currentStrategyId: null,
  };

  document.addEventListener("DOMContentLoaded", init);

  async function init() {
    try {
      state.session = await apiFetch("/api/auth/session");
    } catch (error) {
      state.session = { authenticated: false };
    }
    if (pagePath === "/") {
      window.location.replace("/dashboard/today");
      return;
    }
    if (pagePath === "/login") {
      if (state.session && state.session.authenticated) {
        window.location.replace(pageQuery.get("next") || "/dashboard/today");
        return;
      }
      renderLogin();
      return;
    }
    if (!state.session || !state.session.authenticated) {
      window.location.replace(`/login?next=${encodeURIComponent(pagePath)}`);
      return;
    }
    if (pagePath.startsWith("/dashboard")) {
      renderDashboard();
      return;
    }
    if (pagePath.startsWith("/fund")) {
      renderFundPage();
      return;
    }
    if (pagePath === "/settings/models") {
      renderModelsPage();
      return;
    }
    if (pagePath === "/settings/strategy") {
      renderStrategiesPage();
      return;
    }
    renderNotFound();
  }

  async function apiFetch(url, options = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
    const response = await fetch(url, Object.assign({ credentials: "same-origin" }, options, { headers }));
    const text = await response.text();
    const data = text ? JSON.parse(text) : {};
    if (!response.ok) {
      const error = new Error(data.error || response.statusText);
      error.payload = data;
      throw error;
    }
    return data;
  }

  function shell(title, description, bodyHtml) {
    app.innerHTML = `
      <div class="shell">
        <section class="hero">
          <div class="hero-card">
            <span class="eyebrow">Fund Intel Admin</span>
            <h1>${escapeHtml(title)}</h1>
            <p>${escapeHtml(description)}</p>
            <nav class="nav">
              ${navLink("/dashboard/today", "今日报告")}
              ${navLink(`/fund/${escapeHtml(defaultFundSymbol())}`, "单基金")}
              ${navLink("/settings/models", "模型配置")}
              ${navLink("/settings/strategy", "策略配置")}
              <button class="ghost-button" id="logoutButton" type="button">退出登录</button>
            </nav>
          </div>
          <div class="hero-card">
            <div class="eyebrow">Session</div>
            <h2 style="margin: 14px 0 8px;">${escapeHtml(state.session.session.username || "admin")}</h2>
            <p>会话有效期：${escapeHtml(state.session.session.expires_at || "-")}</p>
            <p class="subtle">模型配置版本：${escapeHtml(state.session.config_versions.models.version || "-")}</p>
            <p class="subtle">策略配置版本：${escapeHtml(state.session.config_versions.strategies.version || "-")}</p>
          </div>
        </section>
        ${state.message ? messageHtml(state.message.type, state.message.text) : ""}
        ${bodyHtml}
      </div>
    `;
    const logoutButton = document.getElementById("logoutButton");
    if (logoutButton) {
      logoutButton.addEventListener("click", logout);
    }
  }

  function navLink(path, label) {
    const active = pagePath === path ? "active" : "";
    return `<a class="${active}" href="${path}">${label}</a>`;
  }

  function renderLogin() {
    app.innerHTML = `
      <div class="login-wrap">
        <form class="login" id="loginForm">
          <span class="eyebrow">Runtime Access</span>
          <h1>登录管理台</h1>
          <p class="muted">当前管理台用于日报生成、模型配置、策略调优和链路监控。默认开发密码可通过环境变量覆盖。</p>
          ${state.message ? messageHtml(state.message.type, state.message.text) : ""}
          <div class="field">
            <label for="password">管理员密码</label>
            <input id="password" name="password" type="password" autocomplete="current-password" placeholder="输入密码" />
          </div>
          <div class="actions" style="margin-top: 16px;">
            <button class="button" type="submit">登录</button>
          </div>
          <p class="subtle" style="margin-top: 16px;">成功后将跳转到 ${escapeHtml(pageQuery.get("next") || "/dashboard/today")}</p>
        </form>
      </div>
    `;
    document.getElementById("loginForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const password = document.getElementById("password").value;
      try {
        await apiFetch("/api/auth/login", {
          method: "POST",
          body: JSON.stringify({ password }),
        });
        window.location.replace(pageQuery.get("next") || "/dashboard/today");
      } catch (error) {
        const retry = error.payload && error.payload.retry_after_seconds ? `，${error.payload.retry_after_seconds}s 后重试` : "";
        setMessage("error", `登录失败：${error.message}${retry}`);
        renderLogin();
      }
    });
  }

  async function renderDashboard() {
    shell(
      "今日量化报告",
      "在同一页面里完成“生成、查看、导出、监控”闭环，所有卡片都直接消费后端当前运行时的真实响应。",
      `
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2 style="margin: 0;">报告控制台</h2>
              <p class="muted">支持同步生成今日报告、读取最近报告和导出 Markdown。</p>
            </div>
            <div class="status-row">
              <button class="ghost-button" id="loadLatestReport" type="button">读取最新</button>
              <button class="ghost-button" id="loadMonitor" type="button">刷新链路状态</button>
            </div>
          </div>
          <div class="toolbar">
            <div class="field">
              <label>基金/ETF 代码</label>
              <input id="symbolsInput" value="014943,159870" />
            </div>
            <div class="field">
              <label>市场状态</label>
              <select id="marketStateSelect">
                <option value="neutral">neutral</option>
                <option value="bull">bull</option>
                <option value="bear">bear</option>
              </select>
            </div>
            <div class="field">
              <label>操作</label>
              <button class="button" id="generateReport" type="button">一键生成今日报告</button>
            </div>
            <div class="field">
              <label>导出</label>
              <a class="ghost-button" id="exportReport" href="/api/report/export?symbols=014943,159870&format=md" target="_blank">导出 Markdown</a>
            </div>
          </div>
        </section>
        <section class="section-grid columns-4" id="summaryMetrics"></section>
        <section class="split">
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">分级榜单</h2></div>
            <div class="table-card"><table id="rankingTable"></table></div>
          </div>
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">板块资金流</h2></div>
            <div class="table-card"><table id="sectorTable"></table></div>
          </div>
        </section>
        <section class="split">
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">风险与证据</h2></div>
            <div id="riskAlerts"></div>
            <h3>证据</h3>
            <pre id="evidenceBlock">等待加载</pre>
          </div>
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">数据链路状态</h2></div>
            <div id="monitorSummary"></div>
            <div class="section-grid" id="sourceCards"></div>
          </div>
        </section>
      `
    );
    document.getElementById("generateReport").addEventListener("click", generateTodayReport);
    document.getElementById("loadLatestReport").addEventListener("click", loadLatestReport);
    document.getElementById("loadMonitor").addEventListener("click", loadMonitor);
    document.getElementById("symbolsInput").addEventListener("input", syncExportLink);
    document.getElementById("marketStateSelect").addEventListener("change", syncExportLink);
    syncExportLink();
    try {
      await Promise.all([loadLatestReport(), loadMonitor()]);
    } catch (error) {
      setMessage("error", `初始化看板失败：${error.message}`);
      const summaryMetrics = document.getElementById("summaryMetrics");
      if (summaryMetrics) {
        summaryMetrics.innerHTML = `<article class="metric"><span class="muted">状态</span><strong>待重试</strong></article>`;
      }
    }
  }

  async function renderFundPage() {
    const initialSymbol = pagePath.split("/")[2] || defaultFundSymbol();
    shell(
      "单基金量化报告",
      "围绕单个基金代码输出评分、新闻、回测和证据链，便于研究与复盘。",
      `
        <section class="panel">
          <div class="toolbar">
            <div class="field">
              <label>基金代码</label>
              <input id="fundSymbolInput" value="${escapeHtml(initialSymbol)}" />
            </div>
            <div class="field">
              <label>操作</label>
              <button class="button" id="loadFundDetail" type="button">查询详情</button>
            </div>
          </div>
        </section>
        <section class="split">
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">评分与风险</h2></div>
            <pre id="scorecardBlock">等待加载</pre>
          </div>
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">新闻与回测</h2></div>
            <pre id="newsBlock">等待加载</pre>
            <pre id="backtestBlock" style="margin-top: 12px;">等待加载</pre>
          </div>
        </section>
        <section class="panel">
          <div class="panel-header"><h2 style="margin: 0;">证据来源</h2></div>
          <div id="fundEvidence"></div>
        </section>
      `
    );
    document.getElementById("loadFundDetail").addEventListener("click", async () => {
      const symbol = document.getElementById("fundSymbolInput").value.trim() || defaultFundSymbol();
      history.replaceState({}, "", `/fund/${encodeURIComponent(symbol)}`);
      await loadFundDetail(symbol);
    });
    await loadFundDetail(initialSymbol);
  }

  async function renderModelsPage() {
    shell(
      "模型配置中心",
      "统一管理 `url / apiKey / model` 三个核心字段，支持新增、更新、设默认、启停和连通性测试。",
      `
        <section class="split">
          <div class="panel">
            <div class="panel-header">
              <div>
                <h2 style="margin: 0;">模型配置列表</h2>
                <p class="muted">读取结果中的 apiKey 已脱敏。</p>
              </div>
              <button class="ghost-button" id="reloadModels" type="button">热更新</button>
            </div>
            <div class="table-card"><table id="modelsTable"></table></div>
          </div>
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">编辑配置</h2></div>
            <form id="modelForm">
              <div class="form-grid two">
                <div class="field"><label>名称</label><input id="modelName" required /></div>
                <div class="field"><label>模型名</label><input id="modelModel" required /></div>
              </div>
              <div class="field"><label>URL</label><input id="modelUrl" required /></div>
              <div class="field"><label>API Key（留空则保留原值）</label><input id="modelApiKey" /></div>
              <div class="form-grid two">
                <div class="field">
                  <label>启用</label>
                  <select id="modelEnabled"><option value="true">true</option><option value="false">false</option></select>
                </div>
                <div class="field">
                  <label>设为默认</label>
                  <select id="modelDefault"><option value="false">false</option><option value="true">true</option></select>
                </div>
              </div>
              <div class="actions" style="margin-top: 16px;">
                <button class="button" type="submit">保存配置</button>
                <button class="ghost-button" id="resetModelForm" type="button">新建</button>
              </div>
            </form>
            <div class="panel" style="margin-top: 16px; box-shadow: none;">
              <h3 style="margin-top: 0;">测试结果</h3>
              <pre id="modelTestResult">选择一条配置后可直接测试。</pre>
            </div>
          </div>
        </section>
      `
    );
    document.getElementById("reloadModels").addEventListener("click", async () => {
      await apiFetch("/api/settings/models/reload", { method: "POST" });
      setMessage("success", "模型配置已热更新");
      renderModelsPage();
    });
    document.getElementById("modelForm").addEventListener("submit", saveModel);
    document.getElementById("resetModelForm").addEventListener("click", () => {
      state.currentModelId = null;
      renderModelsPage();
    });
    await loadModels();
  }

  async function renderStrategiesPage() {
    shell(
      "策略配置中心",
      "支持参数、权重、启停、默认项、版本回滚、热更新，以及基于历史数据的离线 replay/tune。",
      `
        <section class="split">
          <div class="panel">
            <div class="panel-header">
              <div>
                <h2 style="margin: 0;">策略配置列表</h2>
                <p class="muted">当前日报链路会读取启用中的策略配置。</p>
              </div>
              <button class="ghost-button" id="reloadStrategies" type="button">热更新</button>
            </div>
            <div class="table-card"><table id="strategiesTable"></table></div>
          </div>
          <div class="panel">
            <div class="panel-header"><h2 style="margin: 0;">编辑策略</h2></div>
            <form id="strategyForm">
              <div class="form-grid two">
                <div class="field"><label>名称</label><input id="strategyName" required /></div>
                <div class="field">
                  <label>策略类型</label>
                  <select id="strategyType">
                    <option value="score_threshold">score_threshold</option>
                    <option value="score_momentum">score_momentum</option>
                  </select>
                </div>
              </div>
              <div class="form-grid two">
                <div class="field"><label>权重</label><input id="strategyWeight" type="number" step="0.1" value="1" /></div>
                <div class="field">
                  <label>启用</label>
                  <select id="strategyEnabled"><option value="true">true</option><option value="false">false</option></select>
                </div>
              </div>
              <div class="field"><label>参数 JSON</label><textarea id="strategyParams">{}</textarea></div>
              <div class="actions" style="margin-top: 16px;">
                <button class="button" type="submit">保存策略</button>
                <button class="ghost-button" id="resetStrategyForm" type="button">新建</button>
              </div>
            </form>
            <div class="panel" style="margin-top: 16px; box-shadow: none;">
              <h3 style="margin-top: 0;">离线调优结果</h3>
              <div class="toolbar">
                <div class="field"><label>Symbols</label><input id="tuneSymbols" value="014943,159870" /></div>
                <div class="field"><label>Market State</label><select id="tuneMarketState"><option value="neutral">neutral</option><option value="bull">bull</option><option value="bear">bear</option></select></div>
                <div class="field"><label>回放天数</label><input id="tuneLimit" type="number" value="120" /></div>
              </div>
              <div class="actions" style="margin-top: 14px;">
                <button class="button" id="runTune" type="button">运行 Replay / Tune</button>
              </div>
              <pre id="tuneResult">选择一条策略后运行。</pre>
            </div>
          </div>
        </section>
      `
    );
    document.getElementById("reloadStrategies").addEventListener("click", async () => {
      await apiFetch("/api/settings/strategies/reload", { method: "POST" });
      setMessage("success", "策略配置已热更新");
      renderStrategiesPage();
    });
    document.getElementById("strategyForm").addEventListener("submit", saveStrategy);
    document.getElementById("resetStrategyForm").addEventListener("click", () => {
      state.currentStrategyId = null;
      renderStrategiesPage();
    });
    document.getElementById("runTune").addEventListener("click", runTune);
    await loadStrategies();
  }

  function renderNotFound() {
    shell("未找到页面", "当前路由没有对应页面。", `<section class="panel"><p>请从导航返回可用页面。</p></section>`);
  }

  async function loadLatestReport() {
    const payload = await apiFetch("/api/report/daily/latest");
    renderReport(payload);
  }

  async function generateTodayReport() {
    try {
      const symbols = document.getElementById("symbolsInput").value;
      const marketState = document.getElementById("marketStateSelect").value;
      const payload = await apiFetch("/api/report/daily/generate", {
        method: "POST",
        body: JSON.stringify({ symbols, market_state: marketState }),
      });
      setMessage("success", `报告已生成：${payload.report_id}`);
      renderDashboard();
      renderReport(payload);
      await loadMonitor();
    } catch (error) {
      setMessage("error", `生成报告失败：${error.message}`);
      renderDashboard();
    }
  }

  function renderReport(payload) {
    const summary = payload.market_summary || {};
    const metrics = [
      { label: "覆盖标的", value: summary.symbol_count || 0 },
      { label: "平均评分", value: summary.avg_score || 0 },
      { label: "多头占比", value: summary.bullish_ratio || 0 },
      { label: "低置信占比", value: summary.low_confidence_ratio || 0 },
    ];
    const summaryMetrics = document.getElementById("summaryMetrics");
    summaryMetrics.innerHTML = metrics
      .map((item) => `<article class="metric"><span class="muted">${item.label}</span><strong>${item.value}</strong></article>`)
      .join("");
    const ranking = payload.ranking || [];
    document.getElementById("rankingTable").innerHTML = `
      <thead><tr><th>Symbol</th><th>Name</th><th>Tier</th><th>Score</th><th>Conf</th><th>Action</th><th>Reason</th><th>Risk</th></tr></thead>
      <tbody>
        ${ranking
          .map(
            (row) => `<tr>
              <td><a href="/fund/${encodeURIComponent(row.symbol)}">${escapeHtml(row.symbol)}</a></td>
              <td>${escapeHtml(row.name)}</td>
              <td>${escapeHtml(row.tier)}</td>
              <td>${number(row.total_score)}</td>
              <td>${number(row.confidence)}</td>
              <td>${escapeHtml(row.tactical_action)}</td>
              <td>${escapeHtml(row.tactical_reason)}</td>
              <td>${escapeHtml((row.risk_tags || []).join(", ") || "-")}</td>
            </tr>`
          )
          .join("")}
      </tbody>
    `;
    const sectors = payload.sector_ranking || [];
    document.getElementById("sectorTable").innerHTML = `
      <thead><tr><th>Sector</th><th>Change%</th><th>Inflow</th><th>Ratio</th><th>Top</th></tr></thead>
      <tbody>
        ${sectors
          .map(
            (row) => `<tr>
              <td>${escapeHtml(row.sector)}</td>
              <td>${number(row.change_pct)}</td>
              <td>${number(row.main_net_inflow)}</td>
              <td>${number(row.main_inflow_ratio)}</td>
              <td>${escapeHtml(row.top_stock || "-")}</td>
            </tr>`
          )
          .join("")}
      </tbody>
    `;
    document.getElementById("riskAlerts").innerHTML = (payload.risk_alerts || [])
      .map((item) => `<div class="badge badge-warning" style="margin: 0 8px 8px 0;">${escapeHtml(item)}</div>`)
      .join("") || '<p class="muted">当前无风险标签。</p>';
    document.getElementById("evidenceBlock").textContent = JSON.stringify(payload.evidence || {}, null, 2);
  }

  async function loadMonitor() {
    const payload = await apiFetch("/api/monitor/data-sources");
    document.getElementById("monitorSummary").innerHTML = `
      <div class="status-row">
        ${statusBadge(payload.overall_status)}
        <span class="muted">数据源 ${payload.source_count}</span>
        <span class="muted">审计事件 ${payload.audit_event_count}</span>
      </div>
      <div class="stack" style="margin-top: 10px;">
        ${(payload.alerts || []).map((alert) => `<span class="badge ${alert.level === "critical" ? "badge-critical" : "badge-warning"}">${escapeHtml(alert.source)}: ${escapeHtml(alert.message)}</span>`).join("")}
      </div>
    `;
    document.getElementById("sourceCards").innerHTML = (payload.sources || [])
      .map(
        (source) => `<article class="status-card">
          <div class="panel-header">
            <strong>${escapeHtml(source.source)}</strong>
            ${statusBadge(source.circuit_open_until ? "warning" : "healthy")}
          </div>
          <p class="muted">enabled=${escapeHtml(String(source.enabled))}</p>
          <p>失败数：${number(source.failure_count)} / 连续失败：${number(source.consecutive_failures)}</p>
          <p>平均延迟：${number(source.avg_latency_ms)}</p>
          <p>熔断至：${escapeHtml(source.circuit_open_until || "-")}</p>
          <p>缓存命中：${escapeHtml(String((source.cache_metrics || {}).hit_count || 0))}</p>
        </article>`
      )
      .join("");
  }

  async function loadFundDetail(symbol) {
    try {
      const payload = await apiFetch(`/api/report/fund-detail?symbol=${encodeURIComponent(symbol)}`);
      document.getElementById("scorecardBlock").textContent = JSON.stringify(payload.detail.scorecard || {}, null, 2);
      document.getElementById("newsBlock").textContent = JSON.stringify(payload.detail.news_summary || {}, null, 2);
      document.getElementById("backtestBlock").textContent = JSON.stringify(payload.detail.backtest_summary || {}, null, 2);
      document.getElementById("fundEvidence").innerHTML = `
        <div class="stack">
          ${(payload.detail.data_source_refs || []).map((ref) => `<span class="badge">${escapeHtml(ref)}</span>`).join("")}
        </div>
        <p class="muted" style="margin-top: 12px;">source_time_utc: ${escapeHtml(payload.detail.source_time_utc || "-")}</p>
      `;
    } catch (error) {
      document.getElementById("scorecardBlock").textContent = `加载失败：${error.message}`;
      document.getElementById("newsBlock").textContent = "";
      document.getElementById("backtestBlock").textContent = "";
      document.getElementById("fundEvidence").innerHTML = "";
    }
  }

  async function loadModels() {
    const payload = await apiFetch("/api/settings/models");
    const rows = payload.items || [];
    document.getElementById("modelsTable").innerHTML = `
      <thead><tr><th>Name</th><th>URL</th><th>Model</th><th>Key</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>
        ${rows
          .map(
            (row) => `<tr>
              <td>${escapeHtml(row.name)} ${row.is_default ? '<span class="badge">default</span>' : ""}</td>
              <td>${escapeHtml(row.url)}</td>
              <td>${escapeHtml(row.model)}</td>
              <td>${escapeHtml(row.apiKey || "-")}</td>
              <td>${row.enabled ? '<span class="badge badge-ok">enabled</span>' : '<span class="badge badge-warning">disabled</span>'}</td>
              <td class="actions">
                <button class="ghost-button" data-model-action="edit" data-model-id="${escapeHtml(row.id)}">编辑</button>
                <button class="ghost-button" data-model-action="default" data-model-id="${escapeHtml(row.id)}">设默认</button>
                <button class="ghost-button" data-model-action="toggle" data-model-enabled="${row.enabled}" data-model-id="${escapeHtml(row.id)}">${row.enabled ? "停用" : "启用"}</button>
                <button class="ghost-button" data-model-action="test" data-model-id="${escapeHtml(row.id)}">测试</button>
              </td>
            </tr>`
          )
          .join("")}
      </tbody>
    `;
    document.querySelectorAll("[data-model-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.modelAction;
        const modelId = button.dataset.modelId;
        if (action === "edit") {
          const item = rows.find((entry) => entry.id === modelId);
          if (!item) return;
          state.currentModelId = item.id;
          document.getElementById("modelName").value = item.name;
          document.getElementById("modelModel").value = item.model;
          document.getElementById("modelUrl").value = item.url;
          document.getElementById("modelApiKey").value = "";
          document.getElementById("modelEnabled").value = String(item.enabled);
          document.getElementById("modelDefault").value = String(item.is_default);
          document.getElementById("modelTestResult").textContent = JSON.stringify(item, null, 2);
          return;
        }
        if (action === "default") {
          await apiFetch(`/api/settings/models/${encodeURIComponent(modelId)}/default`, { method: "POST", body: "{}" });
          setMessage("success", `已将 ${modelId} 设为默认模型`);
          renderModelsPage();
          return;
        }
        if (action === "toggle") {
          const enabled = button.dataset.modelEnabled !== "true";
          await apiFetch(`/api/settings/models/${encodeURIComponent(modelId)}/enabled`, {
            method: "POST",
            body: JSON.stringify({ enabled }),
          });
          setMessage("success", `${modelId} 状态已更新`);
          renderModelsPage();
          return;
        }
        if (action === "test") {
          const result = await apiFetch(`/api/settings/models/${encodeURIComponent(modelId)}/test`, { method: "POST", body: "{}" });
          document.getElementById("modelTestResult").textContent = JSON.stringify(result, null, 2);
        }
      });
    });
  }

  async function saveModel(event) {
    event.preventDefault();
    const payload = {
      name: document.getElementById("modelName").value.trim(),
      model: document.getElementById("modelModel").value.trim(),
      url: document.getElementById("modelUrl").value.trim(),
      apiKey: document.getElementById("modelApiKey").value.trim(),
      enabled: document.getElementById("modelEnabled").value === "true",
      is_default: document.getElementById("modelDefault").value === "true",
    };
    try {
      if (state.currentModelId) {
        await apiFetch(`/api/settings/models/${encodeURIComponent(state.currentModelId)}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setMessage("success", `模型 ${state.currentModelId} 已更新`);
      } else {
        await apiFetch("/api/settings/models", { method: "POST", body: JSON.stringify(payload) });
        setMessage("success", `模型 ${payload.name} 已新增`);
      }
      renderModelsPage();
    } catch (error) {
      setMessage("error", `保存模型失败：${error.message}`);
      renderModelsPage();
    }
  }

  async function loadStrategies() {
    const payload = await apiFetch("/api/settings/strategies");
    const rows = payload.items || [];
    document.getElementById("strategiesTable").innerHTML = `
      <thead><tr><th>Name</th><th>Type</th><th>Version</th><th>Weight</th><th>Status</th><th>Actions</th></tr></thead>
      <tbody>
        ${rows
          .map(
            (row) => `<tr>
              <td>${escapeHtml(row.name)} ${row.is_default ? '<span class="badge">default</span>' : ""}</td>
              <td>${escapeHtml(row.strategy_type)}</td>
              <td>${escapeHtml(row.profile_version)}</td>
              <td>${number(row.weight)}</td>
              <td>${row.enabled ? '<span class="badge badge-ok">enabled</span>' : '<span class="badge badge-warning">disabled</span>'}</td>
              <td class="actions">
                <button class="ghost-button" data-strategy-action="edit" data-strategy-id="${escapeHtml(row.id)}">编辑</button>
                <button class="ghost-button" data-strategy-action="default" data-strategy-id="${escapeHtml(row.id)}">设默认</button>
                <button class="ghost-button" data-strategy-action="toggle" data-strategy-enabled="${row.enabled}" data-strategy-id="${escapeHtml(row.id)}">${row.enabled ? "停用" : "启用"}</button>
                <button class="ghost-button" data-strategy-action="rollback" data-strategy-version="${escapeHtml(((row.history || [])[0] || {}).profile_version || "")}" data-strategy-id="${escapeHtml(row.id)}">回滚最新历史</button>
              </td>
            </tr>`
          )
          .join("")}
      </tbody>
    `;
    document.querySelectorAll("[data-strategy-action]").forEach((button) => {
      button.addEventListener("click", async () => {
        const action = button.dataset.strategyAction;
        const strategyId = button.dataset.strategyId;
        if (action === "edit") {
          const item = rows.find((entry) => entry.id === strategyId);
          if (!item) return;
          state.currentStrategyId = item.id;
          document.getElementById("strategyName").value = item.name;
          document.getElementById("strategyType").value = item.strategy_type;
          document.getElementById("strategyWeight").value = item.weight;
          document.getElementById("strategyEnabled").value = String(item.enabled);
          document.getElementById("strategyParams").value = JSON.stringify(item.params || {}, null, 2);
          document.getElementById("tuneResult").textContent = JSON.stringify(item, null, 2);
          return;
        }
        if (action === "default") {
          await apiFetch(`/api/settings/strategies/${encodeURIComponent(strategyId)}/default`, { method: "POST", body: "{}" });
          setMessage("success", `已将 ${strategyId} 设为默认策略`);
          renderStrategiesPage();
          return;
        }
        if (action === "toggle") {
          const enabled = button.dataset.strategyEnabled !== "true";
          await apiFetch(`/api/settings/strategies/${encodeURIComponent(strategyId)}/enabled`, {
            method: "POST",
            body: JSON.stringify({ enabled }),
          });
          setMessage("success", `${strategyId} 状态已更新`);
          renderStrategiesPage();
          return;
        }
        if (action === "rollback") {
          const version = button.dataset.strategyVersion;
          if (!version) {
            setMessage("error", `${strategyId} 暂无可回滚历史版本`);
            renderStrategiesPage();
            return;
          }
          await apiFetch(`/api/settings/strategies/${encodeURIComponent(strategyId)}/rollback`, {
            method: "POST",
            body: JSON.stringify({ version }),
          });
          setMessage("success", `${strategyId} 已回滚到历史快照`);
          renderStrategiesPage();
        }
      });
    });
  }

  async function saveStrategy(event) {
    event.preventDefault();
    let params = {};
    try {
      params = JSON.parse(document.getElementById("strategyParams").value || "{}");
    } catch (error) {
      setMessage("error", `参数 JSON 解析失败：${error.message}`);
      renderStrategiesPage();
      return;
    }
    const payload = {
      name: document.getElementById("strategyName").value.trim(),
      strategy_type: document.getElementById("strategyType").value,
      weight: Number(document.getElementById("strategyWeight").value || 1),
      enabled: document.getElementById("strategyEnabled").value === "true",
      params,
    };
    try {
      if (state.currentStrategyId) {
        await apiFetch(`/api/settings/strategies/${encodeURIComponent(state.currentStrategyId)}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        });
        setMessage("success", `策略 ${state.currentStrategyId} 已更新`);
      } else {
        await apiFetch("/api/settings/strategies", { method: "POST", body: JSON.stringify(payload) });
        setMessage("success", `策略 ${payload.name} 已新增`);
      }
      renderStrategiesPage();
    } catch (error) {
      setMessage("error", `保存策略失败：${error.message}`);
      renderStrategiesPage();
    }
  }

  async function runTune() {
    if (!state.currentStrategyId) {
      setMessage("error", "请先选择一条策略再运行调优");
      renderStrategiesPage();
      return;
    }
    const symbols = document.getElementById("tuneSymbols").value;
    const marketState = document.getElementById("tuneMarketState").value;
    const limit = Number(document.getElementById("tuneLimit").value || 120);
    try {
      const result = await apiFetch(`/api/settings/strategies/${encodeURIComponent(state.currentStrategyId)}/replay-tune`, {
        method: "POST",
        body: JSON.stringify({ symbols, market_state: marketState, limit, persist: true }),
      });
      document.getElementById("tuneResult").textContent = JSON.stringify(result, null, 2);
      setMessage("success", `已完成策略 ${state.currentStrategyId} 的离线调优并写回新版本`);
      renderStrategiesPage();
    } catch (error) {
      setMessage("error", `离线调优失败：${error.message}`);
      renderStrategiesPage();
    }
  }

  async function logout() {
    await apiFetch("/api/auth/logout", { method: "POST", body: "{}" });
    window.location.replace("/login");
  }

  function syncExportLink() {
    const symbols = document.getElementById("symbolsInput").value;
    const marketState = document.getElementById("marketStateSelect").value;
    document.getElementById("exportReport").href = `/api/report/export?symbols=${encodeURIComponent(symbols)}&market_state=${encodeURIComponent(marketState)}&format=md`;
  }

  function setMessage(type, text) {
    state.message = { type, text };
  }

  function messageHtml(type, text) {
    return `<div class="message ${type}">${escapeHtml(text)}</div>`;
  }

  function statusBadge(status) {
    if (status === "critical") return '<span class="badge badge-critical">critical</span>';
    if (status === "warning") return '<span class="badge badge-warning">warning</span>';
    return '<span class="badge badge-ok">healthy</span>';
  }

  function defaultFundSymbol() {
    return "014943";
  }

  function number(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
    return Number(value).toFixed(2);
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
})();
