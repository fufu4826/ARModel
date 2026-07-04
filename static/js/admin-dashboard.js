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

  function render(data) {
    renderOverview(data);
    renderStorage(data.storage);
    renderHealth(data.health);
    document.getElementById("analytics-disabled").querySelector("strong").textContent =
      data.analytics.message || "ยังไม่ได้ตั้งค่าระบบวิเคราะห์ผู้เข้าชม";
    document.getElementById("dashboard-generated").textContent =
      `สร้างข้อมูลเมื่อ ${new Date(data.generated_at).toLocaleString("th-TH")}`;
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
      if (!response.ok || data.error) throw new Error(data.error || `เกิดข้อผิดพลาด HTTP ${response.status}`);
      render(data);
      loading.hidden = true;
      content.hidden = false;
    } catch (loadError) {
      loading.hidden = true;
      error.hidden = false;
      errorMessage.textContent = loadError.message || "กรุณาลองอีกครั้ง";
    }
  }

  retry.addEventListener("click", loadDashboard);
  loadDashboard();
})();
