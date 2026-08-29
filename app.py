"""
SarkariSahay AI — backend
--------------------------
A small Flask app that:
  1. Serves the static, multi-page frontend (frontend/*.html, css, js).
  2. Exposes a REST API that matches a citizen's profile against a curated
     dataset of real government schemes (data/schemes.json) using
     transparent, rule-based eligibility logic.
  3. Calls the Anthropic API to turn each matched scheme's raw eligibility
     data into a clear, source-grounded explanation in the user's chosen
     language — the model is only ever given facts from schemes.json and is
     instructed not to invent anything beyond that, which is what keeps the
     "AI-Powered Matching" step honest instead of hallucinated.

Run locally:
    pip install -r requirements.txt
    cp .env.example .env      # then add your ANTHROPIC_API_KEY
    python app.py
Then open http://localhost:5000
"""

import os
import json
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
SCHEMES_PATH = BASE_DIR / "data" / "schemes.json"
FRONTEND_DIR = BASE_DIR / "frontend"

MODEL_NAME = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

with open(SCHEMES_PATH, "r", encoding="utf-8") as f:
    SCHEMES = json.load(f)

OCCUPATION_LABELS = {
    "farmer": "Farmer",
    "student": "Student",
    "salaried": "Salaried / Job holder",
    "job_seeker": "Job seeker / Unemployed",
    "business": "Self-employed / Business owner",
    "self_employed": "Self-employed / Business owner",
    "unorganized_worker": "Daily wage / Unorganised worker",
    "daily_wage": "Daily wage / Unorganised worker",
    "homemaker": "Homemaker",
    "senior_citizen": "Senior citizen / Retired",
    "other": "Other",
}


# ---------------------------------------------------------------------------
# Rule-based matching
# ---------------------------------------------------------------------------
def scheme_score(user: dict, scheme: dict):
    """
    Returns (is_eligible: bool, score: float, reasons: list[str], gaps: list[str])
    Deterministic, explainable rules — no model involved at this stage.
    """
    elig = scheme["eligibility"]
    reasons = []
    gaps = []
    checks = 0
    passed = 0

    # Age
    if elig.get("min_age") is not None or elig.get("max_age") is not None:
        checks += 1
        age = user.get("age")
        min_age = elig.get("min_age")
        max_age = elig.get("max_age")
        ok = True
        if age is None:
            ok = False
        else:
            if min_age is not None and age < min_age:
                ok = False
            if max_age is not None and age > max_age:
                ok = False
        if ok:
            passed += 1
            reasons.append(f"age requirement met ({age})")
        else:
            gaps.append(f"age must be between {min_age or 0} and {max_age or 'any'}")

    # Gender
    if elig.get("gender"):
        checks += 1
        if user.get("gender") == elig["gender"]:
            passed += 1
            reasons.append(f"scheme is for {elig['gender']} applicants")
        else:
            gaps.append(f"scheme is limited to {elig['gender']} applicants")

    # Income
    if elig.get("max_income_annual") is not None:
        checks += 1
        income = user.get("income_annual")
        if income is not None and income <= elig["max_income_annual"]:
            passed += 1
            reasons.append("household income is within the scheme's limit")
        elif income is None:
            gaps.append("income not provided")
        else:
            gaps.append(f"annual income must be at or below ₹{elig['max_income_annual']:,}")

    # Occupation
    occs = elig.get("occupations", ["Any"])
    if occs != ["Any"]:
        checks += 1
        if user.get("occupation") in occs:
            passed += 1
            reasons.append("occupation matches this scheme's target group")
        else:
            gaps.append("occupation does not match this scheme's target group")

    # State
    states = elig.get("states", ["All"])
    if states != ["All"]:
        checks += 1
        if user.get("state") in states:
            passed += 1
            reasons.append("available in your state")
        else:
            gaps.append("not currently listed as available in your state")

    # Social category
    cats = elig.get("social_categories", ["Any"])
    if cats not in (["Any"], None):
        checks += 1
        user_cat = user.get("social_category")
        if user_cat in cats or "Women" in cats and user.get("gender") == "female":
            passed += 1
            reasons.append("social category matches this scheme's eligibility")
        elif user_cat is None:
            gaps.append("social category not provided")
        else:
            gaps.append(f"scheme is limited to: {', '.join(cats)}")

    if checks == 0:
        return True, 1.0, ["open to all applicants"], []

    score = passed / checks
    is_eligible = len(gaps) == 0
    return is_eligible, round(score, 2), reasons, gaps


def match_schemes(user: dict, include_partial=True, limit=8):
    scored = []
    for scheme in SCHEMES:
        eligible, score, reasons, gaps = scheme_score(user, scheme)
        if eligible or (include_partial and score >= 0.5):
            scored.append(
                {
                    "scheme": scheme,
                    "eligible": eligible,
                    "score": score,
                    "reasons": reasons,
                    "gaps": gaps,
                }
            )
    scored.sort(key=lambda x: (x["eligible"], x["score"]), reverse=True)
    return scored[:limit]


