(function () {
  const triggers = document.querySelectorAll("[data-landing-intro-trigger]");
  const trigger = triggers[0];
  const configElement = document.getElementById("landingIntroConfig");
  const overlay = document.getElementById("landingIntroOverlay");
  const logo = document.getElementById("landingIntroLogo");
  const logoGroup = document.getElementById("landingIntroLogoGroup");
  const skipButton = document.querySelector("[data-landing-intro-skip]");
  if (!trigger || !configElement || !overlay || !logo || !logoGroup || !skipButton) return;

  let config;
  try {
    config = JSON.parse(configElement.textContent || "{}");
  } catch {
    return;
  }

  const preloadUrls = Array.isArray(config.preloadUrls) ? config.preloadUrls.slice(0, 50) : [];
  const logos = Array.isArray(config.logos) ? config.logos.filter(Boolean).slice(0, 3) : [];
  const displayMode = config.mode === "all_at_once" ? "all_at_once" : "sequence";
  const durationMs = Math.max(600, Math.min(Number(config.durationMs) || 1400, 1600));
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const preloadedImages = [];
  let active = false;
  let skipped = false;

  preloadUrls.forEach((url) => {
    const image = new Image();
    image.decoding = "async";
    image.src = url;
    preloadedImages.push(image);
  });

  function wait(milliseconds) {
    return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
  }

  function preloadLogo(url) {
    return new Promise((resolve) => {
      const image = new Image();
      const timeout = window.setTimeout(() => resolve(false), 900);
      image.onload = () => {
        window.clearTimeout(timeout);
        resolve(true);
      };
      image.onerror = () => {
        window.clearTimeout(timeout);
        resolve(false);
      };
      image.src = url;
    });
  }

  function navigate() {
    window.location.assign(trigger.href);
  }

  function skip() {
    if (!active) return;
    skipped = true;
    navigate();
  }

  async function playLogo(url) {
    if (!(await preloadLogo(url)) || skipped) return;
    logo.src = url;
    logo.hidden = false;
    logo.classList.remove("is-visible");
    await new Promise((resolve) => window.requestAnimationFrame(() => {
      window.requestAnimationFrame(resolve);
    }));
    if (skipped) return;
    logo.classList.add("is-visible");
    await wait(Math.round(durationMs * 0.72));
    logo.classList.remove("is-visible");
    await wait(Math.round(durationMs * 0.28));
    logo.hidden = true;
  }

  async function playAllLogos(urls) {
    const validLogos = (
      await Promise.all(
        urls.map(async (url) => ((await preloadLogo(url)) ? url : ""))
      )
    ).filter(Boolean);
    if (!validLogos.length || skipped) return false;

    logoGroup.replaceChildren();
    validLogos.forEach((url, index) => {
      const image = document.createElement("img");
      image.className = "landing-intro-logo-group__item";
      image.src = url;
      image.alt = `โลโก้อินโทร ${index + 1}`;
      image.addEventListener("error", () => image.remove(), { once: true });
      logoGroup.appendChild(image);
    });
    logoGroup.hidden = false;
    logoGroup.classList.remove("is-visible");
    await new Promise((resolve) => window.requestAnimationFrame(() => {
      window.requestAnimationFrame(resolve);
    }));
    if (skipped) return false;
    logoGroup.classList.add("is-visible");
    await wait(Math.round(durationMs * 0.72));
    logoGroup.classList.remove("is-visible");
    await wait(Math.round(durationMs * 0.28));
    logoGroup.hidden = true;
    return true;
  }

  triggers.forEach((trig) => {
    trig.addEventListener("click", async (event) => {
      if (!config.enabled || !logos.length || reducedMotion || active) return;
      event.preventDefault();
      active = true;
      skipped = false;
      overlay.hidden = false;
      overlay.setAttribute("aria-hidden", "false");
      document.body.classList.add("landing-intro-active");
      overlay.dataset.mode = displayMode;
      window.requestAnimationFrame(() => overlay.classList.add("is-active"));
      skipButton.focus();

      try {
        if (displayMode === "all_at_once") {
          await playAllLogos(logos);
        } else {
          for (const url of logos) {
            if (skipped) return;
            await playLogo(url);
          }
        }
        if (!skipped) window.location.assign(trig.href);
      } catch {
        window.location.assign(trig.href);
      }
    });
  });

  skipButton.addEventListener("click", skip);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") skip();
  });
})();
