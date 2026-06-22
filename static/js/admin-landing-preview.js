(function () {
  function initialize() {
    const preview = document.querySelector("[data-landing-preview]");
    if (!preview) return;

    const form = preview.closest("form");
    if (!form) return;

    const previewBg = preview.querySelector("[data-preview-bg]");
    const previewContent = preview.querySelector("[data-preview-content]");
    const previewBadge = preview.querySelector("[data-preview-badge]");
    const previewHeadline = preview.querySelector("[data-preview-headline]");
    const previewSubheadline = preview.querySelector("[data-preview-subheadline]");
    const previewDescription = preview.querySelector("[data-preview-description]");
    const previewPrimary = preview.querySelector("[data-preview-primary]");
    const coverFile = form.querySelector("#landing-cover-file");
    const coverValue = form.querySelector("#landing-cover-value");
    let coverObjectUrl = "";

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

    function setBackground(url) {
      const resolvedUrl = resolveAssetUrl(url);
      previewBg.style.backgroundImage = resolvedUrl
        ? `url(${JSON.stringify(resolvedUrl)})`
        : "none";
    }

    function updatePreview() {
      previewBadge.textContent = preview.dataset.defaultBadge || "นิทรรศการดิจิทัล 3D / AR";
      previewHeadline.textContent = fields.headline.value.trim() || "หัวข้อหน้าปก";
      previewSubheadline.textContent = fields.subheadline.value.trim() || "หัวข้อรองหน้าปก";
      previewDescription.textContent = fields.description.value.trim() || "คำอธิบายหน้าปก";
      previewPrimary.textContent = fields.primary.value.trim() || "เข้าสู่เว็บไซต์";

      previewContent.style.setProperty(
        "--preview-text-width",
        `${clampField(fields.textWidth, 320, 900, 520)}px`
      );
      previewContent.style.setProperty(
        "--preview-headline-size",
        `${clampField(fields.headlineSize, 28, 96, 56)}px`
      );
      previewContent.style.setProperty(
        "--preview-subheadline-size",
        `${clampField(fields.subheadlineSize, 18, 56, 28)}px`
      );
      previewContent.style.setProperty(
        "--preview-description-size",
        `${clampField(fields.descriptionSize, 14, 28, 18)}px`
      );
      previewContent.style.setProperty(
        "--preview-badge-size",
        `${clampField(fields.badgeSize, 10, 22, 14)}px`
      );
      previewContent.style.setProperty(
        "--preview-button-size",
        `${clampField(fields.buttonSize, 12, 24, 16)}px`
      );

      if (!coverObjectUrl) {
        setBackground(coverValue.value || preview.dataset.currentCoverUrl);
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
          setBackground(coverObjectUrl);
        } else {
          updatePreview();
        }
      });
    }

    window.addEventListener("pagehide", () => {
      if (coverObjectUrl) URL.revokeObjectURL(coverObjectUrl);
    });

    updatePreview();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initialize, { once: true });
  } else {
    initialize();
  }
})();
