(function () {
  const root = document.documentElement;
  const directUploadsEnabled = root.dataset.directUploads === "true";
  if (!directUploadsEnabled) return;

  const uploadEndpoint = "/admin/api/create-upload-url";

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
      }),
    });
    if (!response.ok) {
      const message = await response.text();
      throw new Error(message || "Unable to create upload URL.");
    }
    return response.json();
  }

  async function uploadFile(input) {
    const file = input.files && input.files[0];
    if (!file) return;

    const target = targetInputFor(input);
    if (!target) {
      throw new Error("Upload target field is missing.");
    }

    const status = statusFor(input);
    status.textContent = `Uploading ${file.name}...`;
    input.disabled = true;

    try {
      const upload = await createUploadUrl(input, file);
      const response = await fetch(upload.upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file,
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || "Direct upload failed.");
      }

      target.value = upload.public_url;
      input.removeAttribute("name");
      status.textContent = "Upload complete.";
    } catch (error) {
      input.disabled = false;
      status.style.color = "#b42318";
      status.textContent = error.message || "Upload failed.";
      throw error;
    }
  }

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      if (form.dataset.directUploadSubmitting === "true") return;

      const inputs = Array.from(form.querySelectorAll("input[type='file'][data-upload-kind]"));
      const selectedInputs = inputs.filter((input) => input.files && input.files.length);
      if (!selectedInputs.length) return;

      event.preventDefault();
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
        submitters.forEach((button) => {
          button.disabled = false;
        });
      }
    });
  });
})();
