(function () {
  const mainImage = document.getElementById("modelGalleryMain");
  if (!mainImage) return;

  const placeholder = mainImage.nextElementSibling;
  const buttons = Array.from(document.querySelectorAll("[data-gallery-image]"));

  function showPlaceholder() {
    mainImage.hidden = true;
    if (placeholder) placeholder.hidden = false;
  }

  function showImage(button) {
    mainImage.hidden = false;
    if (placeholder) placeholder.hidden = true;
    mainImage.src = button.dataset.galleryImage;
    mainImage.alt = button.dataset.galleryAlt;
    buttons.forEach((item) => {
      const active = item === button;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-pressed", String(active));
    });
  }

  mainImage.addEventListener("error", showPlaceholder);
  mainImage.addEventListener("load", () => {
    mainImage.hidden = false;
    if (placeholder) placeholder.hidden = true;
  });
  buttons.forEach((button) => button.addEventListener("click", () => showImage(button)));
})();
