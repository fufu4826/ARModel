(function () {
  // 1. Handle file inputs (local URL.createObjectURL)
  document.querySelectorAll("input[type='file']").forEach((input) => {
    const preview = document.querySelector(`[data-image-preview="${input.id}"]`);
    if (!preview) return;

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) {
        input.value = "";
        window.alert("ไฟล์รูปภาพต้องมีขนาดไม่เกิน 5 MB");
        return;
      }

      const objectUrl = URL.createObjectURL(file);
      preview.src = objectUrl;
      preview.hidden = false;
      preview.addEventListener("load", () => URL.revokeObjectURL(objectUrl), { once: true });
      const fallback = preview.parentElement && preview.parentElement.querySelector(".preview-fallback");
      if (fallback) fallback.hidden = true;
    });
  });

  // Helper to resolve URL or static path
  function resolveUrl(value) {
    if (!value) return "";
    if (/^https?:\/\//i.test(value) || value.startsWith("/") || value.startsWith("data:")) {
      return value;
    }
    return `/static/${value.replace(/^static\//, "")}`;
  }

  // 2. Handle URL / Path text inputs (data-image-preview-target)
  document.querySelectorAll("[data-image-preview-target]").forEach((textInput) => {
    const previewId = textInput.dataset.imagePreviewTarget;
    const previewImg = document.getElementById(previewId);
    if (!previewImg) return;

    function updatePreview() {
      const value = textInput.value.trim();
      if (value) {
        previewImg.src = resolveUrl(value);
        previewImg.hidden = false;
        const fallback = previewImg.parentElement && previewImg.parentElement.querySelector(".preview-fallback");
        if (fallback) fallback.hidden = true;
      } else {
        // If we clear the URL input, see if the file input has a file
        const fileInputId = previewImg.dataset.imagePreview;
        const fileInput = fileInputId ? document.getElementById(fileInputId) : null;
        if (fileInput && fileInput.files && fileInput.files[0]) {
          // Keep file preview
        } else {
          // Check if there is an original image attribute or hide it
          const originalSrc = previewImg.dataset.originalSrc;
          if (originalSrc && originalSrc !== window.location.href) {
            previewImg.src = originalSrc;
            previewImg.hidden = false;
          } else {
            previewImg.hidden = true;
          }
        }
      }
    }

    textInput.addEventListener("input", updatePreview);
    textInput.addEventListener("change", updatePreview);

    // Store initial src as original if present
    if (previewImg.src && !previewImg.hidden && previewImg.src !== window.location.href) {
      previewImg.dataset.originalSrc = previewImg.src;
    }
  });
})();
