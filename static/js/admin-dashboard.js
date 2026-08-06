(() => {
  "use strict";

  const config = window.ARModelDashboard || {};
  const loading = document.getElementById("dashboard-loading");
  const error = document.getElementById("dashboard-error");
  const errorMessage = document.getElementById("dashboard-error-message");
  const content = document.getElementById("dashboard-content");
  const retry = document.getElementById("dashboard-retry");
  const dateInput = document.getElementById("analytics-date");
  const todayButton = document.getElementById("analytics-today");
  const dateLabel = document.getElementById("analytics-date-label");
  const dateStatus = document.getElementById("analytics-date-status");
  let requestController = null;
  let activeTrendRange = "daily_7d";

  const formatInteger = (value) => new Intl.NumberFormat().format(Number(value || 0));
  const formatBytes = (bytes) => {
    const value = Number(bytes || 0);
    if (!value) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const unitIndex = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
    return `${(value / (1024 ** unitIndex)).toFixed(unitIndex > 1 ? 2 : 0)} ${units[unitIndex]}`;
  };
  const categoryLabels = {
    glb_models: "โมเดล 3D / GLB",
    thumbnails: "ภาพปกโมเดล",
    narration_audio: "ไฟล์เสียงบรรยาย",
    project_images: "ภาพโครงการ",
    site_settings_images: "ภาพตั้งค่าเว็บไซต์",
    slider_images: "ภาพสไลด์",
    other: "ไฟล์อื่น ๆ",
  };

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
      ["โมเดล 3D", data.content.models],
      ["โครงการ", data.content.projects],
      ["รายการตั้งค่าเว็บไซต์", data.content.site_settings],
      ["สไลด์", data.content.sliders],
      ["URL ไฟล์ที่ติดตาม", data.assets.tracked_urls],
      ["URL บน Cloudflare R2", data.assets.r2_urls],
      ["URL ของ Supabase", data.assets.supabase_urls],
      ["ไฟล์ที่ไม่ทราบขนาด", data.storage.unknown_size_count],
    ].forEach(([title, value]) => addMetric(cards, title, formatInteger(value)));

    const strip = document.getElementById("runtime-strip");
    strip.replaceChildren();
    [
      `แหล่งข้อมูล Runtime: ${data.runtime.source}`,
      `พื้นที่จัดเก็บไฟล์: ${data.runtime.asset_storage}`,
      `โหมดแอดมิน: ${data.runtime.admin_mode === "read-only" ? "อ่านอย่างเดียว" : "พัฒนาในเครื่อง"}`,
      "รายการไฟล์: เฉพาะ URL ใน JSON ที่ระบบติดตาม",
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
    const source = storage.soft_limit_source === "default" ? "ค่าเริ่มต้น" : "ค่าที่กำหนด";
    document.getElementById("storage-note").textContent =
      `เข้าถึงไฟล์ R2 ได้ ${formatInteger(storage.reachable_count)} จาก ${formatInteger(storage.checked_count)} ไฟล์ ` +
      `และมี ${formatInteger(storage.unknown_size_count)} ไฟล์ที่ไม่ทราบขนาด พื้นที่คงเหลือคำนวณจากขีดจำกัด${source} ` +
      `${storage.soft_limit_gb} GB ไม่ใช่โควตาจริงของ Cloudflare`;

    const chart = document.getElementById("storage-chart");
    chart.replaceChildren();
    const maxSize = Math.max(...storage.breakdown.map((item) => item.size_bytes), 1);
    storage.breakdown.forEach((item) => {
      const row = document.createElement("div");
      row.className = "dashboard-chart-row";
      const name = document.createElement("span");
      name.textContent = categoryLabels[item.category] || item.category;
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
      json_data_integrity: "ความถูกต้องของข้อมูล JSON",
      r2_asset_reachability: "การเข้าถึงไฟล์ R2",
      supabase_url_cleanliness: "การตรวจว่าไม่มี URL ของ Supabase",
      admin_read_only_protection: "การป้องกันโหมดอ่านอย่างเดียวของแอดมิน",
      public_runtime_status: "สถานะ Runtime ฝั่ง Public",
    };
    const list = document.getElementById("health-list");
    list.replaceChildren();
    Object.entries(health).forEach(([key, item]) => {
      const row = document.createElement("div");
      row.className = `dashboard-health-item dashboard-health-item--${item.status}`;
      const name = document.createElement("strong");
      name.textContent = names[key] || key;
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

  function renderMiniChart(container, items, emptyText = "ยังไม่มีข้อมูล") {
    if (container.classList.contains("dashboard-empty")) {
      container.classList.remove("dashboard-empty");
      container.classList.add("dashboard-chart");
    }
    container.replaceChildren();
    if (!items || !items.length) {
      const empty = document.createElement("div");
      empty.className = "dashboard-empty";
      empty.textContent = emptyText;
      container.append(empty);
      return;
    }
    const maxValue = Math.max(...items.map((item) => Number(item.value || item.visitors || 0)), 1);
    items.forEach((item) => {
      const valueNumber = Number(item.value || item.visitors || 0);
      const row = document.createElement("div");
      row.className = "dashboard-chart-row";
      const name = document.createElement("span");
      name.textContent = item.label || item.date || "Unknown";
      const track = document.createElement("div");
      track.className = "dashboard-chart-track";
      const bar = document.createElement("span");
      bar.style.width = `${Math.max(4, valueNumber / maxValue * 100)}%`;
      track.append(bar);
      const value = document.createElement("span");
      value.textContent = formatInteger(valueNumber);
      row.append(name, track, value);
      container.append(row);
    });
  }

  function formatTrendLabel(item, rangeKey) {
    if (rangeKey === "hourly_24h") return item.label;
    if (rangeKey === "monthly_12m") {
      const date = new Date(`${item.label}-01T00:00:00`);
      return date.toLocaleDateString("th-TH", { month: "short", year: "2-digit" });
    }
    const date = new Date(`${item.label}T00:00:00`);
    return date.toLocaleDateString("th-TH", { day: "numeric", month: "short" });
  }

  function renderTrendGraph(container, analytics) {
    const ranges = analytics.trend_ranges || {
      daily_7d: (analytics.trend || []).slice(-7).map((item) => ({
        label: item.date,
        visitors: item.visitors,
        pageviews: item.pageviews,
      })),
      default_range: "daily_7d",
    };
    const rangeOptions = [
      ["hourly_24h", "24 ชม."],
      ["daily_7d", "7 วัน"],
      ["daily_30d", "30 วัน"],
      ["monthly_12m", "12 เดือน"],
    ].filter(([key]) => Array.isArray(ranges[key]));
    let activeRange = activeTrendRange || ranges.default_range || "daily_7d";
    if (!ranges[activeRange]) activeRange = rangeOptions[0]?.[0] || "daily_7d";

    container.replaceChildren();
    container.classList.add("dashboard-trend");
    container.classList.remove("dashboard-chart-placeholder");

    const controls = document.createElement("div");
    controls.className = "dashboard-trend-controls";
    const viewport = document.createElement("div");
    viewport.className = "dashboard-trend-viewport";
    const summary = document.createElement("div");
    summary.className = "dashboard-trend-summary";

    function draw(rangeKey) {
      activeRange = rangeKey;
      activeTrendRange = rangeKey;
      controls.querySelectorAll("button").forEach((button) => {
        button.classList.toggle("active", button.dataset.range === rangeKey);
      });

      const items = ranges[rangeKey] || [];
      viewport.replaceChildren();
      if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "dashboard-empty";
        empty.textContent = "ยังไม่มีข้อมูลสำหรับช่วงเวลานี้";
        viewport.append(empty);
        summary.textContent = "";
        return;
      }

      const width = Math.max(680, items.length * 88);
      const height = 230;
      const pad = { top: 24, right: 34, bottom: 48, left: 46 };
      const plotWidth = width - pad.left - pad.right;
      const plotHeight = height - pad.top - pad.bottom;
      const maxVisitors = Math.max(...items.map((item) => Number(item.visitors || 0)), 1);
      const maxPageviews = Math.max(...items.map((item) => Number(item.pageviews || 0)), 1);
      const maxValue = Math.max(maxVisitors, maxPageviews, 1);
      const xFor = (index) => pad.left + (items.length === 1 ? plotWidth : (index / (items.length - 1)) * plotWidth);
      const yFor = (value) => pad.top + plotHeight - (Number(value || 0) / maxValue) * plotHeight;
      const points = items.map((item, index) => `${xFor(index)},${yFor(item.visitors)}`).join(" ");
      const areaPoints = `${pad.left},${pad.top + plotHeight} ${points} ${pad.left + plotWidth},${pad.top + plotHeight}`;
      const gridLines = [0, .25, .5, .75, 1].map((ratio) => {
        const y = pad.top + plotHeight - ratio * plotHeight;
        const value = Math.round(maxValue * ratio);
        return `<line x1="${pad.left}" y1="${y}" x2="${pad.left + plotWidth}" y2="${y}" class="dashboard-trend-grid"></line><text x="${pad.left - 10}" y="${y + 4}" class="dashboard-trend-axis" text-anchor="end">${value}</text>`;
      }).join("");
      const labels = items.map((item, index) => {
        const x = xFor(index);
        return `<text x="${x}" y="${height - 17}" class="dashboard-trend-label" text-anchor="middle">${formatTrendLabel(item, rangeKey)}</text>`;
      }).join("");
      const bars = items.map((item, index) => {
        const x = xFor(index) - 11;
        const y = yFor(item.pageviews);
        const barHeight = pad.top + plotHeight - y;
        return `<rect x="${x}" y="${y}" width="22" height="${barHeight}" rx="5" class="dashboard-trend-bar"><title>${formatTrendLabel(item, rangeKey)} · pageviews ${formatInteger(item.pageviews)}</title></rect>`;
      }).join("");
      const dots = items.map((item, index) => {
        const label = formatTrendLabel(item, rangeKey);
        return `<circle cx="${xFor(index)}" cy="${yFor(item.visitors)}" r="4.5" class="dashboard-trend-dot"><title>${label} · visitors ${formatInteger(item.visitors)}</title></circle>`;
      }).join("");

      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
      svg.setAttribute("width", String(width));
      svg.setAttribute("height", String(height));
      svg.setAttribute("role", "img");
      svg.setAttribute("aria-label", "กราฟแนวโน้มผู้เข้าชม");
      svg.innerHTML = `
        ${gridLines}
        ${bars}
        <polygon points="${areaPoints}" class="dashboard-trend-area"></polygon>
        <polyline points="${points}" class="dashboard-trend-line"></polyline>
        ${dots}
        ${labels}
      `;
      viewport.append(svg);
      viewport.scrollLeft = viewport.scrollWidth;

      const totalVisitors = items.reduce((sum, item) => sum + Number(item.visitors || 0), 0);
      const totalPageviews = items.reduce((sum, item) => sum + Number(item.pageviews || 0), 0);
      summary.textContent = `ช่วงนี้รวมผู้เข้าชม ${formatInteger(totalVisitors)} · เปิดหน้า ${formatInteger(totalPageviews)} ครั้ง`;
    }

    rangeOptions.forEach(([key, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.range = key;
      button.textContent = label;
      button.addEventListener("click", () => draw(key));
      controls.append(button);
    });

    container.append(controls, viewport, summary);
    draw(activeRange);
  }

  function renderAnalytics(analytics) {
    const data = analytics || {};
    const disabled = document.getElementById("analytics-disabled");
    const metrics = document.querySelector(".dashboard-analytics-metrics");
    const badge = document.querySelector("[aria-labelledby='analytics-title'] .dashboard-badge");
    const trend = document.querySelector(".dashboard-panel--wide .dashboard-chart-placeholder, .dashboard-panel--wide .dashboard-trend");
    const panels = document.querySelectorAll(".dashboard-analytics-grid .dashboard-panel:not(.dashboard-panel--wide) .dashboard-chart, .dashboard-analytics-grid .dashboard-panel:not(.dashboard-panel--wide) .dashboard-empty");

    if (disabled) {
      const title = disabled.querySelector("strong");
      const description = disabled.querySelector("span");
      if (title) title.textContent = data.message || "Analytics is ready.";
      if (description) {
        description.textContent = data.enabled
          ? `Provider: ${data.provider || "local"} · Events: ${formatInteger(data.metrics?.total_events || 0)}`
          : "Visit public pages to start collecting data.";
      }
      disabled.classList.toggle("dashboard-disabled--active", Boolean(data.enabled));
    }

    if (badge) {
      badge.textContent = data.enabled ? (data.provider || "active") : "ready";
      badge.classList.toggle("dashboard-badge--disabled", !data.enabled);
    }

    if (metrics) {
      metrics.classList.toggle("dashboard-analytics-metrics--active", Boolean(data.enabled));
      metrics.replaceChildren();
      const values = data.metrics || {};
      [
        [data.is_today ? "ผู้เข้าชมวันนี้" : "ผู้เข้าชมวันที่เลือก", values.visitors_today],
        [data.is_today ? "จำนวนการเปิดหน้าเว็บวันนี้" : "จำนวนการเปิดหน้าวันที่เลือก", values.pageviews_today],
        ["ผู้เข้าชมย้อนหลัง 7 วัน สิ้นสุดวันที่เลือก", values.visitors_7d],
        ["ผู้เข้าชมย้อนหลัง 30 วัน สิ้นสุดวันที่เลือก", values.visitors_30d],
      ].forEach(([title, value]) => addMetric(metrics, title, formatInteger(value)));
    }

    const scope = data.selected_date_label ? `ข้อมูลประจำวันที่ ${data.selected_date_label}` : "ข้อมูลวันที่เลือก";
    document.querySelectorAll("[data-analytics-heading]").forEach((heading) => {
      const base = {
        countries: "ประเทศที่มีผู้เข้าชมสูงสุด",
        referrers: "แหล่งที่มาของผู้เข้าชม",
        pages: "หน้าที่มีผู้เข้าชมสูงสุด",
      }[heading.dataset.analyticsHeading] || heading.textContent;
      heading.textContent = `${base} · ${scope}`;
    });

    if (trend) {
      trend.classList.toggle("dashboard-chart-placeholder--active", Boolean(data.enabled));
      renderTrendGraph(trend, data);
    }

    if (panels.length >= 3) {
      renderMiniChart(panels[0], data.top_countries, "ยังไม่มีข้อมูลประเทศ");
      renderMiniChart(panels[1], data.top_referrers, "ยังไม่มีข้อมูลแหล่งที่มา");
      renderMiniChart(panels[2], data.top_pages, "ยังไม่มีข้อมูลหน้าเว็บ");
    }
  }

  function render(data) {
    renderOverview(data);
    renderStorage(data.storage);
    renderHealth(data.health);
    renderAnalytics(data.analytics);
    if (data.analytics?.selected_date && dateInput) {
      dateInput.value = data.analytics.selected_date;
      dateLabel.textContent = `ข้อมูลประจำวันที่ ${data.analytics.selected_date_label}`;
    }
    document.getElementById("dashboard-generated").textContent =
      `สร้างข้อมูลเมื่อ ${new Date(data.generated_at).toLocaleString("th-TH")}`;
  }

  function syncDateUrl(selectedDate) {
    const url = new URL(window.location.href);
    if (selectedDate) url.searchParams.set("date", selectedDate);
    else url.searchParams.delete("date");
    window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function loadDashboard() {
    const selectedDate = dateInput?.value || "";
    if (requestController) requestController.abort();
    requestController = new AbortController();
    if (content.hidden) loading.hidden = false;
    error.hidden = true;
    if (dateInput) dateInput.disabled = true;
    if (todayButton) todayButton.disabled = true;
    if (dateStatus) dateStatus.textContent = "กำลังโหลดข้อมูลวันที่เลือก…";
    try {
      const url = new URL(config.summaryUrl, window.location.origin);
      if (selectedDate) url.searchParams.set("date", selectedDate);
      const response = await fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
        signal: requestController.signal,
      });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error || `เกิดข้อผิดพลาด HTTP ${response.status}`);
      render(data);
      loading.hidden = true;
      content.hidden = false;
      syncDateUrl(data.analytics?.selected_date || selectedDate);
      if (dateStatus) dateStatus.textContent = "อัปเดตข้อมูลแล้ว";
    } catch (loadError) {
      if (loadError.name === "AbortError") return;
      loading.hidden = true;
      error.hidden = false;
      errorMessage.textContent = loadError.message || "กรุณาลองอีกครั้ง";
      if (dateStatus) dateStatus.textContent = "ไม่สามารถอัปเดตข้อมูลได้";
    } finally {
      if (dateInput) dateInput.disabled = false;
      if (todayButton) todayButton.disabled = false;
    }
  }

  retry.addEventListener("click", loadDashboard);
  if (dateInput) {
    const requestedDate = new URLSearchParams(window.location.search).get("date");
    if (requestedDate && /^\d{4}-\d{2}-\d{2}$/.test(requestedDate) && requestedDate <= dateInput.max) {
      dateInput.value = requestedDate;
    }
    dateInput.addEventListener("change", loadDashboard);
  }
  if (todayButton && dateInput) {
    todayButton.addEventListener("click", () => {
      if (dateInput.value === dateInput.max) return;
      dateInput.value = dateInput.max;
      loadDashboard();
    });
  }
  loadDashboard();
})();