# ---------------------------------------------------------------------------
# AI explanation layer (grounded on matched scheme data only)
# ---------------------------------------------------------------------------
def build_prompt(user: dict, matches: list, language: str):
    lang_line = {
        "hi": "Write every explanation and summary in simple, conversational Hindi (Devanagari script).",
        "hinglish": "Write every explanation and summary in Hinglish (Hindi written in Roman/English script, casual tone).",
    }.get(language, "Write every explanation and summary in simple, plain English.")

    payload = {
        "applicant": {k: v for k, v in user.items() if v not in (None, "")},
        "schemes": [
            {
                "id": m["scheme"]["id"],
                "name": m["scheme"]["name_en"],
                "eligible": m["eligible"],
                "match_score": m["score"],
                "official_description": m["scheme"]["short_desc_en"],
                "matched_reasons": m["reasons"],
                "gaps": m["gaps"],
            }
            for m in matches
        ],
    }

    instructions = f"""You are helping a citizen understand which Indian government
schemes they qualify for. You are given a JSON object with the applicant's
profile and a list of schemes that a rule-based matcher already scored.

STRICT RULES:
- Only use the facts given in the JSON below. Do not invent eligibility
  criteria, amounts, or benefits that are not present in the input.
- For each scheme, write:
  - "one_line_summary": a single friendly sentence (max 20 words) saying
    whether they qualify and why, in plain language.
  - "explanation": 2-4 sentences explaining exactly why they are (or are
    not fully) eligible, referencing the matched_reasons and gaps given.
- {lang_line}
- Return ONLY valid JSON — an array of objects like:
  [{{"id": "scheme-id", "one_line_summary": "...", "explanation": "..."}}]
- No markdown, no commentary, no code fences — just the JSON array.

DATA:
{json.dumps(payload, ensure_ascii=False)}
"""
    return instructions


def call_anthropic(prompt: str):
    """Calls the Anthropic API. Raises on failure so the caller can fall back."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if block.type == "text")
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def fallback_explanations(matches: list, language: str):
    """Offline, templated explanations used when no API key is configured
    or the API call fails — keeps the demo fully working without a key."""
    out = []
    for m in matches:
        name = m["scheme"]["name_en"]
        if m["eligible"]:
            reason_text = "; ".join(m["reasons"]) or "you meet the listed criteria"
            summary = f"You appear eligible for {name}."
            explanation = (
                f"Based on the details you shared, you meet this scheme's criteria: {reason_text}. "
                f"Review the document checklist below and apply through the official channel listed."
            )
        else:
            gap_text = "; ".join(m["gaps"]) or "some criteria are unclear"
            summary = f"You may partially qualify for {name} — check the gaps below."
            explanation = (
                f"You match some criteria for this scheme, but not all: {gap_text}. "
                f"You may still want to check with the official source, as some conditions vary by state."
            )
        out.append({"id": m["scheme"]["id"], "one_line_summary": summary, "explanation": explanation})
    return out


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/schemes")
def list_schemes():
    return jsonify(SCHEMES)


@app.post("/api/match")
def api_match():
    user = request.get_json(force=True) or {}
    language = user.get("language", "en")

    # normalise numeric fields
    for key in ("age", "income_annual"):
        if user.get(key) not in (None, ""):
            try:
                user[key] = float(user[key])
            except (TypeError, ValueError):
                user[key] = None

    matches = match_schemes(user)

    if not matches:
        return jsonify({"matches": [], "ai_used": False})

    ai_used = False
    try:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("No ANTHROPIC_API_KEY configured")
        prompt = build_prompt(user, matches, language)
        explanations = call_anthropic(prompt)
        ai_used = True
    except Exception as exc:  # noqa: BLE001 — any failure falls back gracefully
        app.logger.warning("Falling back to templated explanations: %s", exc)
        explanations = fallback_explanations(matches, language)

    exp_by_id = {e["id"]: e for e in explanations}

    results = []
    for m in matches:
        s = m["scheme"]
        exp = exp_by_id.get(s["id"], {})
        results.append(
            {
                "id": s["id"],
                "name": s["name_hi"] if language == "hi" else s["name_en"],
                "category": s["category"],
                "eligible": m["eligible"],
                "match_score": m["score"],
                "one_line_summary": exp.get("one_line_summary", ""),
                "explanation": exp.get("explanation", ""),
                "documents": s["documents"],
                "apply_steps": s["apply_steps"],
                "source": s["source"],
            }
        )

    return jsonify({"matches": results, "ai_used": ai_used})


@app.get("/api/scheme/<scheme_id>")
def api_scheme_detail(scheme_id):
    for s in SCHEMES:
        if s["id"] == scheme_id:
            return jsonify(s)
    return jsonify({"error": "not found"}), 404


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "schemes_loaded": len(SCHEMES), "ai_configured": bool(ANTHROPIC_API_KEY)})


# Serve the multi-page static frontend (index.html, form.html, results.html, scheme.html, ...)
@app.get("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
