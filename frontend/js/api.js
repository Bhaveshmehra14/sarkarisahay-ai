const SSAI_API = (() => {
  // Same-origin by default since Flask serves the frontend too.
  // Override by setting window.SSAI_API_BASE before this script loads
  // (useful if you deploy frontend and backend separately).
  const BASE = window.SSAI_API_BASE || "";

  async function matchSchemes(profile) {
    const res = await fetch(`${BASE}/api/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
    if (!res.ok) throw new Error(`Match request failed (${res.status})`);
    return res.json();
  }

  async function getScheme(id) {
    const res = await fetch(`${BASE}/api/scheme/${encodeURIComponent(id)}`);
    if (!res.ok) throw new Error(`Scheme ${id} not found`);
    return res.json();
  }

  return { matchSchemes, getScheme };
})();
