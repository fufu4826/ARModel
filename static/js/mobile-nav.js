(function () {
  // Publish the sticky header height so sections reached from the menu are not hidden under it.
  const header = document.querySelector(".site-nav");
  const setNavHeight = () => {
    if (header) document.documentElement.style.setProperty("--nav-h", header.offsetHeight + "px");
  };
  setNavHeight();
  window.addEventListener("resize", setNavHeight);

  document.querySelectorAll("[data-mobile-nav-toggle]").forEach((toggle) => {
    const targetId = toggle.getAttribute("aria-controls");
    const menu = document.getElementById(targetId);
    if (!menu) return;
    const close = () => {
      menu.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    };

    toggle.addEventListener("click", () => {
      const isOpen = menu.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(isOpen));
    });

    // Close after choosing a link (same-page links like #projects would otherwise leave it open).
    menu.querySelectorAll("a").forEach((link) => link.addEventListener("click", close));

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && menu.classList.contains("is-open")) {
        close();
        toggle.focus();
      }
    });
  });
})();
