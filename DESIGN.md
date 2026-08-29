# Design Doc: SarkariSahay AI (MVP)

**Status:** Draft — MVP implemented
**Owner:** [fill in]
**Reviewers:** [fill in]

## 1. Summary

SarkariSahay AI is a mobile-first, multilingual web assistant that takes a
citizen's basic profile (age, state, occupation, income, category) and
returns the government schemes they qualify for — with a plain-language
explanation of *why*, the exact documents required, and how to apply. This
doc describes the MVP architecture implemented in this repository.

## 2. Problem

Citizens eligible for government welfare schemes frequently miss out
because scheme information is scattered across ministry websites, written
in dense legal language, and offers no way to check "do I actually
qualify?" without manually reading eligibility clauses. A naive LLM chatbot
solves the language problem but introduces a worse one: it can confidently
state incorrect eligibility criteria or benefit amounts.

## 3. Goals

- Let a citizen describe themselves in under a minute and get a ranked list
  of relevant schemes.
- Explain eligibility in plain language, not a bare yes/no.
- Ground every explanation in a checkable, official source — no invented
  facts.
- Work in English, Hindi, and Hinglish.
- Ship as a lightweight MVP: no login, no persistence, fast to deploy.

### Non-goals (for this MVP)

- Not a source of legal/final eligibility determination — it's a discovery
  and explanation tool; the citizen still applies through official channels.
- Not covering every scheme in India (12 curated central schemes for the
  demo; state-specific schemes are future scope).
- No user accounts, saved history, or application submission.

## 4. Architecture

```
 ┌───────────────┐      ┌────────────────┐      ┌──────────────────┐
 │  Frontend      │ HTTP │  Backend        │      │  Data layer       │
 │  (HTML/CSS/JS) ├─────►│  Flask REST API │◄────►│  schemes.json     │
 │  multi-page    │      │                 │      │  (curated)        │
 └───────────────┘      └───────┬────────┘      └──────────────────┘
                                 │
                                 ▼
                       ┌───────────────────┐
                       │  Rule-based        │
                       │  eligibility engine│
                       └─────────┬─────────┘
                                 │ matched schemes + reasons/gaps only
                                 ▼
                       ┌───────────────────┐
                       │  AI explanation     │
                       │  layer (Anthropic   │
                       │  API, grounded)     │
                       └───────────────────┘
```

### 4.1 Flow of solution (6 steps)

| # | Step | Where it happens |
|---|------|-------------------|
| 1 | User info input (age, state, occupation, income) | `form.html` |
| 2 | Rule-based match against scheme DB | `app.py: match_schemes()` |
| 3 | Ranked, relevant results | `POST /api/match` response |
| 4 | Explanation of why the user is/isn't eligible | AI layer, grounded on step 2's output |
| 5 | Exact document checklist | pulled directly from `schemes.json`, not the model |
| 6 | Step-by-step apply guidance | pulled directly from `schemes.json`, not the model |

### 4.2 Why matching is rule-based, not LLM-based

The eligibility decision itself (steps 1–3) is deterministic Python, not an
LLM call. This is the key anti-hallucination design choice: the model is
never asked "is this person eligible?" — it's only asked to phrase an
already-computed, structured verdict (which criteria matched, which didn't)
into natural language. This means:

- The eligibility verdict is reproducible and testable.
- The AI call can fail or be disabled entirely (no API key) and the product
  still works correctly, just with templated instead of natural phrasing.
- Document lists, apply steps, and source links are always the literal
  values from `schemes.json` — the model never generates or touches them.

### 4.3 API surface

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/match` | Body: applicant profile → matched schemes with AI/templated explanations |
| `GET` | `/api/scheme/<id>` | Full raw record for one scheme |
| `GET` | `/api/schemes` | All schemes (debug/admin use) |
| `GET` | `/api/health` | Liveness + whether an API key is configured |

`POST /api/match` request body:

```json
{
  "age": 34, "gender": "male", "state": "Punjab",
  "occupation": "farmer", "income_annual": 150000,
  "social_category": "General", "language": "en"
}
```

Response (truncated):

```json
{
  "ai_used": true,
  "matches": [
    {
      "id": "pm-kisan", "name": "PM-KISAN ...", "category": "Farmer",
      "eligible": true, "match_score": 1.0,
      "one_line_summary": "...", "explanation": "...",
      "documents": ["..."], "apply_steps": ["..."],
      "source": { "name": "pmkisan.gov.in", "url": "https://pmkisan.gov.in" }
    }
  ]
}
```

### 4.4 Data model (`schemes.json`)

Each scheme record has: bilingual name/description, owning ministry, an
`eligibility` object (min/max age, gender, max annual income, occupation
list, state list, social category list — any of which can be `null`/`"Any"`
to mean "not restricted"), a document checklist, ordered apply steps, and a
source `{name, url}`. Adding a scheme is a pure data change; no code touches
scheme-specific logic.

## 5. Tech stack (as implemented)

- **Frontend:** HTML, CSS, vanilla JS. Hindi/English toggle stored in
  `localStorage`. Multi-page (not an SPA) — `index`, `form`, `results`,
  `scheme` — matching the brief's page-per-step approach.
- **Backend:** Flask, single service, also serves the static frontend.
- **AI layer:** Anthropic API (`claude-sonnet-5` by default, configurable),
  called once per match request with a grounded, JSON-only prompt.
- **Data layer:** a single curated JSON file (`schemes.json`). Swappable
  for SQLite/Postgres later without changing the API contract.
- **Hosting:** designed to run as one Render/Railway web service; can be
  split into a static frontend (Vercel) + API (Render) via `SSAI_API_BASE`.

## 6. Privacy & security notes

- No data is persisted server-side; the profile and results live only in
  the browser's `sessionStorage` for that visit.
- No PII beyond what's needed for matching (no name, no Aadhaar number
  collected in the MVP form).
- The Anthropic API key lives only in a server-side `.env` file, never
  shipped to the client.

## 7. Limitations

- Scheme eligibility data is illustrative and must be verified against the
  official source before a citizen relies on it for a real application —
  this is called out in the product UI and README.
- Only central-government schemes are included; state schemes are a large,
  valuable extension.
- Rule engine currently supports single-value fields (e.g., one occupation,
  one state); doesn't yet model household-level composition.

## 8. Future roadmap

- **Native app + WhatsApp bot**, as noted on the platform roadmap — the
  existing `/api/match` endpoint is already channel-agnostic and could back
  a WhatsApp bot (via the WhatsApp Business API) with no backend changes.
- Expand `schemes.json` to state-level schemes, ideally sourced from a
  maintained government open-data feed rather than manual curation.
- Add a feedback loop: let users flag an explanation as unclear or a scheme
  as outdated, feeding back into dataset upkeep.
- Move `schemes.json` into SQLite/Postgres once the dataset grows past a
  size that's comfortable to hand-maintain as a single file.

## 9. Alternatives considered

- **LLM decides eligibility directly** (profile + all schemes in one
  prompt, model returns which apply): rejected — no way to guarantee the
  model doesn't misstate a threshold (e.g., an income cutoff), which is
  exactly the hallucination risk the product is trying to eliminate.
- **Single-page React app**: would work well for a v2, but the brief asked
  for a genuinely working multi-page site with a simple, framework-free
  stack that's easy to hand off and deploy piece by piece.
