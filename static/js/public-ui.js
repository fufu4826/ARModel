// Public-site enhancements (progressive): model-page tabs, mobile action bar, filter chips.
// Without JavaScript every panel stays visible and the original <select> filter works.
(() => {
  // ---------- Tabs (WAI-ARIA tabs pattern, automatic activation) ----------
  document.querySelectorAll("[data-tabs]").forEach((root) => {
    const list = root.querySelector('[role="tablist"]');
    const tabs = Array.from(root.querySelectorAll('[role="tab"]'));
    const panels = tabs.map((tab) => document.getElementById(tab.getAttribute("aria-controls")));
    if (!list || !tabs.length) return;
    list.hidden = false;
    root.classList.add("js-tabs");

    function select(index, focus) {
      tabs.forEach((tab, i) => {
        const active = i === index;
        tab.setAttribute("aria-selected", String(active));
        tab.tabIndex = active ? 0 : -1;
        if (panels[i]) panels[i].hidden = !active;
      });
      if (focus) tabs[index].focus();
    }

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => select(index, false));
      tab.addEventListener("keydown", (event) => {
        const keys = { ArrowRight: 1, ArrowLeft: -1, Home: "first", End: "last" };
        if (!(event.key in keys)) return;
        event.preventDefault();
        const step = keys[event.key];
        const next = step === "first" ? 0 : step === "last" ? tabs.length - 1 : (index + step + tabs.length) % tabs.length;
        select(next, true);
      });
    });
    root.showTab = (panelId) => {
      const index = tabs.findIndex((tab) => tab.getAttribute("aria-controls") === panelId);
      if (index >= 0) select(index, false);
    };
    select(0, false);
  });

  // ---------- Model page mobile action bar ----------
  const viewer = document.getElementById("mainModelViewer");
  const tabsRoot = document.querySelector(".model-tabs[data-tabs]");
  const arButton = document.querySelector("[data-action-ar]");
  if (arButton) {
    arButton.addEventListener("click", () => {
      if (viewer && viewer.canActivateAR && typeof viewer.activateAR === "function") {
        viewer.activateAR();
        return;
      }
      // AR not available here: show how to use it instead of failing silently.
      if (tabsRoot && tabsRoot.showTab) tabsRoot.showTab("panel-ar");
      const guide = document.getElementById("ar-guide-title");
      if (guide) guide.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }
  const narrationButton = document.querySelector("[data-action-narration]");
  const narrationToggle = document.querySelector("[data-narration-toggle]");
  if (narrationButton && narrationToggle) {
    narrationButton.addEventListener("click", () => narrationToggle.click());
  }

  // ---------- Filter chips driving the existing <select> ----------
  document.querySelectorAll("[data-filter-chips]").forEach((group) => {
    const select = document.getElementById(group.dataset.filterChips);
    const holder = group.querySelector(".filter-chips");
    if (!select || !holder) return;
    const chips = Array.from(select.options).map((option) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "filter-chip";
      chip.textContent = option.value ? option.textContent : "ทั้งหมด";
      chip.dataset.value = option.value;
      chip.setAttribute("aria-pressed", String(option.value === select.value));
      chip.addEventListener("click", () => {
        select.value = option.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
      });
      holder.append(chip);
      return chip;
    });
    select.addEventListener("change", () => {
      chips.forEach((chip) => chip.setAttribute("aria-pressed", String(chip.dataset.value === select.value)));
    });
    const selectGroup = select.closest(".field-group");
    if (selectGroup) selectGroup.classList.add("visually-hidden-field");
    group.hidden = false;
  });
})();
