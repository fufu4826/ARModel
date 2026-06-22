(function () {
  function initialize() {
    const preview = document.querySelector("[data-landing-preview]");
    if (!preview) return;

    const form = preview.closest("form");
    if (!form) return;

    const previewFrame = preview.querySelector("[data-landing-preview-frame]");
    const previewFrameShell = previewFrame.closest(".admin-preview-frame-shell");
    const coverFile = form.querySelector("#landing-cover-file");
    const coverValue = form.querySelector("#landing-cover-value");
    let coverObjectUrl = "";
    let previewDocument = null;
    let previewResizeObserver = null;

    const fields = {
      headline: form.querySelector("#landing-headline"),
      subheadline: form.querySelector("#landing-subheadline"),
      description: form.querySelector("#landing-description"),
      primary: form.querySelector("#landing-cta-text"),
      textWidth: form.querySelector("#landing-text-max-width-desktop"),
      headlineSize: form.querySelector("#landing-headline-font-size-desktop"),
      subheadlineSize: form.querySelector("#landing-subheadline-font-size-desktop"),
      descriptionSize: form.querySelector("#landing-description-font-size-desktop"),
      badgeSize: form.querySelector("#landing-badge-font-size-desktop"),
      buttonSize: form.querySelector("#landing-button-font-size-desktop"),
    };

    function clampField(field, minimum, maximum, fallback) {
      const value = Number.parseFloat(field && field.value);
      if (!Number.isFinite(value)) return fallback;
      return Math.min(maximum, Math.max(minimum, Math.round(value)));
    }

    function resolveAssetUrl(value) {
      const path = String(value || "").trim();
      if (!path) return "";
      if (/^(https?:|data:|blob:)/i.test(path) || path.startsWith("/")) return path;
      return `/static/${path.replace(/^static\//, "")}`;
    }

    function previewElements() {
      if (!previewDocument) return null;
      return {
        root: previewDocument.querySelector("[data-preview-root]"),
        badge: previewDocument.querySelector("[data-preview-badge]"),
        headline: previewDocument.querySelector("[data-preview-headline]"),
        subheadline: previewDocument.querySelector("[data-preview-subheadline]"),
        description: previewDocument.querySelector("[data-preview-description]"),
        primary: previewDocument.querySelector("[data-preview-primary]"),
      };
    }

    function setBackground(root, url) {
      const resolvedUrl = resolveAssetUrl(url);
      const backgroundValue = resolvedUrl ? `url(${JSON.stringify(resolvedUrl)})` : "none";
      root.style.setProperty("--landing-image", backgroundValue);
      root.style.setProperty("--landing-cover-desktop", backgroundValue);
    }

    function resizePreviewFrame() {
      if (!previewFrameShell) return;
      const scale = Math.min(1, previewFrameShell.clientWidth / 1180);
      previewFrameShell.style.setProperty("--admin-preview-scale", String(scale));
      previewFrameShell.style.height = `${Math.round(680 * scale)}px`;
    }

    function updatePreview() {
      const elements = previewElements();
      if (!elements || !elements.root) return;

      elements.badge.textContent = preview.dataset.defaultBadge || "นิทรรศการดิจิทัล 3D / AR";
      elements.headline.textContent = fields.headline.value.trim() || "หัวข้อหน้าปก";
      elements.subheadline.textContent = fields.subheadline.value.trim() || "หัวข้อรองหน้าปก";
      elements.description.textContent = fields.description.value.trim() || "คำอธิบายหน้าปก";
      elements.primary.textContent = fields.primary.value.trim() || "เข้าสู่เว็บไซต์";

      elements.root.style.setProperty(
        "--landing-text-max-width-desktop",
        `${clampField(fields.textWidth, 320, 900, 520)}px`
      );
      elements.root.style.setProperty(
        "--landing-headline-font-size-desktop",
        `${clampField(fields.headlineSize, 28, 96, 56)}px`
      );
      elements.root.style.setProperty(
        "--landing-subheadline-font-size-desktop",
        `${clampField(fields.subheadlineSize, 18, 56, 28)}px`
      );
      elements.root.style.setProperty(
        "--landing-description-font-size-desktop",
        `${clampField(fields.descriptionSize, 14, 28, 18)}px`
      );
      elements.root.style.setProperty(
        "--landing-badge-font-size-desktop",
        `${clampField(fields.badgeSize, 10, 22, 14)}px`
      );
      elements.root.style.setProperty(
        "--landing-button-font-size-desktop",
        `${clampField(fields.buttonSize, 12, 24, 16)}px`
      );

      if (!coverObjectUrl) {
        setBackground(elements.root, coverValue.value || preview.dataset.currentCoverUrl);
      }
    }

    Object.values(fields).forEach((field) => {
      if (!field) return;
      field.addEventListener("input", updatePreview);
      field.addEventListener("change", updatePreview);
    });

    if (coverValue) {
      coverValue.addEventListener("input", updatePreview);
      coverValue.addEventListener("change", updatePreview);
    }

    if (coverFile) {
      coverFile.addEventListener("change", () => {
        if (coverObjectUrl) {
          URL.revokeObjectURL(coverObjectUrl);
          coverObjectUrl = "";
        }
        const file = coverFile.files && coverFile.files[0];
        if (file) {
          coverObjectUrl = URL.createObjectURL(file);
          const elements = previewElements();
          if (elements && elements.root) setBackground(elements.root, coverObjectUrl);
        } else {
          updatePreview();
        }
      });
    }

    previewFrame.addEventListener("load", () => {
      previewDocument = previewFrame.contentDocument;
      resizePreviewFrame();
      updatePreview();
    });
    if (previewFrame.contentDocument && previewFrame.contentDocument.readyState === "complete") {
      previewDocument = previewFrame.contentDocument;
    }

    if ("ResizeObserver" in window && previewFrameShell) {
      previewResizeObserver = new ResizeObserver(resizePreviewFrame);
      previewResizeObserver.observe(previewFrameShell);
    } else {
      window.addEventListener("resize", resizePreviewFrame);
    }

    window.addEventListener("pagehide", () => {
      if (coverObjectUrl) URL.revokeObjectURL(coverObjectUrl);
      if (previewResizeObserver) previewResizeObserver.disconnect();
    });

    resizePreviewFrame();
    updatePreview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
