(function () {
  const root = document.querySelector("[data-admin-model-preview-root]");
  if (!root) return;

  const modelViewer = root.querySelector("[data-admin-model-preview]");
  const placeholder = root.querySelector("[data-admin-model-preview-placeholder]");

  const fileInput = document.getElementById("edit-model-file") || document.getElementById("model-file");
  const pathInput = document.getElementById("edit-model-path") || document.getElementById("model-path");
  const urlInput = document.getElementById("edit-model-url") || document.getElementById("model-url");
  const scaleInput = document.getElementById("edit-model-scale") || document.getElementById("scale");
  const rotateXInput = document.getElementById("edit-model-rotate-x") || document.getElementById("rotate-x");
  const rotateYInput = document.getElementById("edit-model-rotate-y") || document.getElementById("rotate-y");
  const rotateZInput = document.getElementById("edit-model-rotate-z") || document.getElementById("rotate-z");

  let currentBlobUrl = null;
  let lastSrc = "";
  let lastScale = null;
  let lastRotateX = null;
  let lastRotateY = null;
  let lastRotateZ = null;

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
    if (rotateXInput && rotateXInput.value) {
      const parsedRotateX = parseFloat(rotateXInput.value);
      if (!isNaN(parsedRotateX)) {
        rotateX = parsedRotateX;
      }
    }

    let rotateY = 0;
    if (rotateYInput && rotateYInput.value) {
      const parsedRotateY = parseFloat(rotateYInput.value);
      if (!isNaN(parsedRotateY)) {
        rotateY = parsedRotateY;
      }
    }

    let rotateZ = 0;
    if (rotateZInput && rotateZInput.value) {
      const parsedRotateZ = parseFloat(rotateZInput.value);
      if (!isNaN(parsedRotateZ)) {
        rotateZ = parsedRotateZ;
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

    if (rotateX !== lastRotateX || rotateY !== lastRotateY || rotateZ !== lastRotateZ) {
      lastRotateX = rotateX;
      lastRotateY = rotateY;
      lastRotateZ = rotateZ;
      modelViewer.setAttribute("orientation", `${rotateX}rad ${rotateY}rad ${rotateZ}rad`);
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
  if (rotateXInput) {
    rotateXInput.addEventListener("input", updatePreview);
    rotateXInput.addEventListener("change", updatePreview);
  }
  if (rotateYInput) {
    rotateYInput.addEventListener("input", updatePreview);
    rotateYInput.addEventListener("change", updatePreview);
  }
  if (rotateZInput) {
    rotateZInput.addEventListener("input", updatePreview);
    rotateZInput.addEventListener("change", updatePreview);
  }

  // Handle Preset Buttons
  const presetButtons = document.querySelectorAll(".preset-btn");
  presetButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const px = btn.getAttribute("data-preset-x");
      const py = btn.getAttribute("data-preset-y");
      const pz = btn.getAttribute("data-preset-z");

      if (px !== null && rotateXInput) {
        rotateXInput.value = px;
        rotateXInput.dispatchEvent(new Event("input"));
        rotateXInput.dispatchEvent(new Event("change"));
      }
      if (py !== null && rotateYInput) {
        rotateYInput.value = py;
        rotateYInput.dispatchEvent(new Event("input"));
        rotateYInput.dispatchEvent(new Event("change"));
      }
      if (pz !== null && rotateZInput) {
        rotateZInput.value = pz;
        rotateZInput.dispatchEvent(new Event("input"));
        rotateZInput.dispatchEvent(new Event("change"));
      }
    });
  });


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
