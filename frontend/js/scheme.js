function render(scheme) {
  const eligible = scheme.eligible;
  const pillClass = eligible ? "status-pill--eligible" : "status-pill--partial";
  const pillLabel = eligible ? "Looks eligible" : "Partial match";

  document.getElementById("scheme-detail").innerHTML = `
    <div style="margin: 8px 0 20px;">
      <div class="case-file__category">${scheme.category}</div>
      <h1 style="font-size:30px; margin-bottom:10px;">${scheme.name}</h1>
      <span class="status-pill ${pillClass}">${pillLabel} · ${Math.round((scheme.match_score || 0) * 100)}% match</span>
    </div>

    <div class="detail-grid">
      <div>
        <div class="officer-note">
          <div class="officer-note__label">Why this result</div>
          <p>${scheme.explanation || scheme.one_line_summary || "No explanation available."}</p>
        </div>
      </div>

      <div>
        <div class="side-card">
          <h4>Documents needed</h4>
          <ul class="checklist">
            ${(scheme.documents || []).map((d) => `<li>${d}</li>`).join("")}
          </ul>
        </div>
        <div class="side-card">
          <h4>How to apply</h4>
          <ol class="steps-list">
            ${(scheme.apply_steps || []).map((s) => `<li>${s}</li>`).join("")}
          </ol>
        </div>
        <div class="source-strip">
          <span>Source-verified</span>
          <a href="${scheme.source?.url || '#'}" target="_blank" rel="noopener">${scheme.source?.name || "Official portal"} →</a>
        </div>
      </div>
    </div>`;
}

function init() {
  const params = new URLSearchParams(window.location.search);
  const index = Number(params.get("index"));
  const raw = sessionStorage.getItem("ssai_matches");

  if (!raw || Number.isNaN(index)) {
    window.location.href = "results.html";
    return;
  }

  const matches = JSON.parse(raw);
  const scheme = matches[index];

  if (!scheme) {
    window.location.href = "results.html";
    return;
  }

  render(scheme);
}

document.addEventListener("DOMContentLoaded", init);
