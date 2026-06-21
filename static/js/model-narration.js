document.addEventListener("DOMContentLoaded", () => {
  const controls = Array.from(document.querySelectorAll("[data-model-narration]"));
  if (!controls.length) return;

  const supported =
    "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  const speech = supported ? window.speechSynthesis : null;
  let cachedVoices = [];
  let activeUtterance = null;
  let activeControl = null;

  const getVoices = () => {
    if (!speech) return [];
    const voices = speech.getVoices();
    return Array.isArray(voices) ? voices : [];
  };

  const refreshVoices = () => {
    cachedVoices = getVoices();
  };

  const selectThaiVoice = () =>
    cachedVoices.find((voice) =>
      String(voice.lang || "").toLowerCase().startsWith("th")
    ) ||
    cachedVoices.find((voice) =>
      String(voice.name || "").toLowerCase().includes("thai")
    ) ||
    null;

  const setStatus = (control, message) => {
    control.status.textContent = message;
    control.status.hidden = !message;
  };

  const resetControl = (control, statusMessage = "") => {
    control.button.textContent = "ฟังคำบรรยาย";
    control.button.setAttribute("aria-pressed", "false");
    setStatus(control, statusMessage);
  };

  const clearActiveSpeech = (statusMessage = "") => {
    const previousControl = activeControl;
    activeUtterance = null;
    activeControl = null;
    if (previousControl) resetControl(previousControl, statusMessage);
  };

  const cancelSpeech = (statusMessage = "") => {
    if (speech) speech.cancel();
    clearActiveSpeech(statusMessage);
  };

  const getNarrationText = (element) => {
    const titleId = element.dataset.titleSource;
    const descriptionId = element.dataset.descriptionSource;
    const title = titleId
      ? document.getElementById(titleId)?.textContent?.trim()
      : "";
    const description = descriptionId
      ? document.getElementById(descriptionId)?.textContent?.trim()
      : "";
    return [title, description].filter(Boolean).join(". ").trim();
  };

  const startNarration = (control) => {
    const text = getNarrationText(control.element);
    if (!text) {
      control.button.disabled = true;
      setStatus(control, "ไม่มีคำบรรยายสำหรับโมเดลนี้");
      return;
    }

    setStatus(control, "กำลังเตรียมเสียง...");
    speech.cancel();

    const utterance = new window.SpeechSynthesisUtterance(text);
    const thaiVoice = selectThaiVoice();
    utterance.lang = "th-TH";
    utterance.rate = 0.95;
    utterance.pitch = 1;
    if (thaiVoice) utterance.voice = thaiVoice;

    utterance.onstart = () => {
      if (activeUtterance !== utterance) return;
      setStatus(control, "กำลังอ่านคำบรรยาย...");
    };

    utterance.onend = () => {
      if (activeUtterance !== utterance) return;
      clearActiveSpeech("อ่านจบแล้ว");
    };

    utterance.onerror = (event) => {
      if (activeUtterance !== utterance) return;
      const canceled = event.error === "canceled" || event.error === "interrupted";
      clearActiveSpeech(
        canceled ? "" : "อ่านคำบรรยายไม่สำเร็จบนอุปกรณ์นี้"
      );
      if (!canceled) {
        console.warn("Model narration failed:", event.error || "unknown error");
      }
    };

    activeUtterance = utterance;
    activeControl = control;
    control.button.textContent = "หยุดอ่าน";
    control.button.setAttribute("aria-pressed", "true");

    try {
      speech.speak(utterance);
      if (typeof speech.resume === "function") speech.resume();
    } catch (error) {
      if (activeUtterance === utterance) {
        clearActiveSpeech("อ่านคำบรรยายไม่สำเร็จบนอุปกรณ์นี้");
      }
      console.warn("Unable to start model narration:", error);
    }
  };

  const narrationControls = controls
    .map((element) => ({
      element,
      button: element.querySelector("[data-narration-toggle]"),
      status: element.querySelector("[data-narration-status]"),
    }))
    .filter((control) => control.button && control.status);

  if (!supported) {
    narrationControls.forEach((control) => {
      control.button.disabled = true;
      control.button.textContent = "อุปกรณ์นี้ไม่รองรับการอ่านออกเสียง";
      setStatus(control, "อุปกรณ์นี้ไม่รองรับการอ่านออกเสียง");
    });
    console.warn("Web Speech API is unavailable on this device.");
    return;
  }

  refreshVoices();
  if ("onvoiceschanged" in speech) {
    if (typeof speech.addEventListener === "function") {
      speech.addEventListener("voiceschanged", refreshVoices);
    } else {
      speech.onvoiceschanged = refreshVoices;
    }
  }

  narrationControls.forEach((control) => {
    control.button.disabled = !getNarrationText(control.element);
    control.button.setAttribute("aria-pressed", "false");
    if (control.button.disabled) {
      setStatus(control, "ไม่มีคำบรรยายสำหรับโมเดลนี้");
    }

    control.button.addEventListener("click", () => {
      if (activeControl === control && activeUtterance) {
        cancelSpeech("");
        return;
      }

      if (activeUtterance) cancelSpeech("");
      startNarration(control);
    });
  });

  const stopOnNavigation = () => {
    if (speech) speech.cancel();
    activeUtterance = null;
    activeControl = null;
  };

  window.addEventListener("pagehide", stopOnNavigation);
  window.addEventListener("beforeunload", stopOnNavigation);
});
