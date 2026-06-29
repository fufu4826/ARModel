(function () {
  const viewer = document.getElementById("mainModelViewer");
  if (!viewer) return;

  const loadingState = document.getElementById("modelLoadingState");
  const errorState = document.getElementById("modelErrorState");
  const arButton = viewer.querySelector(".ar-button");
  const modelSource = viewer.dataset.modelSrc || "";
  const shouldAutoActivateAr = viewer.dataset.autoAr === "true";
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let loadTimeout = null;
  let loadStarted = false;
  let autoArActivated = false;

  if (prefersReducedMotion) {
    viewer.removeAttribute("auto-rotate");
  }

  function clearLoadTimeout() {
    if (loadTimeout) {
      window.clearTimeout(loadTimeout);
      loadTimeout = null;
    }
  }

  function showLoading() {
    viewer.setAttribute("aria-busy", "true");
    if (loadingState) {
      loadingState.hidden = false;
      loadingState.classList.add("is-visible");
    }
    if (errorState) {
      errorState.hidden = true;
      errorState.classList.remove("is-visible");
    }
  }

  function hideLoading() {
    clearLoadTimeout();
    viewer.setAttribute("aria-busy", "false");
    if (loadingState) {
      loadingState.hidden = true;
      loadingState.classList.remove("is-visible");
    }
  }

  function hideError() {
    if (errorState) {
      errorState.hidden = true;
      errorState.classList.remove("is-visible");
    }
  }

  function showError() {
    clearLoadTimeout();
    hideLoading();
    console.warn("Unable to load 3D model:", modelSource);
    if (errorState) {
      errorState.hidden = false;
      errorState.classList.add("is-visible");
    }
  }

  function updateArButtonAvailability() {
    if (!arButton || !("canActivateAR" in viewer)) return;
    arButton.hidden = viewer.canActivateAR === false;
  }

  function startModelLoad() {
    if (loadStarted) return;
    loadStarted = true;
    if (!modelSource) {
      showError();
      return;
    }

    showLoading();
    loadTimeout = window.setTimeout(showError, 30000);

    // Assign the GLB URL once and only near the viewport. This prevents
    // hidden/off-screen viewers from consuming Supabase egress.
    viewer.src = modelSource;
  }

  viewer.addEventListener("load", () => {
    hideLoading();
    hideError();
    setTimeout(updateArButtonAvailability, 250);
    if (shouldAutoActivateAr && !autoArActivated && viewer.activateAR) {
      autoArActivated = true;
      viewer.activateAR();
    }
  });
  viewer.addEventListener("error", showError);
  viewer.addEventListener("model-visibility", () => {
    hideLoading();
    hideError();
  });
  viewer.addEventListener("ar-status", (event) => {
    if (!arButton) return;
    if (event.detail && event.detail.status === "failed") {
      arButton.hidden = true;
      return;
    }
    updateArButtonAvailability();
  });

  if (!window.customElements) {
    showError();
    return;
  }

  window.customElements.whenDefined("model-viewer").then(() => {
    if (!("IntersectionObserver" in window)) {
      startModelLoad();
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) return;
        observer.disconnect();
        startModelLoad();
      },
      { rootMargin: "200px 0px" }
    );
    observer.observe(viewer);
  }).catch(showError);
})();
