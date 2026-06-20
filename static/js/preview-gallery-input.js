(function () {
  function previewUrl(value) {
    if (/^https?:\/\//i.test(value) || value.startsWith("/")) return value;
    return `/static/${value.replace(/^static\//, "")}`;
  }

  document.querySelectorAll("[data-gallery-input]").forEach((input) => {
    const preview = input.form && input.form.querySelector("[data-gallery-input-preview]");
    if (!preview) return;

    function render() {
      preview.replaceChildren();
      const urls = input.value
        .split(/\r?\n/)
        .map((value) => value.trim())
        .filter(Boolean);

      urls.forEach((url, index) => {
        const image = document.createElement("img");
        image.src = previewUrl(url);
        image.alt = `ตัวอย่างรูปที่ ${index + 1}`;
        image.loading = "lazy";
        image.addEventListener("error", () => image.remove(), { once: true });
        preview.appendChild(image);
      });
    }

    input.addEventListener("input", render);
    render();
  });
})();
