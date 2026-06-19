(function () {
  const viewer = document.getElementById("mainModelViewer");
  if (!viewer) return;

  const loadingState = document.getElementById("modelLoadingState");
  const errorState = document.getElementById("modelErrorState");
  const arButton = viewer.querySelector(".ar-button");
  const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let loadTimeout = window.setTimeout(showError, 30000);

  if (prefersReducedMotion) {
    viewer.removeAttribute("auto-rotate");
  }

  if (!window.customElements) {
    showError();
  } else if (!window.customElements.get("model-viewer")) {
    window.customElements.whenDefined("model-viewer").catch(showError);
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
    console.warn("Unable to load 3D model:", viewer.src);
    if (errorState) {
      errorState.hidden = false;
      errorState.classList.add("is-visible");
    }
  }

  function updateArButtonAvailability() {
    if (!arButton || !("canActivateAR" in viewer)) return;
    arButton.hidden = viewer.canActivateAR === false;
  }

  viewer.addEventListener("load", () => {
    hideLoading();
    hideError();
    setTimeout(updateArButtonAvailability, 250);
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
})();
