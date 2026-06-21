(function () {
  document.querySelectorAll("[data-mobile-nav-toggle]").forEach((toggle) => {
    const targetId = toggle.getAttribute("aria-controls");
    const menu = document.getElementById(targetId);
    if (!menu) return;

    toggle.addEventListener("click", () => {
      const isOpen = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menu.classList.contains("is-open")) {
        menu.classList.remove("is-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
  });
})();
