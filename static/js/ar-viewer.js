(function () {
  const viewer = document.getElementById("mainModelViewer");
  if (!viewer) return;

  const loadingState = document.getElementById("modelLoadingState");
  const errorState = document.getElementById("modelErrorState");
  const title = document.getElementById("modelTitle");
  const description = document.getElementById("modelDescription");
  const projectName = document.getElementById("modelProjectName");
  const thumbnail = document.getElementById("modelThumbnail");
  const size = document.getElementById("modelSize");
  const arButton = viewer.querySelector(".ar-button");

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
    viewer.setAttribute("aria-busy", "false");
    if (loadingState) {
      loadingState.hidden = true;
      loadingState.classList.remove("is-visible");
    }
  }

  function showError() {
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
    setTimeout(updateArButtonAvailability, 250);
  });
  viewer.addEventListener("error", showError);
  viewer.addEventListener("model-visibility", hideLoading);
  viewer.addEventListener("ar-status", (event) => {
    if (!arButton) return;
    if (event.detail && event.detail.status === "failed") {
      arButton.hidden = true;
      return;
    }
    updateArButtonAvailability();
  });

  document.querySelectorAll(".model-switch").forEach((card) => {
    card.addEventListener("click", (event) => {
      const modelUrl = card.dataset.modelUrl;
      if (!modelUrl) return;

      event.preventDefault();
      showLoading();

      viewer.src = modelUrl;
      viewer.poster = card.dataset.thumbnailUrl || "";
      viewer.alt = card.dataset.name || "โมเดลสามมิติ";

      if (title) title.textContent = card.dataset.name || "";
      if (description) description.textContent = card.dataset.description || "โมเดลสามมิติสำหรับการเรียนรู้";
      if (projectName) projectName.textContent = card.dataset.project || "";
      if (size) size.textContent = card.dataset.size || "ไม่ระบุ";

      if (thumbnail) {
        if (card.dataset.thumbnailUrl) {
          thumbnail.src = card.dataset.thumbnailUrl;
          thumbnail.alt = card.dataset.name || "";
          thumbnail.hidden = false;
        } else {
          thumbnail.hidden = true;
        }
      }

      window.history.pushState({}, "", card.href);
    });
  });
})();
