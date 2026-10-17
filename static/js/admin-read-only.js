(() => {
  const root = document.documentElement;
  if (root.dataset.adminReadOnly !== "true") {
    return;
  }

  const forms = document.querySelectorAll("form");
  forms.forEach((form) => {
    const action = form.getAttribute("action") || "";
    if (action.endsWith("/admin/logout")) {
      return;
    }

    form.setAttribute("aria-disabled", "true");
    form.querySelectorAll("button, input, select, textarea").forEach((control) => {
      // View-only helpers (search, list filters) stay usable; they are never submitted.
      if (control.matches("[data-admin-list-search], [data-admin-list-selected], [data-admin-table-filter]")) return;
      control.disabled = true;
      control.setAttribute("title", "บัญชีหรือระบบนี้ดูได้อย่างเดียว");
    });
  });
})();
