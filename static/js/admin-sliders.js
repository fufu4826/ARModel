// News (slider) admin: live preview + link picker in the form, and instant reorder / show-hide in the list.
(function () {
  "use strict";

  // ---------- form: live preview and link picker ----------
  document.querySelectorAll("[data-news-form]").forEach((form) => {
    const q = (sel) => form.querySelector(sel);
    const title = q("[data-news-title]");
    const desc = q("[data-news-description]");
    const pick = q("[data-news-link-pick]");
    const url = q("[data-news-url]");
    const text = q("[data-news-button-text]");
    const customBox = q("[data-news-custom-url]");
    const textBox = q("[data-news-button-text-field]");
    const fileInput = q("input[type=file]");
    const card = {
      img: q("[data-news-card-img]"), empty: q("[data-news-card-empty]"), title: q("[data-news-card-title]"),
      desc: q("[data-news-card-desc]"), button: q("[data-news-card-button]"),
    };
    const dropImg = q("[data-news-preview-src]");
    const dropLabel = q(".news-drop__text strong");
    const knownUrls = Array.from(pick.options).map((o) => o.value).filter((v) => v && v !== "__custom");
    const suggestion = (option) => {
      const group = option.parentElement && option.parentElement.label;
      if (group === "โมเดล") return "ดูโมเดล";
      if (group === "แหล่งเรียนรู้") return "ดูแหล่งเรียนรู้";
      return "ดูรายละเอียด";
    };

    // Start the picker from the saved link.
    if (url.value) pick.value = knownUrls.includes(url.value) ? url.value : "__custom";

    function syncButtonFields() {
      const choice = pick.value;
      const hasButton = choice !== "";
      customBox.hidden = choice !== "__custom";
      textBox.hidden = !hasButton;
      url.required = hasButton;
      text.required = hasButton;
      if (!hasButton) { url.value = ""; text.value = ""; }
    }
    pick.addEventListener("change", () => {
      const option = pick.selectedOptions[0];
      if (pick.value && pick.value !== "__custom") {
        url.value = pick.value;
        if (!text.value.trim() || /^ดู(โมเดล|แหล่งเรียนรู้|รายละเอียด)$/.test(text.value.trim())) text.value = suggestion(option);
      } else if (pick.value === "__custom") {
        if (knownUrls.includes(url.value)) url.value = "";
        url.focus();
      }
      syncButtonFields();
      render();
    });

    function render() {
      card.title.textContent = title.value.trim() || "หัวข้อข่าว";
      card.desc.textContent = desc.value.trim();
      card.desc.hidden = !desc.value.trim();
      card.button.textContent = text.value.trim();
      card.button.hidden = !(pick.value && text.value.trim());
    }
    [title, desc, text, url].forEach((el) => el.addEventListener("input", render));

    fileInput.addEventListener("change", () => {
      const file = fileInput.files && fileInput.files[0];
      if (!file) return;
      const src = URL.createObjectURL(file);
      card.img.src = src; card.img.hidden = false; card.empty.hidden = true;
      dropImg.src = src; dropImg.hidden = false;
      if (dropLabel) dropLabel.textContent = "เปลี่ยนรูป";
    });

    syncButtonFields();
    render();
  });

  // ---------- add panel ----------
  const addPanel = document.querySelector("[data-news-add]");
  const addOpen = document.querySelector("[data-news-add-open]");
  if (addPanel && addOpen) {
    addOpen.addEventListener("click", () => {
      addPanel.hidden = false;
      addOpen.hidden = true;
      addPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      addPanel.querySelector("[data-news-title]")?.focus({ preventScroll: true });
    });
    addPanel.querySelector("[data-news-add-close]")?.addEventListener("click", () => {
      addPanel.hidden = true;
      addOpen.hidden = false;
      addOpen.focus();
    });
    if (location.hash === "#news-add") addOpen.click();
  }

  // ---------- list: instant reorder and show/hide ----------
  const root = document.querySelector("[data-news]");
  const list = document.querySelector("[data-news-list]");
  if (!root || !list) return;
  const security = document.querySelector("[data-news-security]");
  const status = document.querySelector("[data-news-status]");
  const summary = document.querySelector("[data-news-summary]");
  let statusTimer = null;

  function say(message, isError) {
    status.textContent = message;
    status.hidden = !message;
    status.classList.toggle("is-error", Boolean(isError));
    clearTimeout(statusTimer);
    if (message && !isError) statusTimer = setTimeout(() => { status.hidden = true; }, 2500);
  }
  async function post(url, fields) {
    const form = new FormData(security);
    Object.entries(fields).forEach(([k, v]) => form.set(k, v));
    let response, body = null;
    try {
      response = await fetch(url, { method: "POST", body: form, headers: { Accept: "application/json" }, credentials: "same-origin" });
      body = await response.json();
    } catch (error) {
      throw new Error("บันทึกไม่สำเร็จ กรุณาตรวจอินเทอร์เน็ตแล้วลองใหม่");
    }
    if (!response.ok || !body || !body.ok) throw new Error((body && body.error) || "บันทึกไม่สำเร็จ กรุณาโหลดหน้าใหม่");
    const revision = body.revisions && body.revisions.slider_items;
    const input = security.querySelector('input[name="revision_slider_items"]');
    if (input && revision != null) input.value = String(revision);
    return body;
  }
  const rows = () => Array.from(list.querySelectorAll("[data-news-id]"));
  function renumber() {
    rows().forEach((row, i, all) => {
      row.querySelector(".news-row__pos").textContent = i + 1;
      row.querySelector('[data-news-move="-1"]').disabled = i === 0;
      row.querySelector('[data-news-move="1"]').disabled = i === all.length - 1;
    });
    const shown = rows().filter((r) => !r.classList.contains("is-hidden")).length;
    if (summary) summary.textContent = `แสดงอยู่ ${shown} · ซ่อน ${rows().length - shown}`;
  }

  let saving = Promise.resolve();
  list.addEventListener("click", (event) => {
    const move = event.target.closest("[data-news-move]");
    if (!move) return;
    const row = move.closest("[data-news-id]");
    const step = Number(move.dataset.newsMove);
    const sibling = step < 0 ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    const before = rows().map((r) => r.dataset.newsId);
    if (step < 0) list.insertBefore(row, sibling); else list.insertBefore(sibling, row);
    renumber();
    move.focus();
    row.classList.add("is-moved");
    setTimeout(() => row.classList.remove("is-moved"), 600);
    const order = rows().map((r) => r.dataset.newsId).join(",");
    saving = saving.then(() => post(root.dataset.reorderUrl, { order }))
      .then(() => say("บันทึกลำดับแล้ว"))
      .catch((error) => {
        // Put the rows back the way the server still has them.
        before.forEach((id) => list.appendChild(list.querySelector(`[data-news-id="${id}"]`)));
        renumber();
        say(error.message, true);
      });
  });

  list.addEventListener("change", async (event) => {
    const box = event.target.closest("[data-news-visible]");
    if (!box) return;
    const row = box.closest("[data-news-id]");
    const label = row.querySelector("[data-news-visible-label]");
    const apply = (on) => { row.classList.toggle("is-hidden", !on); label.textContent = on ? "แสดงอยู่" : "ซ่อนอยู่"; box.checked = on; renumber(); };
    const wanted = box.checked;
    apply(wanted);
    box.disabled = true;
    try {
      await (saving = saving.then(() => post(root.dataset.visibilityUrl.replace("__ID__", encodeURIComponent(row.dataset.newsId)), { visible: wanted ? "1" : "0" })));
      say(wanted ? "แสดงข่าวบนเว็บแล้ว" : "ซ่อนข่าวจากเว็บแล้ว");
    } catch (error) {
      apply(!wanted);
      say(error.message, true);
    } finally {
      box.disabled = false;
    }
  });

  renumber();
})();
