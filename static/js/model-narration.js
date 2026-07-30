document.addEventListener("DOMContentLoaded", () => {
  const elements = Array.from(document.querySelectorAll("[data-model-narration]"));
  if (!elements.length) return;

  const speechSupported =
    "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  const speech = speechSupported ? window.speechSynthesis : null;
  let voices = [];
  let activeUtterance = null;
  let activeAudio = null;
  let activeControl = null;
  let speechStartTimer = null;

  const controls = elements
    .map((element) => ({
      element,
      button: element.querySelector("[data-narration-toggle]"),
      status: element.querySelector("[data-narration-status]"),
      audio: element.querySelector("[data-narration-audio]"),
    }))
    .filter((control) => control.button && control.status);

  const setStatus = (control, message) => {
    control.status.textContent = message;
    control.status.hidden = !message;
  };

  const resetButton = (control, message = "") => {
    control.button.textContent = control.element.dataset.narrationLabel || "ฟังคำบรรยาย";
    control.button.setAttribute("aria-pressed", "false");
    setStatus(control, message);
  };

  const clearSpeechTimer = () => {
    if (speechStartTimer) window.clearTimeout(speechStartTimer);
    speechStartTimer = null;
  };

  const clearActive = (message = "") => {
    const previousControl = activeControl;
    clearSpeechTimer();
    activeUtterance = null;
    activeAudio = null;
    activeControl = null;
    if (previousControl) resetButton(previousControl, message);
  };

  const stopActive = (message = "") => {
    clearSpeechTimer();
    if (activeAudio) {
      activeAudio.pause();
      activeAudio.currentTime = 0;
    }
    if (speech) speech.cancel();
    clearActive(message);
  };

  const narrationText = (control) => {
    const titleId = control.element.dataset.titleSource;
    const descriptionId = control.element.dataset.descriptionSource;
    const title = titleId
      ? document.getElementById(titleId)?.textContent?.trim()
      : "";
    const description = descriptionId
      ? document.getElementById(descriptionId)?.textContent?.trim()
      : "";
    return [title, description].filter(Boolean).join(". ").trim();
  };

  const refreshVoices = () => {
    voices = speech ? speech.getVoices() || [] : [];
  };

  const thaiVoice = () =>
    voices.find((voice) =>
      String(voice.lang || "").toLowerCase().startsWith("th")
    ) ||
    voices.find((voice) =>
      String(voice.name || "").toLowerCase().includes("thai")
    ) ||
    null;

  const speakWithBrowser = (control) => {
    const text = narrationText(control);
    if (!speechSupported || !speech) {
      clearActive("อุปกรณ์นี้ไม่รองรับการอ่านออกเสียง และไม่มีไฟล์เสียงคำบรรยาย");
      console.warn("Web Speech API is unavailable on this device.");
      return;
    }
    if (!text) {
      clearActive("ไม่มีคำบรรยายสำหรับโมเดลนี้");
      return;
    }

    setStatus(control, "กำลังเตรียมเสียง...");
    speech.cancel();

    const utterance = new window.SpeechSynthesisUtterance(text);
    const selectedVoice = thaiVoice();
    utterance.lang = "th-TH";
    utterance.rate = 0.9;
    utterance.pitch = 1;
    utterance.volume = 1;
    if (selectedVoice) utterance.voice = selectedVoice;

    let started = false;
    utterance.onstart = () => {
      if (activeUtterance !== utterance) return;
      started = true;
      clearSpeechTimer();
      setStatus(control, "กำลังอ่านคำบรรยาย...");
    };
    utterance.onend = () => {
      if (activeUtterance !== utterance) return;
      clearActive("อ่านจบแล้ว");
    };
    utterance.onerror = (event) => {
      if (activeUtterance !== utterance) return;
      const canceled = event.error === "canceled" || event.error === "interrupted";
      clearActive(canceled ? "" : "อ่านคำบรรยายไม่สำเร็จบนอุปกรณ์นี้");
      if (!canceled) {
        console.warn("Model narration failed:", event.error || "unknown error");
      }
    };

    activeUtterance = utterance;
    activeAudio = null;
    activeControl = control;
    control.button.textContent = "หยุดอ่าน";
    control.button.setAttribute("aria-pressed", "true");

    try {
      speech.speak(utterance);
      if (typeof speech.resume === "function") speech.resume();
      speechStartTimer = window.setTimeout(() => {
        if (
          activeUtterance === utterance &&
          !started &&
          !speech.speaking
        ) {
          speech.cancel();
          clearActive(
            "เครื่องนี้ไม่มีเสียงอ่านภาษาไทย กรุณาใช้ไฟล์เสียงคำบรรยาย"
          );
        }
      }, 1200);
    } catch (error) {
      if (activeUtterance === utterance) {
        clearActive("อ่านคำบรรยายไม่สำเร็จบนอุปกรณ์นี้");
      }
      console.warn("Unable to start model narration:", error);
    }
  };

  const playAudioFile = (control) => {
    if (!control.audio) {
      speakWithBrowser(control);
      return;
    }

    activeControl = control;
    activeAudio = control.audio;
    activeUtterance = null;
    control.audio.currentTime = 0;
    control.button.textContent = "หยุดอ่าน";
    control.button.setAttribute("aria-pressed", "true");
    setStatus(control, "กำลังเตรียมไฟล์เสียง...");

    const fallbackToSpeech = (reason) => {
      if (activeAudio !== control.audio) return;
      control.audio.pause();
      activeAudio = null;
      console.warn("Narration audio playback failed:", reason);
      setStatus(control, "ไฟล์เสียงเล่นไม่ได้ กำลังลองเสียงอ่านจากเบราว์เซอร์...");
      speakWithBrowser(control);
    };

    control.audio.onplaying = () => {
      if (activeAudio === control.audio) {
        setStatus(control, "กำลังเล่นคำบรรยาย...");
      }
    };
    control.audio.onended = () => {
      if (activeAudio === control.audio) clearActive("อ่านจบแล้ว");
    };
    control.audio.onerror = () => fallbackToSpeech("media error");

    try {
      const playResult = control.audio.play();
      if (playResult && typeof playResult.catch === "function") {
        playResult.catch((error) => fallbackToSpeech(error?.message || "play rejected"));
      }
    } catch (error) {
      fallbackToSpeech(error?.message || "play failed");
    }
  };

  if (speechSupported && speech) {
    refreshVoices();
    if ("onvoiceschanged" in speech) {
      if (typeof speech.addEventListener === "function") {
        speech.addEventListener("voiceschanged", refreshVoices);
      } else {
        speech.onvoiceschanged = refreshVoices;
      }
    }
  }

  controls.forEach((control) => {
    const hasText = Boolean(narrationText(control));
    control.button.disabled = !control.audio && (!speechSupported || !hasText);
    control.button.setAttribute("aria-pressed", "false");
    if (control.button.disabled) {
      setStatus(
        control,
        speechSupported
          ? "ไม่มีคำบรรยายสำหรับโมเดลนี้"
          : "อุปกรณ์นี้ไม่รองรับการอ่านออกเสียง และไม่มีไฟล์เสียงคำบรรยาย"
      );
    }

    control.button.addEventListener("click", () => {
      if (activeControl === control && (activeAudio || activeUtterance)) {
        stopActive("");
        return;
      }
      if (activeControl) stopActive("");
      playAudioFile(control);
    });
  });

  const stopOnNavigation = () => {
    clearSpeechTimer();
    if (activeAudio) activeAudio.pause();
    if (speech) speech.cancel();
    activeAudio = null;
    activeUtterance = null;
    activeControl = null;
  };

  window.addEventListener("pagehide", stopOnNavigation);
  window.addEventListener("beforeunload", stopOnNavigation);
});
