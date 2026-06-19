(function () {
  document.querySelectorAll("input[type='file']").forEach((input) => {
    const preview = document.querySelector(`[data-image-preview="${input.id}"]`);
    if (!preview) return;

    input.addEventListener("change", () => {
      const file = input.files && input.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) {
        input.value = "";
        window.alert("ไฟล์ต้องมีขนาดไม่เกิน 5 MB");
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
})();
