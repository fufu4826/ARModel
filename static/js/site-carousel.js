(function () {
  if (!window.Swiper) return;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  document.querySelectorAll("[data-site-slider]").forEach((element) => {
    const slideCount = element.querySelectorAll(".swiper-slide").length;
    const isLandingCarousel = Boolean(element.closest(".landing-carousel"));
    new window.Swiper(element, {
      loop: slideCount > 1,
      speed: reduceMotion ? 0 : 600,
      autoplay: slideCount > 1 && !reduceMotion ? { delay: 7000, disableOnInteraction: false } : false,
      keyboard: { enabled: true },
      pagination: { el: element.querySelector(".swiper-pagination"), clickable: true },
      navigation: {
        nextEl: element.querySelector(".swiper-button-next"),
        prevEl: element.querySelector(".swiper-button-prev"),
      },
      slidesPerView: isLandingCarousel ? 1 : 3,
      spaceBetween: isLandingCarousel ? 0 : 18,
      breakpoints: isLandingCarousel ? {} : {
        921: {
          slidesPerView: 4,
          spaceBetween: 20,
        },
      },
    });
  });
})();
