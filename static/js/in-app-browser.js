// In-app browser notice: when the site is opened inside LINE, Messenger, Facebook, Instagram or TikTok,
// show a large popup with one big button that reopens the same page in the phone's own browser
// (Chrome on Android, Safari on iPhone). In-app browsers often block AR, audio and sharing.
(function () {
  "use strict";
  var ua = navigator.userAgent || "";
  var STAY_KEY = "puparn-inapp-stay";
  var url = new URL(window.location.href);

  // Back in a real browser after LINE's ?openExternalBrowser=1: tidy the address bar.
  function cleanUrl() {
    if (!url.searchParams.has("openExternalBrowser")) return;
    url.searchParams.delete("openExternalBrowser");
    try { history.replaceState(history.state, "", url.pathname + url.search + url.hash); } catch (e) { /* ignore */ }
  }

  var app = null;
  if (/\bLine\//i.test(ua)) app = "LINE";
  else if (/Messenger|Orca-Android|MessengerForiOS|MessengerLite/i.test(ua)) app = "Messenger";
  else if (/FBAN|FBAV|FB_IAB|FB4A|FBIOS|FBMD/i.test(ua)) app = "Facebook";
  else if (/Instagram/i.test(ua)) app = "Instagram";
  else if (/musical_ly|BytedanceWebview|TikTok/i.test(ua)) app = "TikTok";

  if (!app) { cleanUrl(); return; }
  try { if (sessionStorage.getItem(STAY_KEY) === "1") return; } catch (e) { /* storage blocked: still show */ }

  var isIOS = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
  var isAndroid = /Android/i.test(ua);
  var browser = isIOS ? "Safari" : "Chrome";
  var pageUrl = (function () { var u = new URL(url.href); u.searchParams.delete("openExternalBrowser"); return u.href; })();

  function openOutside() {
    if (app === "LINE") {
      // LINE opens any link with this parameter in the phone's default browser (iPhone and Android).
      var u = new URL(pageUrl);
      u.searchParams.set("openExternalBrowser", "1");
      window.location.href = u.href;
      return;
    }
    if (isAndroid) {
      var target = pageUrl.replace(/^https?:\/\//, "");
      window.location.href = "intent://" + target + "#Intent;scheme=https;package=com.android.chrome;S.browser_fallback_url=" +
        encodeURIComponent(pageUrl) + ";end";
      setTimeout(showSteps, 1800);
      return;
    }
    if (isIOS) {
      // Facebook, Messenger and Instagram on iPhone have no reliable way to hand a page to Safari,
      // so show the two manual steps right away and also try the x-safari-https link newer iOS accepts.
      showSteps();
      if (/^https:\/\//.test(pageUrl)) {
        var a = document.createElement("a");
        a.href = pageUrl.replace(/^https:\/\//, "x-safari-https://");
        a.rel = "noopener";
        a.style.display = "none";
        document.body.appendChild(a);
        a.click();
        a.remove();
      }
      return;
    }
    showSteps();
  }

  var css =
    ".iab{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:flex-end;justify-content:center;" +
    "background:rgba(14,18,44,.72);-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);font-family:inherit;}" +
    ".iab__card{width:100%;max-width:480px;background:#fff;color:#1b1f3b;border-radius:24px 24px 0 0;" +
    "padding:28px 22px calc(22px + env(safe-area-inset-bottom,0px));display:flex;flex-direction:column;gap:14px;" +
    "box-shadow:0 -10px 40px rgba(0,0,0,.25);text-align:center;}" +
    "@media (min-height:700px){.iab{align-items:center;padding:16px}.iab__card{border-radius:24px}}" +
    ".iab__icon{width:64px;height:64px;margin:0 auto;border-radius:18px;display:grid;place-items:center;" +
    "background:var(--indigo-50,#eef0fb);color:var(--indigo-700,#2b3280)}" +
    ".iab__icon svg{width:34px;height:34px}" +
    ".iab h2{margin:0;font-size:22px;line-height:1.35;font-weight:600}" +
    ".iab p{margin:0;font-size:16px;line-height:1.6;color:#4a4f6e}" +
    ".iab__go{display:flex;align-items:center;justify-content:center;gap:10px;width:100%;min-height:60px;border:0;" +
    "border-radius:16px;background:var(--indigo-700,#2b3280);color:#fff;font:inherit;font-size:19px;font-weight:600;cursor:pointer}" +
    ".iab__go:active{transform:scale(.99)}" +
    ".iab__copy{width:100%;min-height:52px;border:2px solid var(--indigo-200,#c9cdef);border-radius:16px;background:#fff;" +
    "color:var(--indigo-700,#2b3280);font:inherit;font-size:16px;font-weight:600;cursor:pointer}" +
    ".iab__stay{border:0;background:none;color:#6b7090;font:inherit;font-size:14px;text-decoration:underline;padding:8px;cursor:pointer}" +
    ".iab__steps{text-align:left;background:#f5f6fc;border-radius:14px;padding:14px 16px;font-size:15px;line-height:1.6;color:#1b1f3b}" +
    ".iab__steps ol{margin:6px 0 0;padding-left:22px}" +
    ".iab__steps b{white-space:nowrap}" +
    ".iab__url{width:100%;font:inherit;font-size:13px;padding:8px 10px;border:1px solid #d6d9ee;border-radius:10px;color:#4a4f6e;background:#fff}" +
    ".iab [hidden]{display:none!important}" +
    ".iab button:focus-visible{outline:3px solid #f5b800;outline-offset:2px}" +
    "html.iab-open,html.iab-open body{overflow:hidden}";

  var menuHint = isIOS
    ? "แตะปุ่ม <b>•••</b> หรือ <b>⋯</b> ที่มุมจอ"
    : "แตะปุ่ม <b>⋮</b> หรือ <b>•••</b> ที่มุมขวาบน";
  var openLabel = isIOS ? "“เปิดใน Safari” หรือ “Open in browser”" : "“เปิดในเบราว์เซอร์” หรือ “Open in Chrome”";

  var root = document.createElement("div");
  root.className = "iab";
  root.setAttribute("role", "dialog");
  root.setAttribute("aria-modal", "true");
  root.setAttribute("aria-labelledby", "iab-title");
  root.innerHTML =
    '<div class="iab__card">' +
      '<div class="iab__icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/></svg></div>' +
      '<h2 id="iab-title">เปิดใน ' + browser + ' เพื่อใช้งานเต็มที่</h2>' +
      '<p>ตอนนี้กำลังเปิดผ่านแอป ' + app + ' ซึ่งดูโมเดลในพื้นที่จริง (AR) และฟังเสียงบรรยายได้ไม่เต็มที่</p>' +
      '<button type="button" class="iab__go" data-iab-go>เปิดใน ' + browser + '</button>' +
      '<div class="iab__steps" data-iab-steps hidden>ถ้ายังไม่เปิด ทำแบบนี้:' +
        '<ol><li>' + menuHint + '</li><li>เลือก ' + openLabel + '</li></ol></div>' +
      '<button type="button" class="iab__copy" data-iab-copy>คัดลอกลิงก์ไปเปิดเอง</button>' +
      '<input class="iab__url" data-iab-url readonly hidden aria-label="ลิงก์ของหน้านี้">' +
      '<button type="button" class="iab__stay" data-iab-stay>ใช้งานต่อในแอปนี้</button>' +
    '</div>';

  function showSteps() {
    var steps = root.querySelector("[data-iab-steps]");
    if (steps) steps.hidden = false;
  }

  function mount() {
    if (document.querySelector(".iab")) return;
    var style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
    document.body.appendChild(root);
    document.documentElement.classList.add("iab-open");
    var go = root.querySelector("[data-iab-go]");
    go.addEventListener("click", openOutside);
    root.querySelector("[data-iab-copy]").addEventListener("click", function () {
      var input = root.querySelector("[data-iab-url]");
      var button = this;
      var done = function () { button.textContent = "คัดลอกแล้ว นำไปวางใน " + browser + " ได้เลย"; };
      input.value = pageUrl;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(pageUrl).then(done, function () { input.hidden = false; input.select(); });
      } else {
        input.hidden = false;
        input.select();
        try { if (document.execCommand("copy")) done(); } catch (e) { /* the selected link stays visible */ }
      }
    });
    root.querySelector("[data-iab-stay]").addEventListener("click", function () {
      try { sessionStorage.setItem(STAY_KEY, "1"); } catch (e) { /* ignore */ }
      root.remove();
      document.documentElement.classList.remove("iab-open");
    });
    try { go.focus({ preventScroll: true }); } catch (e) { go.focus(); }
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
