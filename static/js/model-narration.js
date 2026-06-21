document.addEventListener("DOMContentLoaded", () => {
  const narration = document.querySelector("[data-model-narration]");
  if (!narration) return;

  const button = narration.querySelector("[data-narration-toggle]");
  const status = narration.querySelector("[data-narration-status]");
  const speech = window.speechSynthesis;
  const Utterance = window.SpeechSynthesisUtterance;

  if (!button || !status) return;

  const setStatus = (message) => {
    status.textContent = message;
    status.hidden = !message;
  };

  if (!speech || !Utterance) {
    button.disabled = true;
    button.textContent = "อุปกรณ์นี้ไม่รองรับการอ่านออกเสียง";
    setStatus("เบราว์เซอร์นี้ไม่รองรับระบบอ่านคำบรรยาย");
    return;
  }

  let currentUtterance = null;
  let voices = [];

  const updateVoices = () => {
    voices = speech.getVoices();
  };

  const reset = () => {
    currentUtterance = null;
    button.textContent = "ฟังคำบรรยาย";
    button.setAttribute("aria-pressed", "false");
    setStatus("");
  };

  const stop = () => {
    speech.cancel();
    reset();
  };

  const getNarrationText = () => {
    const titleId = narration.dataset.titleSource;
    const descriptionId = narration.dataset.descriptionSource;
    const title = titleId ? document.getElementById(titleId)?.textContent.trim() : "";
    const description = descriptionId
      ? document.getElementById(descriptionId)?.textContent.trim()
      : "";
    return [title, description].filter(Boolean).join(". ");
  };

  const speak = () => {
    const text = getNarrationText();
    if (!text) {
      setStatus("ไม่มีคำบรรยายสำหรับโมเดลนี้");
      return;
    }

    speech.cancel();
    const utterance = new Utterance(text);
    const thaiVoice = voices.find((voice) =>
      String(voice.lang || "").toLowerCase().startsWith("th")
    );

    utterance.lang = "th-TH";
    utterance.rate = 0.95;
    utterance.pitch = 1;
    if (thaiVoice) utterance.voice = thaiVoice;

    utterance.addEventListener("end", reset, { once: true });
    utterance.addEventListener(
      "error",
      (event) => {
        reset();
        if (event.error !== "canceled" && event.error !== "interrupted") {
          setStatus("ไม่สามารถอ่านคำบรรยายได้ กรุณาลองอีกครั้ง");
        }
      },
      { once: true }
    );

    currentUtterance = utterance;
    button.textContent = "หยุดอ่าน";
    button.setAttribute("aria-pressed", "true");
    setStatus("กำลังอ่านคำบรรยาย");
    speech.speak(utterance);
  };

  updateVoices();
  if ("onvoiceschanged" in speech) {
    speech.addEventListener("voiceschanged", updateVoices);
  }

  button.setAttribute("aria-pressed", "false");
  button.addEventListener("click", () => {
    if (currentUtterance) {
      stop();
      return;
    }
    speak();
  });

  window.addEventListener("pagehide", stop, { once: true });
});
