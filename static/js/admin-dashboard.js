(() => {
  "use strict";

  const config = window.ARModelDashboard || {};
  const loading = document.getElementById("dashboard-loading");
  const error = document.getElementById("dashboard-error");
  const errorMessage = document.getElementById("dashboard-error-message");
  const content = document.getElementById("dashboard-content");
  const retry = document.getElementById("dashboard-retry");

  const formatInteger = (value) => new Intl.NumberFormat().format(Number(value || 0));
  const formatBytes = (bytes) => {
    const value = Number(bytes || 0);
    if (!value) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const unitIndex = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / (1024 ** unitIndex)).toFixed(unitIndex > 1 ? 2 : 0)} ${units[unitIndex]}`;
  };
  const label = (value) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

  function addMetric(container, title, value, note = "") {
    const card = document.createElement("article");
    card.className = "dashboard-metric";
    const titleNode = document.createElement("span");
    titleNode.textContent = title;
    const valueNode = document.createElement("strong");
    valueNode.textContent = value;
    card.append(titleNode, valueNode);
    if (note) {
      const noteNode = document.createElement("small");
      noteNode.textContent = note;
      card.append(noteNode);
    }
    container.append(card);
  }

  function renderOverview(data) {
    const cards = document.getElementById("overview-cards");
    cards.replaceChildren();
    [
      ["Models", data.content.models],
      ["Projects", data.content.projects],
      ["Site settings", data.content.site_settings],
      ["Sliders", data.content.sliders],
      ["Tracked asset URLs", data.assets.tracked_urls],
      ["Cloudflare R2 URLs", data.assets.r2_urls],
      ["Supabase URLs", data.assets.supabase_urls],
      ["Unknown asset sizes", data.storage.unknown_size_count],
    ].forEach(([title, value]) => addMetric(cards, title, formatInteger(value)));

    const strip = document.getElementById("runtime-strip");
    strip.replaceChildren();
    [
      `Runtime source: ${data.runtime.source}`,
      `Asset storage: ${data.runtime.asset_storage}`,
      `Admin mode: ${data.runtime.admin_mode}`,
      "Inventory: tracked JSON URLs only",
    ].forEach((text) => {
      const item = document.createElement("span");
      item.className = "dashboard-runtime-item";
      item.textContent = text;
      strip.append(item);
    });
  }

  function renderStorage(storage) {
    document.getElementById("storage-used").textContent = formatBytes(storage.known_size_bytes);
    document.getElementById("storage-remaining").textContent = formatBytes(storage.remaining_bytes);
    const progress = document.getElementById("storage-progress");
    progress.setAttribute("aria-valuenow", String(storage.usage_percent));
    document.getElementById("storage-progress-bar").style.width = `${storage.usage_percent}%`;
    const source = storage.soft_limit_source === "default" ? "default" : "configured";
    document.getElementById("storage-note").textContent =
      `${formatInteger(storage.reachable_count)} of ${formatInteger(storage.checked_count)} tracked R2 assets reachable. ` +
      `${formatInteger(storage.unknown_size_count)} sizes unknown. Remaining is calculated against the ${source} ` +
      `${storage.soft_limit_gb} GB configured soft limit, not an actual Cloudflare quota.`;

    const chart = document.getElementById("storage-chart");
    chart.replaceChildren();
    const maxSize = Math.max(...storage.breakdown.map((item) => item.size_bytes), 1);
    storage.breakdown.forEach((item) => {
      const row = document.createElement("div");
      row.className = "dashboard-chart-row";
      const name = document.createElement("span");
      name.textContent = label(item.category);
      const track = document.createElement("div");
      track.className = "dashboard-chart-track";
      const bar = document.createElement("span");
      bar.style.width = `${item.size_bytes / maxSize * 100}%`;
      track.append(bar);
      const value = document.createElement("span");
      value.textContent = `${formatBytes(item.size_bytes)} · ${item.asset_count}`;
      row.append(name, track, value);
      chart.append(row);
    });
  }

  function renderHealth(health) {
    const names = {
      json_data_integrity: "JSON data integrity",
      r2_asset_reachability: "R2 asset reachability",
      supabase_url_cleanliness: "Supabase URL cleanliness",
      admin_read_only_protection: "Admin read-only protection",
      public_runtime_status: "Public runtime status",
    };
    const list = document.getElementById("health-list");
    list.replaceChildren();
    Object.entries(health).forEach(([key, item]) => {
      const row = document.createElement("div");
      row.className = `dashboard-health-item dashboard-health-item--${item.status}`;
      const name = document.createElement("strong");
      name.textContent = names[key] || label(key);
      const track = document.createElement("div");
      track.className = "dashboard-health-bar";
      const bar = document.createElement("span");
      bar.style.width = `${Math.max(0, Math.min(100, item.score))}%`;
      track.append(bar);
      const score = document.createElement("span");
      score.className = "dashboard-health-score";
      score.textContent = `${item.score}%`;
      row.append(name, track, score);
      list.append(row);
    });
  }

  function render(data) {
    renderOverview(data);
    renderStorage(data.storage);
    renderHealth(data.health);
    document.getElementById("analytics-disabled").querySelector("strong").textContent =
      data.analytics.message || "Analytics provider is not configured.";
    document.getElementById("dashboard-generated").textContent =
      `Generated ${new Date(data.generated_at).toLocaleString()}`;
  }

  async function loadDashboard() {
    loading.hidden = false;
    error.hidden = true;
    content.hidden = true;
    try {
      const response = await fetch(config.summaryUrl, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || `HTTP ${response.status}`);
      render(data);
      loading.hidden = true;
      content.hidden = false;
    } catch (loadError) {
      loading.hidden = true;
      error.hidden = false;
      errorMessage.textContent = loadError.message || "Try again.";
    }
  }

  retry.addEventListener("click", loadDashboard);
  loadDashboard();
})();
