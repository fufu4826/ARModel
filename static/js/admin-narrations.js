(function () {
  "use strict";
  let activeAudio = null;
  const items = Array.from(document.querySelectorAll("[data-narration-item]"));
  const search = document.querySelector("[data-narration-search]");
  const project = document.querySelector("[data-narration-project]");
  const audioStatus = document.querySelector("[data-narration-audio-status]");
  const visibility = document.querySelector("[data-narration-visibility]");
  const resultCount = document.querySelector("[data-narration-result-count]");
  const emptyState = document.querySelector("[data-narration-empty]");

  function restoreAudioButton(button) {
    button.textContent = button.dataset.originalLabel || "ฟังเสียง";
    button.setAttribute("aria-pressed", "false");
  }

  function filterItems() {
    const query = (search?.value || "").trim().toLowerCase();
    let count = 0;
    items.forEach((item) => {
      const matches = (!query || item.dataset.name.includes(query)) &&
        (!project?.value || item.dataset.project === project.value) &&
        (!audioStatus?.value || audioStatus.value === "all" || item.dataset.audio === audioStatus.value) &&
        (!visibility?.value || visibility.value === "all" || item.dataset.visibility === visibility.value);
      item.hidden = !matches;
      if (matches) count += 1;
    });
    if (resultCount) resultCount.textContent = `แสดง ${count} โมเดล`;
    if (emptyState) emptyState.hidden = count !== 0;
  }

  [search, project, audioStatus, visibility].filter(Boolean).forEach((control) => {
    control.addEventListener("input", filterItems);
    control.addEventListener("change", filterItems);
  });
  document.querySelectorAll("[data-narration-reset]").forEach((button) => {
    button.addEventListener("click", () => {
      if (search) search.value = "";
      if (project) project.value = "";
      if (audioStatus) audioStatus.value = "all";
      if (visibility) visibility.value = "all";
      filterItems();
      search?.focus();
    });
  });
  filterItems();

  document.querySelectorAll("[data-generate-dialog]").forEach((button) => {
    button.addEventListener("click", () => document.getElementById(button.dataset.generateDialog)?.showModal());
  });

  document.querySelectorAll("[data-audio-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const source = button.dataset.audioSrc;
      if (!source) return;
      if (activeAudio && activeAudio.button === button) {
        activeAudio.audio.pause();
        activeAudio = null;
        restoreAudioButton(button);
        return;
      }
      if (activeAudio) {
        activeAudio.audio.pause();
        restoreAudioButton(activeAudio.button);
      }
      const audio = new Audio(source);
      button.dataset.originalLabel ||= button.textContent;
      activeAudio = { audio, button };
      button.textContent = "หยุดเสียง";
      button.setAttribute("aria-pressed", "true");
      audio.addEventListener("ended", () => { if (activeAudio?.audio === audio) { restoreAudioButton(button); activeAudio = null; } });
      audio.addEventListener("error", () => { restoreAudioButton(button); activeAudio = null; });
      audio.play().catch(() => { restoreAudioButton(button); activeAudio = null; });
    });
  });
})();
