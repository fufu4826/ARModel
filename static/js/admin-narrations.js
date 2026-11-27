// Voice narration studio: pick a model, edit the script, generate a draft, listen, then use or discard it.
// Everything happens in place (fetch + JSON); the server keeps its normal redirect flow for non-JS use.
(function () {
  "use strict";
  const root = document.querySelector("[data-voice-studio]");
  if (!root) return;

  const data = JSON.parse(document.querySelector("[data-voice-data]").textContent || "{}");
  const security = document.querySelector("[data-voice-security]");
  const editor = root.querySelector("[data-voice-editor]");
  const template = document.querySelector("[data-voice-editor-template]");
  const itemsBox = root.querySelector("[data-voice-items]");
  const items = Array.from(root.querySelectorAll("[data-voice-item]"));
  const search = root.querySelector("[data-voice-search]");
  const projectSelect = root.querySelector("[data-voice-project]");
  const tabs = Array.from(root.querySelectorAll("[data-voice-tab]"));
  const empty = root.querySelector("[data-voice-empty]");
  const batch = root.querySelector("[data-voice-batch]");
  const textMax = Number(root.dataset.textMax || 3000);
  const drafts = {};          // model id -> draft from the server
  const busy = new Set();     // model ids being generated
  let tab = "without";
  let current = null;         // selected model id
  let batchStop = false;
  let batchRunning = false;

  const total = Object.keys(data).length;
  const withAudio = () => Object.values(data).filter((m) => m.audio).length;

  // ---------- server calls ----------
  function securityFields() {
    const form = new FormData();
    if (security) new FormData(security).forEach((value, key) => form.append(key, value));
    return form;
  }
  function setRevision(name, value) {
    if (value == null || !security) return;
    const input = security.querySelector(`input[name="revision_${name}"]`);
    if (input) input.value = String(value);
  }
  async function post(url, fields) {
    const form = securityFields();
    Object.entries(fields || {}).forEach(([key, value]) => form.set(key, value));
    let response;
    try {
      response = await fetch(url, { method: "POST", body: form, headers: { Accept: "application/json" }, credentials: "same-origin" });
    } catch (error) {
      throw new Error("เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจอินเทอร์เน็ตแล้วลองใหม่");
    }
    let body = null;
    try { body = await response.json(); } catch (error) { /* not JSON */ }
    if (response.status === 401 || response.redirected && /\/admin\/login/.test(response.url)) {
      throw new Error("หมดเวลาเข้าสู่ระบบ กรุณาโหลดหน้าใหม่แล้วเข้าสู่ระบบอีกครั้ง");
    }
    if (!response.ok || !body || body.ok === false) {
      throw new Error((body && body.error) || `เกิดข้อผิดพลาด (${response.status}) กรุณาลองใหม่`);
    }
    return body;
  }

  // ---------- list ----------
  function pillFor(id) {
    if (busy.has(id)) return ["กำลังสร้าง…", "busy"];
    if (drafts[id]) return ["รอฟัง", "draft"];
    return data[id].audio ? ["มีเสียง", "ok"] : ["ไม่มีเสียง", "none"];
  }
  function refreshItem(id) {
    const button = itemsBox.querySelector(`[data-voice-item="${id}"]`);
    if (!button) return;
    const [label, state] = pillFor(id);
    const pill = button.querySelector("[data-voice-pill]");
    pill.textContent = label;
    pill.dataset.state = state;
    button.dataset.audio = data[id].audio ? "with" : "without";
    button.classList.toggle("is-selected", id === current);
    button.setAttribute("aria-current", id === current ? "true" : "false");
  }
  function visibleIds() {
    const query = (search.value || "").trim().toLowerCase();
    const project = projectSelect.value;
    return items.filter((button) => {
      const id = button.dataset.voiceItem;
      const audio = data[id].audio ? "with" : "without";
      const inTab = tab === "all" || audio === tab || drafts[id] || busy.has(id) || id === current;
      return inTab && (!query || button.dataset.name.includes(query)) && (!project || button.dataset.project === project);
    }).map((button) => button.dataset.voiceItem);
  }
  function applyFilter() {
    const shown = new Set(visibleIds());
    items.forEach((button) => { button.parentElement.hidden = !shown.has(button.dataset.voiceItem); });
    empty.hidden = shown.size > 0;
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t.dataset.voiceTab === tab)));
    const without = Object.values(data).filter((m) => !m.audio).length;
    root.querySelector('[data-voice-count="without"]').textContent = without;
    root.querySelector('[data-voice-count="with"]').textContent = total - without;
    root.querySelector("[data-voice-done]").textContent = total - without;
    root.querySelector("[data-voice-bar]").style.width = `${(100 * (total - without)) / (total || 1)}%`;
    const pending = [...shown].filter((id) => !data[id].audio && !drafts[id]);
    batch.hidden = tab !== "without" || pending.length < 2 || batchRunning;
    root.querySelector("[data-voice-batch-n]").textContent = pending.length;
  }
  tabs.forEach((t) => t.addEventListener("click", () => { tab = t.dataset.voiceTab; applyFilter(); }));
  search.addEventListener("input", applyFilter);
  projectSelect.addEventListener("change", applyFilter);
  items.forEach((button) => button.addEventListener("click", () => select(button.dataset.voiceItem)));

  // ---------- editor ----------
  let view = null;
  const $ = (name) => view && view.querySelector(`[data-v="${name}"]`);
  const thaiSecondsPerChar = 1 / 11;   // Thai TTS reads roughly 11 characters per second

  function updateCount() {
    const n = $("text").value.trim().length;
    const seconds = Math.max(1, Math.round(n * thaiSecondsPerChar));
    const time = seconds >= 60 ? `${Math.floor(seconds / 60)} นาที ${seconds % 60} วินาที` : `${seconds} วินาที`;
    $("count").textContent = `${n.toLocaleString("th-TH")} ตัวอักษร · ฟังประมาณ ${time}`;
    $("count").classList.toggle("is-over", n > textMax);
    $("generate").disabled = busy.has(current) || n === 0 || n > textMax;
  }

  function renderEditor() {
    const id = current;
    const model = data[id];
    $("thumb").src = model.thumb || "";
    $("name").textContent = model.name;
    $("project").textContent = model.project + (model.visible ? "" : " (ซ่อนอยู่)");
    $("edit").href = root.dataset.editUrl.replace("__ID__", encodeURIComponent(id));
    const audio = $("current-audio");
    audio.hidden = !model.audio;
    if (model.audio && audio.getAttribute("src") !== model.audio) audio.src = model.audio;
    $("no-audio").hidden = Boolean(model.audio);
    const draft = drafts[id];
    $("draft").hidden = !draft;
    if (draft && $("draft-audio").getAttribute("src") !== draft.audio_url) $("draft-audio").src = draft.audio_url;
    $("generate").textContent = model.audio || draft ? "สร้างเสียงใหม่" : "สร้างเสียง";
    $("busy").hidden = !busy.has(id);
    updateCount();
  }

  function select(id, { focusEditor = true } = {}) {
    if (!data[id]) return;
    const previous = current;
    current = id;
    if (!view) {
      editor.innerHTML = "";
      editor.appendChild(template.content.cloneNode(true));
      view = editor.querySelector(".voice-panel");
      $("text").maxLength = textMax + 500;
      $("text").addEventListener("input", () => { data[current].text = $("text").value; updateCount(); });
      $("reset").addEventListener("click", () => { $("text").value = data[current].defaultText; data[current].text = $("text").value; updateCount(); $("text").focus(); });
      $("generate").addEventListener("click", () => generate(current));
      $("regenerate").addEventListener("click", () => generate(current));
      $("confirm").addEventListener("click", () => confirmDraft(current));
      $("discard").addEventListener("click", () => discardDraft(current));
      $("next").addEventListener("click", () => {
        const next = nextWithout(current);
        if (next) select(next); else { $("saved").hidden = true; }
      });
      $("back").addEventListener("click", () => { root.classList.remove("is-editing"); itemsBox.querySelector(`[data-voice-item="${current}"]`)?.focus(); });
    }
    if (previous !== id) {
      $("text").value = data[id].text;
      $("error").hidden = true;
      $("saved").hidden = true;
      $("current-audio").pause();
      $("draft-audio").pause();
    }
    [previous, id].filter(Boolean).forEach(refreshItem);
    renderEditor();
    applyFilter();
    root.classList.add("is-editing");
    if (focusEditor && window.matchMedia("(max-width: 900px)").matches) editor.scrollIntoView({ behavior: "smooth", block: "start" });
    try { history.replaceState(null, "", `?focus=${encodeURIComponent(id)}`); } catch (error) { /* ignore */ }
  }

  function showError(id, message) {
    if (id !== current || !view) return;
    $("error").textContent = message;
    $("error").hidden = !message;
  }

  async function generate(id, { quiet = false } = {}) {
    if (busy.has(id)) return false;
    const text = (data[id].text || "").trim();
    if (!text || text.length > textMax) { showError(id, "กรุณาใส่ข้อความ (ไม่เกิน " + textMax.toLocaleString("th-TH") + " ตัวอักษร)"); return false; }
    busy.add(id);
    refreshItem(id);
    const started = Date.now();
    const tick = setInterval(() => {
      if (id === current && view) $("busy-text").textContent = `กำลังสร้างเสียง… ${Math.round((Date.now() - started) / 1000)} วินาที`;
    }, 1000);
    if (id === current) { showError(id, ""); $("busy-text").textContent = "กำลังสร้างเสียง…"; renderEditor(); }
    try {
      const old = drafts[id];
      const result = await post(root.dataset.draftUrl.replace("__ID__", encodeURIComponent(id)), { text });
      drafts[id] = result;
      if (old) post(old.cancel_url).catch(() => {});   // the replaced draft is no longer needed
      if (id === current && !quiet) {
        renderEditor();
        $("draft").scrollIntoView({ behavior: "smooth", block: "nearest" });
        const player = $("draft-audio");
        player.currentTime = 0;
        player.play().catch(() => {});
      }
      return true;
    } catch (error) {
      showError(id, error.message);
      return false;
    } finally {
      clearInterval(tick);
      busy.delete(id);
      refreshItem(id);
      if (id === current) renderEditor();
      applyFilter();
    }
  }

  async function confirmDraft(id) {
    const draft = drafts[id];
    if (!draft) return;
    $("confirm").disabled = true;
    try {
      const result = await post(draft.confirm_url);
      setRevision("models", result.revisions && result.revisions.models);
      data[id].audio = result.audio_url;
      delete drafts[id];
      if (id === current) {
        renderEditor();
        $("saved").hidden = false;
        $("next").hidden = !nextWithout(id);
      }
    } catch (error) {
      showError(id, error.message);
    } finally {
      if (view) $("confirm").disabled = false;
      refreshItem(id);
      applyFilter();
    }
  }

  async function discardDraft(id) {
    const draft = drafts[id];
    if (!draft) return;
    delete drafts[id];
    $("draft-audio").pause();
    renderEditor();
    refreshItem(id);
    applyFilter();
    post(draft.cancel_url).catch(() => {});
  }

  function nextWithout(fromId) {
    const order = items.map((b) => b.dataset.voiceItem);
    const start = order.indexOf(fromId);
    const rest = order.slice(start + 1).concat(order.slice(0, start));
    return rest.find((id) => !data[id].audio && !busy.has(id)) || null;
  }

  // ---------- batch: draft a voice for every model in the list that has none ----------
  root.querySelector("[data-voice-batch-start]").addEventListener("click", async () => {
    const queue = visibleIds().filter((id) => !data[id].audio && !drafts[id]);
    if (!queue.length) return;
    batchRunning = true;
    batchStop = false;
    const run = root.querySelector("[data-voice-batch-run]");
    const status = root.querySelector("[data-voice-batch-status]");
    root.querySelector("[data-voice-batch-start]").hidden = true;
    run.hidden = false;
    batch.hidden = false;
    let done = 0, failed = 0;
    for (const id of queue) {
      if (batchStop) break;
      status.textContent = `กำลังสร้าง ${done + failed + 1} / ${queue.length}: ${data[id].name}`;
      if (await generate(id, { quiet: true })) done += 1; else failed += 1;
    }
    batchRunning = false;
    status.textContent = `สร้างเสร็จ ${done} เสียง${failed ? ` ไม่สำเร็จ ${failed}` : ""} กดที่โมเดลป้าย “รอฟัง” เพื่อฟังแล้วกดใช้`;
    root.querySelector("[data-voice-batch-start]").hidden = false;
    setTimeout(() => { run.hidden = true; applyFilter(); }, 8000);
    const first = queue.find((id) => drafts[id]);
    if (first) select(first, { focusEditor: false });
  });
  root.querySelector("[data-voice-batch-stop]").addEventListener("click", () => {
    batchStop = true;
    root.querySelector("[data-voice-batch-status]").textContent = "กำลังหยุดหลังจากเสียงที่กำลังสร้างเสร็จ…";
  });

  window.addEventListener("beforeunload", (event) => {
    if (Object.keys(drafts).length || busy.size) { event.preventDefault(); event.returnValue = ""; }
  });

  // ---------- start ----------
  const initial = document.querySelector("[data-voice-initial-draft]");
  if (initial) {
    try { const d = JSON.parse(initial.textContent); drafts[d.model_id] = d; } catch (error) { /* ignore */ }
  }
  if (!Object.values(data).some((m) => !m.audio)) tab = "all";
  items.forEach((b) => refreshItem(b.dataset.voiceItem));
  applyFilter();
  const focus = root.dataset.focus;
  if (focus && data[focus]) select(focus, { focusEditor: false });
  else if (window.matchMedia("(min-width: 901px)").matches) {
    const first = visibleIds()[0];
    if (first) select(first, { focusEditor: false });
  }
})();
