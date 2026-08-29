/* Shared chrome + language toggle for every page.
   Language preference is stored in localStorage and also sent to the
   backend so AI explanations come back in the same language. */

const SSAI = (() => {
  const LANG_KEY = "ssai_lang";

  const STRINGS = {
    en: {
      tagline: "Government schemes, explained honestly",
      nav_home: "Home",
      nav_check: "Check my schemes",
      nav_github: "View code",
      hero_eyebrow: "AI-powered · multilingual · source-verified",
      hero_title: "Not just what you qualify for — exactly why.",
      hero_lede: "Answer five simple questions. SarkariSahay AI checks your profile against real government schemes and shows you the reasoning, the paperwork, and how to apply — every claim traced back to an official source.",
      cta_primary: "Check my schemes",
      cta_secondary: "See how it works",
      footer_note: "Demo build for illustration. Verify scheme details on the official portals linked on each result before applying.",
      form_title: "Applicant details",
      form_lede: "Fill this once — we'll match it against every scheme in our database.",
      submit: "Find my schemes",
      matching: "Matching your profile against government schemes…",
      results_title: "Your matched schemes",
      empty_title: "No schemes matched yet",
      empty_body: "Try widening your income range or double-check your occupation and state.",
      back_to_results: "Back to results",
    },
    hi: {
      tagline: "सरकारी योजनाएं, ईमानदारी से समझाई गईं",
      nav_home: "होम",
      nav_check: "अपनी योजनाएं जांचें",
      nav_github: "कोड देखें",
      hero_eyebrow: "एआई-संचालित · बहुभाषी · स्रोत-सत्यापित",
      hero_title: "सिर्फ यह नहीं कि आप पात्र हैं — बल्कि बिल्कुल क्यों।",
      hero_lede: "पांच आसान सवालों के जवाब दें। SarkariSahay AI आपकी प्रोफ़ाइल की तुलना असली सरकारी योजनाओं से करता है और कारण, कागज़ात व आवेदन का तरीका दिखाता है — हर दावा एक आधिकारिक स्रोत से जुड़ा।",
      cta_primary: "अपनी योजनाएं जांचें",
      cta_secondary: "यह कैसे काम करता है",
      footer_note: "यह एक डेमो है। आवेदन से पहले हर परिणाम में दिए गए आधिकारिक पोर्टल पर विवरण ज़रूर जांचें।",
      form_title: "आवेदक का विवरण",
      form_lede: "एक बार भरें — हम इसे हमारे डेटाबेस की हर योजना से मिलाएंगे।",
      submit: "मेरी योजनाएं खोजें",
      matching: "आपकी प्रोफ़ाइल को सरकारी योजनाओं से मिलाया जा रहा है…",
      results_title: "आपकी मिलान की गई योजनाएं",
      empty_title: "अभी कोई योजना नहीं मिली",
      empty_body: "अपनी आय सीमा बढ़ाकर देखें या व्यवसाय व राज्य दोबारा जांचें।",
      back_to_results: "परिणामों पर वापस जाएं",
    },
  };

  function getLang() {
    return localStorage.getItem(LANG_KEY) || "en";
  }

  function setLang(lang) {
    localStorage.setItem(LANG_KEY, lang);
    applyI18n();
    document.dispatchEvent(new CustomEvent("ssai:langchange", { detail: { lang } }));
  }

  function t(key) {
    const lang = getLang();
    return (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;
  }

  function applyI18n() {
    const lang = getLang();
    document.documentElement.lang = lang === "hi" ? "hi" : "en";
    document.body.toggleAttribute("data-lang-hi", lang === "hi");
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll(".lang-toggle button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.lang === lang);
    });
  }

  function mountChrome(activeNav) {
    const header = document.createElement("header");
    header.className = "letterhead";
    header.innerHTML = `
      <div class="letterhead__bar">
        <a href="index.html" class="wordmark">
          <span class="wordmark__mark">सस</span>
          SarkariSahay <span class="wordmark__tag" data-i18n="tagline"></span>
        </a>
        <nav class="nav-links">
          <a href="index.html" data-i18n="nav_home"></a>
          <a href="form.html" data-i18n="nav_check"></a>
          <div class="lang-toggle" role="group" aria-label="Language">
            <button type="button" data-lang="en">EN</button>
            <button type="button" data-lang="hi">हिं</button>
          </div>
        </nav>
      </div>`;
    document.body.prepend(header);

    const footer = document.createElement("footer");
    footer.className = "site-footer";
    footer.innerHTML = `
      <div class="container">
        <p data-i18n="footer_note"></p>
        <p style="margin-top:8px; opacity:0.7;">SarkariSahay AI — demo MVP · schemes sourced from official portals, verify before applying.</p>
      </div>`;
    document.body.append(footer);

    header.querySelectorAll(".lang-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => setLang(btn.dataset.lang));
    });

    applyI18n();
  }

  function stampSVG({ eligible = true, settle = true } = {}) {
    const color = eligible ? "#2B6B4A" : "#A73B2E";
    const label = eligible ? "ELIGIBLE" : "PARTIAL";
    return `
      <svg viewBox="0 0 120 120" class="stamp${settle ? " stamp--settle" : ""}" role="img" aria-label="${label}">
        <circle cx="60" cy="60" r="52" fill="none" stroke="${color}" stroke-width="3"/>
        <circle cx="60" cy="60" r="44" fill="none" stroke="${color}" stroke-width="1.5" stroke-dasharray="2 3"/>
        <path id="curve-${label}" d="M 20 70 A 40 40 0 0 1 100 70" fill="none"/>
        <text font-family="IBM Plex Mono, monospace" font-size="9" fill="${color}" letter-spacing="2">
          <textPath href="#curve-${label}" startOffset="50%" text-anchor="middle">SARKARISAHAY · VERIFIED</textPath>
        </text>
        <text x="60" y="58" text-anchor="middle" font-family="Zilla Slab, serif" font-weight="700" font-size="17" fill="${color}">${label}</text>
        <text x="60" y="74" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="8" fill="${color}">AI-MATCHED</text>
      </svg>`;
  }

  return { getLang, setLang, t, applyI18n, mountChrome, stampSVG };
})();
