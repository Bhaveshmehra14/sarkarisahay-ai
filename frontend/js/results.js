function renderEmpty() {
  document.getElementById("results-list").innerHTML = `
    <div class="empty-state">
      <h3 data-i18n="empty_title"></h3>
      <p data-i18n="empty_body"></p>
      <a href="form.html" class="btn btn--ghost" style="margin-top:14px;">Try again</a>
    </div>`;
  SSAI.applyI18n();
}

function renderCard(scheme, index) {
  const eligible = scheme.eligible;
  const scorePct = Math.round((scheme.match_score || 0) * 100);
  return `
    <a class="case-file" href="scheme.html?index=${index}">
      <div>
        <div class="case-file__category">${scheme.category}</div>
        <h3>${scheme.name}</h3>
        <p class="case-file__summary">${scheme.one_line_summary || scheme.explanation || ""}</p>
        <div class="case-file__meta">Match confidence: ${scorePct}% · ${eligible ? "Looks eligible" : "Partial match — check gaps"}</div>
      </div>
      <div class="seal ${eligible ? "" : "seal--partial"}">${SSAI.stampSVG({ eligible, settle: false })}</div>
    </a>`;
}

function init() {
  const raw = sessionStorage.getItem("ssai_result");
  if (!raw) {
    window.location.href = "form.html";
    return;
  }
  const result = JSON.parse(raw);
  const matches = result.matches || [];

  const metaEl = document.getElementById("results-meta");
  metaEl.textContent = matches.length
    ? `${matches.length} scheme${matches.length === 1 ? "" : "s"} matched · explanations generated ${result.ai_used ? "by AI, grounded in official scheme data" : "from our offline templates (no API key configured)"}`
    : "";

  if (!matches.length) {
    renderEmpty();
    return;
  }

  sessionStorage.setItem("ssai_matches", JSON.stringify(matches));
  document.getElementById("results-list").innerHTML = matches.map(renderCard).join("");
}

document.addEventListener("DOMContentLoaded", init);
