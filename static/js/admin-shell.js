// Admin layout behaviour only: mobile drawer, in-page tabs, table search, active menu item.
// Forms, routes and saved data are untouched.
(() => {
  const body = document.body;
  const nav = document.getElementById("admin-nav");
  const toggle = document.querySelector("[data-admin-nav-toggle]");
  const backdrop = document.querySelector(".admin-nav-backdrop");
  const mobile = window.matchMedia("(max-width: 960px)");

  function setNav(open) {
    if (!nav || !toggle) return;
    body.classList.toggle("admin-nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    if (backdrop) backdrop.hidden = !open;
    if (open) {
      const first = nav.querySelector("a, button");
      if (first) first.focus();
    }
  }

  if (toggle) toggle.addEventListener("click", () => setNav(!body.classList.contains("admin-nav-open")));
  document.querySelectorAll("[data-admin-nav-close]").forEach((el) => el.addEventListener("click", () => {
    setNav(false);
    if (toggle) toggle.focus();
  }));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && body.classList.contains("admin-nav-open")) {
      setNav(false);
      if (toggle) toggle.focus();
    }
  });
  if (nav) nav.addEventListener("click", (event) => {
    if (mobile.matches && event.target.closest("a")) setNav(false);
  });
  mobile.addEventListener("change", () => setNav(false));

  // Tabs on the content page (#models, #projects, #add-model-section, #add-project-section).
  const tabs = document.querySelector("[data-admin-tabs]");
  const panels = Array.from(document.querySelectorAll("[data-admin-tab-panel]"));
  const hashLinks = Array.from(document.querySelectorAll("[data-admin-nav-hash]"));

  function showPanel(id, { scroll = false } = {}) {
    if (!tabs || !panels.length) return;
    const target = panels.find((panel) => panel.id === id) || panels.find((panel) => panel.id === "models") || panels[0];
    panels.forEach((panel) => { panel.hidden = panel !== target; });
    tabs.querySelectorAll("[data-admin-tab-link]").forEach((link) => {
      const active = link.dataset.adminTabLink === target.id;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
    const listId = ["projects", "add-project-section"].includes(target.id) ? "projects" : "models";
    hashLinks.forEach((link) => link.classList.toggle("active", link.dataset.adminNavHash === listId));
    if (scroll) tabs.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  if (tabs && panels.length) {
    body.classList.add("admin-has-tabs");
    showPanel(location.hash.slice(1));
    window.addEventListener("hashchange", () => showPanel(location.hash.slice(1), { scroll: true }));
    document.querySelectorAll("[data-admin-tab-link]").forEach((link) => link.addEventListener("click", (event) => {
      event.preventDefault();
      const id = link.dataset.adminTabLink;
      history.replaceState(null, "", `#${id}`);
      showPanel(id, { scroll: !link.closest("[data-admin-tabs]") });
    }));
  }

  // Instant search over admin tables.
  document.querySelectorAll("[data-admin-table-filter]").forEach((input) => {
    const table = document.getElementById(input.dataset.adminTableFilter);
    const empty = document.querySelector(`[data-admin-table-empty="${input.dataset.adminTableFilter}"]`);
    if (!table) return;
    const rows = Array.from(table.tBodies[0] ? table.tBodies[0].rows : []);
    input.addEventListener("input", () => {
      const query = input.value.trim().toLowerCase();
      let shown = 0;
      rows.forEach((row) => {
        const match = !query || row.textContent.toLowerCase().includes(query);
        row.hidden = !match;
        if (match) shown += 1;
      });
      if (empty) empty.hidden = shown > 0;
    });
  });

  // Search and "selected only" filter for long card lists (e.g. recommended models).
  document.querySelectorAll("[data-admin-list]").forEach((list) => {
    const key = list.dataset.adminList;
    const search = document.querySelector(`[data-admin-list-search="${key}"]`);
    const selectedOnly = document.querySelector(`[data-admin-list-selected="${key}"]`);
    const empty = list.querySelector(`[data-admin-list-empty="${key}"]`);
    const items = Array.from(list.children).filter((item) => item.tagName === "ARTICLE");
    const apply = () => {
      const query = search ? search.value.trim().toLowerCase() : "";
      const onlyChecked = Boolean(selectedOnly && selectedOnly.checked);
      let shown = 0;
      items.forEach((item) => {
        const box = item.querySelector("input[type=checkbox]");
        const match = (!query || item.textContent.toLowerCase().includes(query)) && (!onlyChecked || (box && box.checked));
        item.hidden = !match;
        if (match) shown += 1;
      });
      if (empty) empty.hidden = shown > 0;
    };
    if (search) search.addEventListener("input", apply);
    if (selectedOnly) selectedOnly.addEventListener("change", apply);
    list.addEventListener("change", (event) => { if (onlyCheckedActive() && event.target.matches("input[type=checkbox]")) apply(); });
    function onlyCheckedActive() { return Boolean(selectedOnly && selectedOnly.checked); }
  });
})();
