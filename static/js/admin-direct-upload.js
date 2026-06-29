(function () {
  const root = document.documentElement;
  const directUploadsEnabled = root.dataset.directUploads === "true";
  if (!directUploadsEnabled) return;

  const uploadEndpoint = "/admin/api/create-upload-url";
  const managedUploadKinds = new Set([
    "landing_cover",
    "landing_mobile_cover_image",
    "site_logo",
    "site_social_image",
    "favicon",
    "intro_logo_1",
    "intro_logo_2",
    "intro_logo_3",
    "slider_image",
    "model_narration_audio",
  ]);
  const managedUploadMaxBytes = 5 * 1024 * 1024;
  const narrationAudioMaxBytes = 20 * 1024 * 1024;

  function fileTooLargeMessage(input) {
    const limit = input.dataset.maxSizeLabel || "ขนาดที่กำหนด";
    if (input.dataset.uploadKind === "model") {
      return `ไฟล์มีขนาดใหญ่เกินกำหนด กรุณาลดขนาดไฟล์ .glb หรือใช้ไฟล์ไม่เกิน ${limit}`;
    }
    return `ไฟล์มีขนาดใหญ่เกินกำหนด กรุณาใช้ไฟล์ไม่เกิน ${limit}`;
  }

  async function uploadErrorMessage(response, input) {
    const responseText = await response.text();
    let message = responseText;
    try {
      const payload = JSON.parse(responseText);
      message = payload.message || payload.error || responseText;
    } catch {
      // Supabase may return plain text for some storage errors.
    }

    if (
      response.status === 413 ||
      /payload too large|maximum allowed size|exceeded.*size/i.test(message)
    ) {
      return fileTooLargeMessage(input);
    }
    return message || "การอัปโหลดไฟล์ไปยังระบบจัดเก็บข้อมูลล้มเหลว";
  }

  function statusFor(input) {
    let status = input.parentElement.querySelector("[data-upload-status]");
    if (!status) {
      status = document.createElement("div");
      status.dataset.uploadStatus = "";
      status.style.color = "#66756b";
      status.style.fontSize = "12px";
      status.style.fontWeight = "800";
      status.style.lineHeight = "1.4";
      input.insertAdjacentElement("afterend", status);
    }
    return status;
  }

  function targetInputFor(input) {
    const targetName = input.dataset.uploadTarget;
    if (!targetName) return null;
    return input.form.querySelector(`[name="${targetName}"]`);
  }

  async function createUploadUrl(input, file) {
    const response = await fetch(uploadEndpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: file.name,
        kind: input.dataset.uploadKind,
        content_type: file.type || "application/octet-stream",
        file_size: file.size,
      }),
    });
    if (!response.ok) {
      throw new Error(await uploadErrorMessage(response, input));
    }
    return response.json();
  }

  async function uploadFile(input) {
    const file = input.files && input.files[0];
    if (!file) return;
    const status = statusFor(input);
    status.style.color = "#66756b";

    try {
      const configuredMaxBytes = Number(input.dataset.maxBytes || 0);
      if (configuredMaxBytes > 0 && file.size > configuredMaxBytes) {
        throw new Error(fileTooLargeMessage(input));
      }
      if (
        input.dataset.uploadKind === "model_narration_audio" &&
        file.size > narrationAudioMaxBytes
      ) {
        throw new Error("ไฟล์เสียงต้องมีขนาดไม่เกิน 20 MB");
      }
      if (
        input.dataset.uploadKind !== "model_narration_audio" &&
        managedUploadKinds.has(input.dataset.uploadKind) &&
        file.size > managedUploadMaxBytes
      ) {
        throw new Error("ไฟล์รูปภาพต้องมีขนาดไม่เกิน 5 MB");
      }

      const target = targetInputFor(input);
      if (!target) {
        throw new Error("ไม่พบฟิลด์เป้าหมายสำหรับการอัปโหลดไฟล์");
      }

      status.textContent = `กำลังอัปโหลด ${file.name}...`;
      input.disabled = true;
      const upload = await createUploadUrl(input, file);
      const response = await fetch(upload.upload_url, {
        method: "PUT",
        headers: {
          "Content-Type": file.type || "application/octet-stream",
          // Unique object names make immutable caching safe and stop repeat
          // model views from consuming Supabase egress.
          "Cache-Control": "max-age=31536000, immutable",
        },
        body: file,
      });
      if (!response.ok) {
        throw new Error(await uploadErrorMessage(response, input));
      }

      target.value = upload.public_url;
      input.removeAttribute("name");
      status.textContent = "อัปโหลดไฟล์เสร็จสมบูรณ์";
    } catch (error) {
      input.disabled = false;
      status.style.color = "#b42318";
      status.textContent = error.message || "การอัปโหลดล้มเหลว";
      throw error;
    }
  }

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      if (form.dataset.adminBusySubmitting === "true") {
        event.preventDefault();
        return;
      }
      if (form.dataset.directUploadSubmitting === "true") return;

      const inputs = Array.from(form.querySelectorAll("input[type='file'][data-upload-kind]"));
      const selectedInputs = inputs.filter((input) => input.files && input.files.length);
      if (!selectedInputs.length) return;

      event.preventDefault();
      if (window.AdminBusy) {
        window.AdminBusy.show(form, {
          submitter: event.submitter || null,
          title: "กำลังอัปโหลดข้อมูล...",
          message: "กำลังอัปโหลดไฟล์และบันทึกข้อมูล กรุณารอสักครู่ อย่าปิดหน้านี้หรือกดซ้ำ",
        });
      }
      const submitters = Array.from(form.querySelectorAll("button[type='submit'], input[type='submit']"));
      submitters.forEach((button) => {
        button.disabled = true;
      });

      try {
        for (const input of selectedInputs) {
          await uploadFile(input);
        }
        form.dataset.directUploadSubmitting = "true";
        form.submit();
      } catch {
        if (window.AdminBusy) window.AdminBusy.reset(form);
        submitters.forEach((button) => {
          button.disabled = false;
        });
      }
    });
  });
})();
