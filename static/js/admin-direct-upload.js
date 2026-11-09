// Admin file uploads go straight from the browser to R2.
// Vercel rejects any request over 4.5 MB, so a form that carried the file itself failed for models,
// large photos and audio. Before the form is sent, each chosen file is uploaded with a short-lived
// link from /admin/api/create-upload-url; its public URL is written into the field named by
// data-upload-target and the file input is emptied, so the form only sends text.
(function () {
  const ENDPOINT = "/admin/api/create-upload-url";

  function csrfToken(form) {
    const field = form.querySelector("input[name='csrf_token']") || document.querySelector("input[name='csrf_token']");
    return field ? field.value : "";
  }

  function formatMb(bytes) {
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function setBusyMessage(text) {
    const message = document.querySelector("[data-admin-busy-message]");
    if (message) message.textContent = text;
  }

  function targetField(form, name) {
    let field = form.querySelector(`[name="${CSS.escape(name)}"]`);
    if (field && field.type === "file") field = null;
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = name;
      form.appendChild(field);
    }
    field.disabled = false;
    return field;
  }

  async function requestUploadLink(form, input, file) {
    const response = await fetch(ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken(form) },
      body: JSON.stringify({
        kind: input.dataset.uploadKind,
        filename: file.name,
        size: file.size,
        content_type: file.type,
      }),
    });
    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      data = {};
    }
    if (!response.ok || !data.upload_url) {
      throw new Error(data.error || `ขอสิทธิ์อัปโหลดไม่สำเร็จ (HTTP ${response.status})`);
    }
    return data;
  }

  function putFile(link, file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", link.upload_url);
      Object.entries(link.headers || {}).forEach(([name, value]) => xhr.setRequestHeader(name, value));
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) onProgress(event.loaded, event.total);
      });
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve();
        else reject(new Error(`อัปโหลดไฟล์ไม่สำเร็จ (HTTP ${xhr.status})`));
      });
      xhr.addEventListener("error", () => reject(new Error("อัปโหลดไฟล์ไม่สำเร็จ กรุณาตรวจการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่")));
      xhr.addEventListener("abort", () => reject(new Error("ยกเลิกการอัปโหลด")));
      xhr.send(file);
    });
  }

  async function uploadAll(form, inputs) {
    for (const [index, input] of inputs.entries()) {
      const file = input.files[0];
      const label = inputs.length > 1 ? `ไฟล์ ${index + 1}/${inputs.length}: ` : "";
      setBusyMessage(`${label}กำลังเตรียมอัปโหลด ${file.name}`);
      const link = await requestUploadLink(form, input, file);
      await putFile(link, file, (loaded, total) => {
        const percent = Math.round((loaded / total) * 100);
        setBusyMessage(`${label}กำลังอัปโหลด ${file.name} ${percent}% (${formatMb(loaded)} / ${formatMb(total)}) อย่าปิดหน้านี้`);
      });
      targetField(form, input.dataset.uploadTarget).value = link.public_url;
      input.value = "";
    }
  }

  document.addEventListener(
    "submit",
    async (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || form.dataset.directUploadDone === "true") return;
      const inputs = Array.from(form.querySelectorAll("input[type='file'][data-upload-kind][data-upload-target]"))
        .filter((input) => !input.disabled && input.files && input.files.length);
      if (!inputs.length) return;
      if (!form.checkValidity()) return;

      for (const input of inputs) {
        const maxBytes = Number(input.dataset.maxBytes || 0);
        if (maxBytes && input.files[0].size > maxBytes) {
          event.preventDefault();
          event.stopImmediatePropagation();
          window.alert(`ไฟล์ ${input.files[0].name} มีขนาด ${formatMb(input.files[0].size)} เกินกำหนด ${input.dataset.maxSizeLabel || formatMb(maxBytes)}`);
          return;
        }
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      if (window.AdminBusy) {
        window.AdminBusy.show(form, { submitter: event.submitter || null, title: "กำลังอัปโหลดไฟล์..." });
      }
      try {
        await uploadAll(form, inputs);
      } catch (error) {
        if (window.AdminBusy) window.AdminBusy.reset(form);
        window.alert(error.message || "อัปโหลดไฟล์ไม่สำเร็จ");
        return;
      }
      // Keep the clicked button's name/value (some forms use it to choose an action).
      const submitter = event.submitter;
      if (submitter && submitter.name) {
        const carrier = document.createElement("input");
        carrier.type = "hidden";
        carrier.name = submitter.name;
        carrier.value = submitter.value;
        form.appendChild(carrier);
      }
      setBusyMessage("อัปโหลดไฟล์เสร็จแล้ว กำลังบันทึกข้อมูล...");
      form.dataset.directUploadDone = "true";
      HTMLFormElement.prototype.submit.call(form);
    },
    true
  );
})();
