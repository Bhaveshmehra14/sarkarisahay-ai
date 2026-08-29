# SarkariSahay AI — MVP

An AI-powered, multilingual assistant that matches Indian citizens to the
government schemes they actually qualify for, and explains exactly why —
grounded in real scheme data so it can be verified, not hallucinated.

This repo is a working full-stack MVP: a multi-page frontend, a Flask REST
API, a rule-based eligibility engine, and an AI explanation layer. See
`DESIGN.md` for the architecture write-up.

## Project structure

```
sarkarisahay-ai/
├── app.py                 # Flask backend: matching engine + AI layer + static hosting
├── requirements.txt
├── .env.example
├── data/
│   └── schemes.json        # curated dataset of 12 real central govt schemes
├── frontend/
│   ├── index.html           # landing / marketing page
│   ├── form.html            # applicant details form
│   ├── results.html         # matched schemes list
│   ├── scheme.html          # scheme detail (explanation, documents, apply steps)
│   ├── css/style.css
│   └── js/{main,api,form,results,scheme}.js
└── DESIGN.md               # architecture / design doc
```

## Run it locally

```bash
cd sarkarisahay-ai
python3 -m venv venv && source venv/bin/activate     # optional but recommended
pip install -r requirements.txt

cp .env.example .env
# open .env and paste your key from https://console.anthropic.com/
#   ANTHROPIC_API_KEY=sk-ant-...

python app.py
```

Open **http://localhost:5000** — the Flask app serves the frontend and the
API from the same origin, so there's nothing else to configure.

**No API key yet?** The app still works. `/api/match` falls back to
templated, rule-based explanations built from the same matched-reason data,
so you can demo the full flow (form → results → scheme detail) with zero
setup. Once a key is added, explanations switch to AI-generated text
automatically — no code change needed.

## How matching actually works

1. The form posts the applicant's profile to `POST /api/match`.
2. `app.py` runs deterministic rule checks (age, income, occupation, state,
   gender, social category) against every scheme in `data/schemes.json` and
   produces a match score + a list of matched reasons / gaps per scheme.
3. Only the matched schemes and their *already-computed* reasons/gaps are
   sent to the Anthropic API, with an explicit instruction not to invent
   facts beyond that input. The model's only job is to turn structured
   facts into a clear sentence in the right language — it never decides
   eligibility itself.
4. The response includes each scheme's real document checklist and apply
   steps (from the dataset, not the model) plus a link to the official
   source portal.

## Deploying

The tech stack diagram in the brief called for Vercel (frontend) + Render
(backend). Since this build serves both from one Flask app, the simplest
path is a single service:

- **Render** (or Railway / Fly.io): create a new Web Service from this repo.
  - Build command: `pip install -r requirements.txt`
  - Start command: `gunicorn app:app` (add `gunicorn` to requirements.txt for production)
  - Add `ANTHROPIC_API_KEY` as an environment variable in the dashboard.

If you'd rather split frontend and backend (e.g. static frontend on Vercel,
API on Render), set `window.SSAI_API_BASE = "https://your-api.onrender.com"`
in a small `<script>` tag before `js/api.js` loads on each HTML page, and
enable CORS for your frontend's domain (already wired up via `flask-cors`).

## Known limitations (MVP, not production)

- The 12 schemes in `data/schemes.json` are illustrative and based on
  general public knowledge of well-known central schemes — eligibility
  rules, income caps and state availability for real schemes change over
  time and vary by state. **Verify against the official portal linked on
  each result before relying on this for a real application.**
- No persistence layer — nothing about a citizen's inputs is stored;
  results live only in the browser's `sessionStorage` for the current visit.
- No authentication, since there's nothing account-specific to protect yet.
- Add more schemes by appending objects to `data/schemes.json` following the
  existing shape — no code changes required for the matcher to pick them up.
