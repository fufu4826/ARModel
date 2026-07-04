(function () {
  const panel = document.querySelector("[data-news-panel]");
  if (!panel) return;

  const hero = panel.closest(".landing-hero");
  const toggle = panel.querySelector("[data-news-panel-toggle]");
  const toggleText = panel.querySelector("[data-news-panel-toggle-text]");
  const content = panel.querySelector("[data-news-panel-content]");
  if (!hero || !toggle || !toggleText || !content) return;

  function setCollapsed(collapsed) {
    panel.classList.toggle("is-collapsed", collapsed);
    hero.classList.toggle("news-panel-collapsed", collapsed);
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "เปิดข่าวสาร" : "ซ่อนข่าวสาร");
    toggleText.textContent = collapsed ? "< ข่าวสาร" : "ซ่อนข่าวสาร >";
    content.setAttribute("aria-hidden", String(collapsed));
    content.inert = collapsed;
  }

  setCollapsed(window.matchMedia("(max-width: 920px)").matches);

  toggle.addEventListener("click", () => {
    setCollapsed(!panel.classList.contains("is-collapsed"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.classList.contains("is-collapsed")) {
      setCollapsed(true);
      toggle.focus();
    }
  });
})();
