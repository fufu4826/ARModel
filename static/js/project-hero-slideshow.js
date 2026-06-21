(function () {
  document.querySelectorAll("[data-hero-slideshow]").forEach((slideshow) => {
    const slides = slideshow.querySelectorAll("[data-hero-slide]");
    if (slides.length <= 1) return;

    // Check prefers-reduced-motion
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) return;

    let currentIndex = 0;
    let timer = null;
    const intervalTime = 4000; // Rotate every 4 seconds

    function showSlide(index) {
      slides[currentIndex].classList.remove("is-active");
      currentIndex = index;
      slides[currentIndex].classList.add("is-active");
    }

    function nextSlide() {
      const nextIndex = (currentIndex + 1) % slides.length;
      showSlide(nextIndex);
    }

    function startTimer() {
      if (timer === null) {
        timer = setInterval(nextSlide, intervalTime);
      }
    }

    function stopTimer() {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    }

    // Start auto-play
    startTimer();

    // Pause on hover or focus
    slideshow.addEventListener("mouseenter", stopTimer);
    slideshow.addEventListener("mouseleave", startTimer);
    slideshow.addEventListener("focusin", stopTimer);
    slideshow.addEventListener("focusout", startTimer);
  });
})();
