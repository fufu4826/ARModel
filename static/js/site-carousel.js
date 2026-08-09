(function () {
  if (window.__siteCarouselInitialized) return;
  window.__siteCarouselInitialized = true;

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const landingSliderMobileQuery = window.matchMedia("(max-width: 768px)");
  const carouselInstances = new WeakMap();
  let activeHoverCard = null;
  let activeHoverPanelPortal = null;
  let hoverHideTimer = null;

  function pauseCarouselAutoplay(carousel) {
    if (carousel && carousel.autoplay && typeof carousel.autoplay.stop === "function") {
      carousel.autoplay.stop();
    }
  }

  function resumeCarouselAutoplay(carousel) {
    if (!reduceMotion && carousel && carousel.autoplay && typeof carousel.autoplay.start === "function") {
      carousel.autoplay.start();
    }
  }

  function refreshCarousel(carousel) {
    if (!carousel || carousel.destroyed) return;
    carousel.updateSize();
    carousel.updateSlides();
    carousel.updateProgress();
    carousel.updateSlidesClasses();
    if (carousel.navigation && typeof carousel.navigation.update === "function") {
      carousel.navigation.update();
    }
    if (carousel.pagination) {
      if (typeof carousel.pagination.render === "function") carousel.pagination.render();
      if (typeof carousel.pagination.update === "function") carousel.pagination.update();
    }
    carousel.update();
  }

  function makeMarqueeClones(element, originalSlides) {
    const wrapper = element.querySelector(".swiper-wrapper");
    if (!wrapper || originalSlides.length < 2) return originalSlides.length;

    const minimumSlides = Math.max(8, originalSlides.length * 4);
    for (let index = originalSlides.length; index < minimumSlides; index += 1) {
      const clone = originalSlides[index % originalSlides.length].cloneNode(true);
      clone.dataset.marqueeClone = "true";
      clone.removeAttribute("data-hover-panel-ready");
      clone.setAttribute("aria-hidden", "true");
      clone.setAttribute("tabindex", "-1");
      clone.querySelectorAll("a, button, input, select, textarea, [tabindex]").forEach((control) => {
        control.setAttribute("tabindex", "-1");
      });
      wrapper.append(clone);
    }
    return minimumSlides;
  }

  function pauseMarquee(carousel) {
    if (!carousel || carousel.destroyed) return;
    carousel.setTransition(0);
    carousel.setTranslate(carousel.getTranslate());
    pauseCarouselAutoplay(carousel);
  }

  function resumeMarquee(carousel) {
    if (reduceMotion || !carousel || carousel.destroyed) return;
    carousel.setTransition(750);
    carousel.slideNext();
    resumeCarouselAutoplay(carousel);
  }

  function clearActiveHoverCard() {
    if (hoverHideTimer) {
      window.clearTimeout(hoverHideTimer);
      hoverHideTimer = null;
    }
    if (activeHoverPanelPortal) {
      activeHoverPanelPortal.remove();
      activeHoverPanelPortal = null;
    }
    document.querySelectorAll(".site-slide.is-hover-active, .site-slide.site-slide--dialog-return-focus").forEach((card) => {
      card.classList.remove("is-hover-active", "is-hover-portal-active", "site-slide--dialog-return-focus");
      card.style.removeProperty("--slide-hover-panel-left");
      card.style.removeProperty("--slide-hover-panel-top");
    });
    if (activeHoverCard) {
      activeHoverCard.classList.remove("is-hover-active", "is-hover-portal-active", "site-slide--dialog-return-focus");
      activeHoverCard.style.removeProperty("--slide-hover-panel-left");
      activeHoverCard.style.removeProperty("--slide-hover-panel-top");
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
      positionHoverPanelPortal(card);
      return;
    }
    clearActiveHoverCard();
    card.classList.add("is-hover-active");
    createHoverPanelPortal(card);
    activeHoverCard = card;
  }

  function positionHoverPanelPortal(slide) {
    if (!activeHoverPanelPortal || !slide) return;
    if (!window.matchMedia("(hover: hover) and (pointer: fine) and (min-width: 921px)").matches) {
      clearActiveHoverCard();
      return;
    }
    const slideRect = slide.getBoundingClientRect();
    const panelRect = activeHoverPanelPortal.getBoundingClientRect();
    const panelWidth = Math.min(panelRect.width, Math.max(0, window.innerWidth - 32));
    const panelHeight = Math.min(panelRect.height, Math.max(0, window.innerHeight - 32));
    const desiredPanelLeft = slideRect.left + (slideRect.width / 2);
    const clampedPanelLeft = Math.min(
      Math.max(desiredPanelLeft, 16 + (panelWidth / 2)),
      Math.max(16 + (panelWidth / 2), window.innerWidth - 16 - (panelWidth / 2))
    );
    const desiredPanelTop = slideRect.top + (slideRect.height / 2);
    const clampedPanelTop = Math.min(
      Math.max(desiredPanelTop, 16 + (panelHeight / 2)),
      Math.max(16 + (panelHeight / 2), window.innerHeight - 16 - (panelHeight / 2))
    );
    activeHoverPanelPortal.style.left = `${Math.round(clampedPanelLeft)}px`;
    activeHoverPanelPortal.style.top = `${Math.round(clampedPanelTop)}px`;
  }

  function createHoverPanelPortal(slide) {
    const panel = slide.querySelector(".site-slide-hover-panel");
    if (!panel) return;

    const portal = panel.cloneNode(true);
    portal.classList.add("site-slide-hover-panel--portal");
    portal.setAttribute("aria-hidden", "true");
    portal.style.visibility = "hidden";
    document.body.append(portal);
    activeHoverPanelPortal = portal;
    slide.classList.add("is-hover-portal-active");
    positionHoverPanelPortal(slide);
    portal.style.removeProperty("visibility");
  }

  function setupHoverPanel(slide) {
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
      if (activeHoverCard === slide) positionHoverPanelPortal(slide);
    });
  }

  document.querySelectorAll("body:not(.landing-page) .site-slider-section .site-slide").forEach(setupHoverPanel);

  if (window.Swiper) {
    document.querySelectorAll("[data-site-slider]").forEach((element) => {
      const originalSlides = Array.from(element.querySelectorAll(".swiper-wrapper > .swiper-slide"));
      const slideCount = originalSlides.length;
      const isLandingCarousel = Boolean(element.closest(".landing-carousel"));
      const isHomeMarquee = !isLandingCarousel && slideCount > 1 && !reduceMotion;
      const effectiveSlideCount = isHomeMarquee ? makeMarqueeClones(element, originalSlides) : slideCount;
      if (isHomeMarquee) element.classList.add("site-slider--marquee");
      if (isHomeMarquee) {
        element.querySelectorAll(".site-slide").forEach(setupHoverPanel);
      }
      let carousel;
      try {
        carousel = new window.Swiper(element, {
        loop: isHomeMarquee,
        rewind: isLandingCarousel && slideCount > 1,
        speed: isHomeMarquee ? 750 : (reduceMotion ? 0 : 600),
        autoplay: isHomeMarquee
          ? { delay: 5000, disableOnInteraction: false, pauseOnMouseEnter: false, waitForTransition: true }
          : (slideCount > 1 && !reduceMotion ? { delay: 7000, disableOnInteraction: false } : false),
        keyboard: { enabled: true },
        pagination: { el: element.querySelector(".swiper-pagination"), clickable: true },
        navigation: {
          nextEl: element.querySelector(".swiper-button-next"),
          prevEl: element.querySelector(".swiper-button-prev"),
        },
        slidesPerView: isHomeMarquee ? "auto" : (isLandingCarousel ? 1 : 3),
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
      } catch (error) {
        return;
      }
      carouselInstances.set(element, carousel);
      if (isHomeMarquee && effectiveSlideCount > 1) {
        let resumeTimer = null;
        const resumeAfterInteraction = () => {
          window.clearTimeout(resumeTimer);
          resumeTimer = window.setTimeout(() => {
            if (!element.matches(":hover") && !element.contains(document.activeElement)) resumeMarquee(carousel);
          }, 120);
        };
        element.addEventListener("pointerenter", () => pauseMarquee(carousel));
        element.addEventListener("pointerleave", resumeAfterInteraction);
        element.addEventListener("focusin", () => pauseMarquee(carousel));
        element.addEventListener("focusout", resumeAfterInteraction);
        carousel.on("touchStart", () => pauseMarquee(carousel));
        carousel.on("touchEnd", resumeAfterInteraction);
        element.querySelectorAll("img").forEach((image) => {
          image.addEventListener("load", () => refreshCarousel(carousel), { once: true });
          image.addEventListener("error", () => refreshCarousel(carousel), { once: true });
        });
      }
      if (element.closest("[data-landing-slider-region][hidden]") && !landingSliderMobileQuery.matches) {
        pauseCarouselAutoplay(carousel);
      }
    });
  }

  document.querySelectorAll("[data-landing-slider-toggle]").forEach((toggle) => {
    const regionId = toggle.getAttribute("aria-controls");
    const region = regionId ? document.getElementById(regionId) : null;
    const slider = region ? region.querySelector("[data-site-slider]") : null;
    if (!region || !slider) return;

    function setCollapsed(collapsed, focusToggle = true) {
      if (collapsed) {
        pauseCarouselAutoplay(carouselInstances.get(slider));
        region.hidden = true;
        toggle.setAttribute("aria-expanded", "false");
        toggle.textContent = "ข่าวสาร";
        if (focusToggle) toggle.focus({ preventScroll: true });
        return;
      }

      region.hidden = false;
      toggle.setAttribute("aria-expanded", "true");
      toggle.textContent = "ปิดสไลด์";
      window.requestAnimationFrame(() => {
        const carousel = carouselInstances.get(slider);
        refreshCarousel(carousel);
        resumeCarouselAutoplay(carousel);
      });
    }

    toggle.addEventListener("click", () => {
      setCollapsed(!region.hidden);
    });

    function synchronizeMobileVisibility() {
      if (landingSliderMobileQuery.matches) {
        setCollapsed(false, false);
      } else if (region.hidden === false && toggle.getAttribute("aria-expanded") === "true") {
        setCollapsed(true, false);
      }
    }

    synchronizeMobileVisibility();
    landingSliderMobileQuery.addEventListener("change", synchronizeMobileVisibility);
  });

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
    const sectionSlider = section.querySelector("[data-site-slider]");
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
      if (sectionSlider?.classList.contains("site-slider--marquee")) {
        resumeMarquee(carouselInstances.get(sectionSlider));
      }

      if (returnFocus && lastTrigger && lastTrigger.isConnected) {
        lastTrigger.classList.add("site-slide--dialog-return-focus");
        lastTrigger.focus({ preventScroll: true });
      } else if (dialog.contains(document.activeElement)) {
        document.activeElement.blur();
      }
    }

    function openDialog(trigger) {
      clearActiveHoverCard();
      if (sectionSlider?.classList.contains("site-slider--marquee")) {
        pauseMarquee(carouselInstances.get(sectionSlider));
      }
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
