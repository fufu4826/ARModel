(function () {
  if (window.__siteCarouselInitialized) return;
  window.__siteCarouselInitialized = true;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let activeHoverCard = null;
  let hoverHideTimer = null;

  function clearActiveHoverCard() {
    if (hoverHideTimer) {
      window.clearTimeout(hoverHideTimer);
      hoverHideTimer = null;
    }
    document.querySelectorAll(".site-slide.is-hover-active, .site-slide.site-slide--dialog-return-focus").forEach((card) => {
      card.classList.remove("is-hover-active", "site-slide--dialog-return-focus");
      card.style.removeProperty("--slide-hover-panel-left");
    });
    if (activeHoverCard) {
      activeHoverCard.classList.remove("is-hover-active", "site-slide--dialog-return-focus");
      activeHoverCard.style.removeProperty("--slide-hover-panel-left");
      activeHoverCard = null;
    }
  }

  function setActiveHoverCard(card) {
    if (!card || document.body.classList.contains("landing-page")) {
      clearActiveHoverCard();
      return;
    }
    if (!window.matchMedia("(hover: hover) and (pointer: fine) and (min-width: 921px)").matches) {
      clearActiveHoverCard();
      return;
    }
    if (activeHoverCard === card) {
      updateHoverPanelPosition(card);
      return;
    }
    clearActiveHoverCard();
    updateHoverPanelPosition(card);
    card.classList.add("is-hover-active");
    activeHoverCard = card;
  }

  function updateHoverPanelPosition(slide) {
    if (document.body.classList.contains("landing-page")) return;
    const panel = slide.querySelector(".site-slide-hover-panel");
    if (!panel || !window.matchMedia("(hover: hover) and (pointer: fine) and (min-width: 921px)").matches) {
      slide.style.removeProperty("--slide-hover-panel-left");
      return;
    }
    const slideRect = slide.getBoundingClientRect();
    const panelWidth = Math.min(460, Math.max(0, window.innerWidth - 32));
    const desiredPanelLeft = slideRect.left + (slideRect.width / 2) - (panelWidth / 2);
    const clampedPanelLeft = Math.min(
      Math.max(desiredPanelLeft, 16),
      Math.max(16, window.innerWidth - panelWidth - 16)
    );
    const panelCenterWithinSlide = clampedPanelLeft - slideRect.left + (panelWidth / 2);
    slide.style.setProperty("--slide-hover-panel-left", `${Math.round(panelCenterWithinSlide)}px`);
  }

  document.querySelectorAll("body:not(.landing-page) .site-slider-section .site-slide").forEach((slide) => {
    if (slide.dataset.hoverPanelReady === "true") return;
    slide.dataset.hoverPanelReady = "true";
    slide.addEventListener("pointerenter", (event) => {
      if (event.pointerType === "touch") {
        clearActiveHoverCard();
        return;
      }
      setActiveHoverCard(slide);
    });
    slide.addEventListener("pointerleave", () => {
      if (activeHoverCard === slide) clearActiveHoverCard();
    });
    slide.addEventListener("pointercancel", clearActiveHoverCard);
    slide.addEventListener("touchstart", clearActiveHoverCard, { passive: true });
    slide.addEventListener("blur", () => {
      slide.classList.remove("site-slide--dialog-return-focus");
    });
    window.addEventListener("resize", () => {
      if (activeHoverCard === slide) updateHoverPanelPosition(slide);
    });
  });

  if (window.Swiper) {
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
        on: {
          slideChange: clearActiveHoverCard,
          touchStart: clearActiveHoverCard,
          sliderMove: clearActiveHoverCard,
        },
      });
    });
  }

  window.addEventListener("blur", clearActiveHoverCard);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) clearActiveHoverCard();
  });

  document.querySelectorAll(".site-slider-section").forEach((section) => {
    if (section.dataset.slideDialogReady === "true") return;
    section.dataset.slideDialogReady = "true";
    const dialog = section.querySelector("[data-slide-dialog]");
    if (!dialog) return;
    const image = dialog.querySelector("[data-slide-dialog-image]");
    const title = dialog.querySelector("[data-slide-dialog-title]");
    const description = dialog.querySelector("[data-slide-dialog-description]");
    const link = dialog.querySelector("[data-slide-dialog-link]");
    const closeButtons = dialog.querySelectorAll("[data-slide-dialog-close]");
    let lastTrigger = null;

    function unlockPageScroll() {
      document.documentElement.classList.remove("slide-dialog-open");
      document.body.classList.remove("slide-dialog-open");
      document.documentElement.style.removeProperty("overflow");
      document.body.style.removeProperty("overflow");
    }

    function lockPageScroll() {
      document.documentElement.classList.add("slide-dialog-open");
      document.body.classList.add("slide-dialog-open");
    }

    function closeDialog(options = {}) {
      const { returnFocus = true } = options;
      clearActiveHoverCard();
      dialog.classList.remove("site-slide-modal--open");
      dialog.hidden = true;
      dialog.setAttribute("aria-hidden", "true");
      unlockPageScroll();
      image.hidden = true;
      image.removeAttribute("src");

      if (returnFocus && lastTrigger && lastTrigger.isConnected) {
        lastTrigger.classList.add("site-slide--dialog-return-focus");
        lastTrigger.focus({ preventScroll: true });
      } else if (dialog.contains(document.activeElement)) {
        document.activeElement.blur();
      }
    }

    function openDialog(trigger) {
      clearActiveHoverCard();
      const slideImage = trigger.querySelector("img");
      const slideTitle = trigger.querySelector(".site-slide-content h2");
      const slideDescription = trigger.querySelector(".site-slide-content p");
      const slideLink = trigger.querySelector(".site-slide-content .button");
      lastTrigger = trigger;

      title.textContent = slideTitle ? slideTitle.textContent.trim() : "";
      if (slideImage && slideImage.currentSrc) {
        image.src = slideImage.currentSrc;
        image.alt = slideImage.alt || title.textContent;
        image.hidden = false;
      } else {
        image.hidden = true;
        image.removeAttribute("src");
      }
      if (slideDescription && slideDescription.textContent.trim()) {
        description.textContent = slideDescription.textContent.trim();
        description.hidden = false;
      } else {
        description.textContent = "";
        description.hidden = true;
      }
      if (slideLink && slideLink.href && slideLink.textContent.trim()) {
        link.href = slideLink.href;
        link.textContent = slideLink.textContent.trim();
        link.hidden = false;
      } else {
        link.hidden = true;
        link.removeAttribute("href");
        link.textContent = "";
      }

      trigger.classList.remove("site-slide--dialog-return-focus");
      dialog.hidden = false;
      dialog.setAttribute("aria-hidden", "false");
      dialog.classList.add("site-slide-modal--open");
      lockPageScroll();
      const closeButton = dialog.querySelector(".site-slide-modal__close");
      if (closeButton) closeButton.focus();
    }

    section.querySelectorAll("[data-slide-dialog-trigger]").forEach((trigger) => {
      trigger.addEventListener("click", (event) => {
        if (event.target.closest(".swiper-button-prev, .swiper-button-next, .swiper-pagination, a")) return;
        openDialog(trigger);
      });
      trigger.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        openDialog(trigger);
      });
    });

    closeButtons.forEach((button) => button.addEventListener("click", closeDialog));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !dialog.hidden) closeDialog();
    });
  });
})();
