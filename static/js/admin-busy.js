(function () {
  const submittingForms = new WeakSet();

  function modalElements() {
    const modal = document.querySelector("[data-admin-busy-modal]");
    if (!modal) return null;
    return {
      modal,
      title: modal.querySelector("[data-admin-busy-title]"),
      message: modal.querySelector("[data-admin-busy-message]"),
    };
  }

  function submitControls(form, submitter) {
    const controls = Array.from(form.elements || []).filter((element) => {
      if (element.tagName === "BUTTON") return element.type === "submit";
      return element.tagName === "INPUT" && element.type === "submit";
    });
    if (submitter && !controls.includes(submitter)) controls.push(submitter);
    return controls;
  }

  function disableSubmitControls(form, submitter) {
    submitControls(form, submitter).forEach((control) => {
      if (control.disabled) return;
      control.dataset.adminBusyDisabled = "true";
      control.disabled = true;
      if (control.tagName === "INPUT") {
        control.dataset.adminBusyOriginalValue = control.value;
        control.value = "กำลังบันทึก...";
      } else {
        control.dataset.adminBusyOriginalText = control.textContent;
        control.textContent = "กำลังบันทึก...";
      }
    });
  }

  function restoreSubmitControls(form) {
    submitControls(form).forEach((control) => {
      if (control.dataset.adminBusyDisabled !== "true") return;
      control.disabled = false;
      delete control.dataset.adminBusyDisabled;
      if (control.dataset.adminBusyOriginalValue !== undefined) {
        control.value = control.dataset.adminBusyOriginalValue;
        delete control.dataset.adminBusyOriginalValue;
      }
      if (control.dataset.adminBusyOriginalText !== undefined) {
        control.textContent = control.dataset.adminBusyOriginalText;
        delete control.dataset.adminBusyOriginalText;
      }
    });
  }

  function show(form, options = {}) {
    const elements = modalElements();
    if (!elements || !form) return false;
    if (submittingForms.has(form)) return false;

    submittingForms.add(form);
    form.dataset.adminBusySubmitting = "true";
    disableSubmitControls(form, options.submitter || null);

    const title =
      options.title ||
      form.dataset.adminBusyTitle ||
      "กำลังบันทึกข้อมูล...";
    const message =
      options.message ||
      form.dataset.adminBusyMessage ||
      "กำลังอัปโหลด/บันทึกข้อมูล กรุณารอสักครู่ อย่าปิดหน้านี้หรือกดซ้ำ";

    elements.title.textContent = title;
    elements.message.textContent = message;
    elements.modal.hidden = false;
    document.body.classList.add("admin-is-busy");
    return true;
  }

  function reset(form) {
    if (form) {
      submittingForms.delete(form);
      delete form.dataset.adminBusySubmitting;
      restoreSubmitControls(form);
    }
    const elements = modalElements();
    if (elements) elements.modal.hidden = true;
    document.body.classList.remove("admin-is-busy");
  }

  window.AdminBusy = { show, reset };

  document.addEventListener(
    "click",
    (event) => {
      const submitter = event.target.closest(
        "button[type='submit'][data-confirm], input[type='submit'][data-confirm]"
      );
      if (!submitter || !submitter.form) return;
      if (!window.confirm(submitter.dataset.confirm)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    },
    true
  );

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.dataset.adminNoBusy !== undefined) return;
    if (String(form.method || "").toLowerCase() !== "post") return;
    if (event.defaultPrevented) return;
    if (!form.checkValidity()) return;

    if (submittingForms.has(form)) {
      event.preventDefault();
      return;
    }

    show(form, { submitter: event.submitter || null });
  });
})();
