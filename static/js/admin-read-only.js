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
      control.disabled = true;
      control.setAttribute("title", "Production admin is read-only");
    });
  });
})();
