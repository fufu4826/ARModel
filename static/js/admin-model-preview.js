(function () {
  const root = document.querySelector("[data-admin-model-preview-root]");
  if (!root) return;

  const modelViewer = root.querySelector("[data-admin-model-preview]");
  const placeholder = root.querySelector("[data-admin-model-preview-placeholder]");

  const fileInput = document.getElementById("edit-model-file") || document.getElementById("model-file");
  const pathInput = document.getElementById("edit-model-path") || document.getElementById("model-path");
  const urlInput = document.getElementById("edit-model-url") || document.getElementById("model-url");
  const scaleInput = document.getElementById("edit-model-scale") || document.getElementById("scale");
  const rotateInput = document.getElementById("edit-model-rotate-x") || document.getElementById("rotate-x");

  let currentBlobUrl = null;
  let lastSrc = "";
  let lastScale = null;
  let lastRotateX = null;

  function updatePreview() {
    let modelSrc = "";

    // 1. Check local file input first (immediate local file preview)
    if (fileInput && fileInput.files && fileInput.files[0]) {
      const file = fileInput.files[0];
      // Only regenerate blob URL if file changes
      if (!currentBlobUrl || currentBlobUrl.fileName !== file.name) {
        if (currentBlobUrl) {
          URL.revokeObjectURL(currentBlobUrl.url);
        }
        currentBlobUrl = {
          url: URL.createObjectURL(file),
          fileName: file.name
        };
      }
      modelSrc = currentBlobUrl.url;
    } else {
      // Clean up old blob if file selection is cleared
      if (currentBlobUrl) {
        URL.revokeObjectURL(currentBlobUrl.url);
        currentBlobUrl = null;
      }

      // 2. Check external model URL field
      if (urlInput && urlInput.value.trim()) {
        modelSrc = urlInput.value.trim();
      }
      // 3. Fallback to local model path field
      else if (pathInput && pathInput.value.trim()) {
        modelSrc = pathInput.value.trim();
      }
    }

    // Resolve relative path for static directory
    if (modelSrc && !modelSrc.startsWith("http://") && !modelSrc.startsWith("https://") && !modelSrc.startsWith("/") && !modelSrc.startsWith("blob:")) {
      if (modelSrc.startsWith("static/")) {
        modelSrc = "/" + modelSrc;
      }
    }

    // Parse Scale & Rotation values safely
    let scale = 0.2;
    if (scaleInput && scaleInput.value) {
      const parsedScale = parseFloat(scaleInput.value);
      if (!isNaN(parsedScale) && parsedScale > 0) {
        scale = parsedScale;
      }
    }

    let rotateX = 0;
    if (rotateInput && rotateInput.value) {
      const parsedRotateX = parseFloat(rotateInput.value);
      if (!isNaN(parsedRotateX)) {
        rotateX = parsedRotateX;
      }
    }

    // Apply only if changed to prevent model-viewer reload loops
    if (modelSrc !== lastSrc) {
      lastSrc = modelSrc;
      if (modelSrc) {
        modelViewer.setAttribute("src", modelSrc);
        modelViewer.style.display = "block";
        if (placeholder) {
          placeholder.style.display = "none";
        }
      } else {
        modelViewer.removeAttribute("src");
        modelViewer.style.display = "none";
        if (placeholder) {
          placeholder.style.display = "flex";
        }
      }
    }

    if (scale !== lastScale) {
      lastScale = scale;
      modelViewer.setAttribute("scale", `${scale} ${scale} ${scale}`);
    }

    if (rotateX !== lastRotateX) {
      lastRotateX = rotateX;
      modelViewer.setAttribute("orientation", `${rotateX}rad 0rad 0rad`);
    }
  }

  // Setup Event Listeners
  if (fileInput) {
    fileInput.addEventListener("change", updatePreview);
  }
  if (pathInput) {
    pathInput.addEventListener("input", updatePreview);
    pathInput.addEventListener("change", updatePreview);
  }
  if (urlInput) {
    urlInput.addEventListener("input", updatePreview);
    urlInput.addEventListener("change", updatePreview);
  }
  if (scaleInput) {
    scaleInput.addEventListener("input", updatePreview);
    scaleInput.addEventListener("change", updatePreview);
  }
  if (rotateInput) {
    rotateInput.addEventListener("input", updatePreview);
    rotateInput.addEventListener("change", updatePreview);
  }

  // Poll for programmatic direct upload values
  const pollInterval = setInterval(updatePreview, 500);

  // Initial trigger
  updatePreview();

  // Clean up interval on page unload
  window.addEventListener("unload", () => {
    clearInterval(pollInterval);
    if (currentBlobUrl) {
      URL.revokeObjectURL(currentBlobUrl.url);
    }
  });
})();
