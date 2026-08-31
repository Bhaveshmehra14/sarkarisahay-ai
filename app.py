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
  4. Exposes a grounded AI chatbot ("/api/chat") on the results page that
     answers follow-up questions ("Why am I eligible?", "Which scheme is
     best for me?", "What documents do I need?", "How do I apply?") using
     ONLY the applicant's profile plus the schemes already matched by the
     same rule-based engine — never inventing schemes, criteria, benefits,
     documents or links.

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

# Fast lookup used by both the /api/scheme/<id> route and the chatbot context
# builder below — schemes.json (loaded once, above) remains the single
# source of truth for every scheme fact used anywhere in this app.
SCHEME_BY_ID = {s["id"]: s for s in SCHEMES}

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
# Rule-based matching (UNCHANGED — this remains the sole source of truth for
# every eligibility decision; the chatbot below only ever reads its output,
# it never re-decides or overrides eligibility itself)
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


def normalise_user(user: dict) -> dict:
    """Shared numeric-field coercion used by both /api/match and /api/chat."""
    user = dict(user or {})
    for key in ("age", "income_annual"):
        if user.get(key) not in (None, ""):
            try:
                user[key] = float(user[key])
            except (TypeError, ValueError):
                user[key] = None
    return user


def lang_instruction(language: str) -> str:
    return {
        "hi": "Write every explanation and summary in simple, conversational Hindi (Devanagari script).",
        "hinglish": "Write every explanation and summary in Hinglish (Hindi written in Roman/English script, casual tone).",
    }.get(language, "Write every explanation and summary in simple, plain English.")


# ---------------------------------------------------------------------------
# AI explanation layer (grounded on matched scheme data only)
# ---------------------------------------------------------------------------
def build_prompt(user: dict, matches: list, language: str):
    lang_line = lang_instruction(language)

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
# Chatbot layer (results page) — grounded on the SAME rule-engine output.
#
# The bot is never given free rein: for every scheme it discusses it is
# handed the exact scheme record from data/schemes.json plus the
# deterministic reasons/gaps that scheme_score() already computed for this
# applicant. It is instructed to answer only from that JSON and to say so
# plainly when something isn't in it, instead of guessing.
# ---------------------------------------------------------------------------
CHAT_SYSTEM_PROMPT_TEMPLATE = """You are the SarkariSahay AI assistant, helping an Indian citizen \
understand the government welfare schemes they were just matched with on the results page.

You must answer ONLY using the JSON context below. It contains the applicant's profile and \
their matched schemes exactly as produced by a deterministic, rule-based eligibility engine — \
that engine, not you, is the source of truth for every eligibility decision.

STRICT RULES — follow all of them:
1. NEVER invent, guess, or assume a scheme name, eligibility rule, benefit amount, document, \
   ministry, deadline, fee, or application link that is not explicitly present in the context JSON.
2. If the user asks about a scheme, document, or detail that is not present in the context, say \
   plainly that it isn't among their matched schemes/information, and suggest they re-check the \
   "official_source" link for that scheme (only if present) or fill in the eligibility form again \
   for a fresh match.
3. When explaining why someone is or isn't eligible, use the "matched_reasons" and "gaps" fields \
   already computed for them — do not recompute eligibility or contradict the engine's verdict \
   ("eligible_for_this_user").
4. When asked which scheme is "best", reason using "eligible_for_this_user", "match_score", and \
   how many/severe the "gaps" are — do not invent a different ranking criterion.
5. When asked about documents or how to apply, list only items from that scheme's \
   "documents_required" / "apply_steps" — do not add anything else.
6. {lang_line}
7. Keep answers conversational and concise (aim for well under 150 words unless the user asks for \
   a full list), in plain language a first-time applicant can follow.
8. You are not a lawyer, accountant, or government official — do not give legal, tax, or financial \
   advice beyond what's in the scheme data, and don't promise approval or timelines.

CONTEXT (JSON):
{context_json}
"""


def build_chat_context(user: dict, scheme_ids: list):
    """Re-derives grounded, per-scheme facts for the chatbot using the exact
    same rule engine (scheme_score) and the exact same schemes.json records
    used everywhere else in the app — nothing here is model-generated."""
    context_schemes = []
    for sid in scheme_ids:
        scheme = SCHEME_BY_ID.get(sid)
        if not scheme:
            continue
        eligible, score, reasons, gaps = scheme_score(user, scheme)
        context_schemes.append(
            {
                "id": scheme["id"],
                "name": scheme["name_en"],
                "category": scheme["category"],
                "ministry": scheme.get("ministry"),
                "official_description": scheme["short_desc_en"],
                "eligibility_criteria": scheme["eligibility"],
                "documents_required": scheme["documents"],
                "apply_steps": scheme["apply_steps"],
                "official_source": scheme["source"],
                "eligible_for_this_user": eligible,
                "match_score": score,
                "matched_reasons": reasons,
                "gaps": gaps,
            }
        )
    return context_schemes


def call_anthropic_chat(system_prompt: str, history: list, message: str) -> str:
    """Calls the Anthropic API for a chat turn. Raises on failure so the
    caller can fall back to the offline templated responder."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    messages = []
    for turn in history[-10:]:  # cap context sent per turn
        role = turn.get("role")
        content = turn.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content.strip()[:4000]})
    messages.append({"role": "user", "content": message})

    resp = client.messages.create(
        model=MODEL_NAME,
        max_tokens=800,
        system=system_prompt,
        messages=messages,
    )
    return "".join(block.text for block in resp.content if block.type == "text").strip()


def fallback_chat_response(message: str, context_schemes: list, language: str) -> str:
    """Offline, templated chatbot answers used when no API key is configured
    or the API call fails — keeps the chat panel useful even without a key,
    using only the same grounded scheme data."""
    if not context_schemes:
        return (
            "मुझे अभी कोई मिलान योजना नहीं दिख रही — कृपया पहले फ़ॉर्म भरें।"
            if language == "hi"
            else "I don't have any matched schemes to discuss yet — please fill in the eligibility "
            "form first, then come back and ask me about your results."
        )

    msg = message.lower()
    lines = []

    if any(k in msg for k in ("document", "paper", "kyc", "proof")):
        for s in context_schemes:
            lines.append(f"{s['name']}: " + ", ".join(s["documents_required"]))
        return "Documents needed:\n" + "\n".join(lines)

    if any(k in msg for k in ("apply", "how do i", "process", "steps", "register")):
        for s in context_schemes:
            steps = " → ".join(s["apply_steps"])
            lines.append(f"{s['name']}: {steps}")
        return "How to apply:\n" + "\n".join(lines)

    if any(k in msg for k in ("best", "which scheme", "recommend", "should i")):
        best = max(context_schemes, key=lambda s: (s["eligible_for_this_user"], s["match_score"]))
        return (
            f"Based on your matched results, {best['name']} looks like the strongest option for you "
            f"(match confidence {round(best['match_score'] * 100)}%, "
            f"{'fully eligible' if best['eligible_for_this_user'] else 'partial match'}). "
            f"Check its documents and apply steps below."
        )

    if any(k in msg for k in ("why", "eligible", "qualify", "criteria")):
        for s in context_schemes:
            reason_text = "; ".join(s["matched_reasons"]) or "no specific matched reasons recorded"
            gap_text = "; ".join(s["gaps"]) if s["gaps"] else "no gaps"
            lines.append(f"{s['name']}: {reason_text}. Gaps: {gap_text}")
        return "\n".join(lines)

    names = ", ".join(s["name"] for s in context_schemes)
    return (
        f"I can help explain your matched schemes ({names}). Ask me why you're eligible, which one "
        f"is best for you, what documents you need, or how to apply. (Note: AI-generated answers are "
        f"offline right now since no ANTHROPIC_API_KEY is configured — these are basic answers pulled "
        f"directly from your matched scheme data.)"
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/schemes")
def list_schemes():
    return jsonify(SCHEMES)


@app.post("/api/match")
def api_match():
    user = normalise_user(request.get_json(force=True) or {})
    language = user.get("language", "en")

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


@app.post("/api/chat")
def api_chat():
    """Grounded chatbot for the results page.

    Expected JSON body:
      {
        "message": "Why am I eligible?",
        "profile": { ...same shape as /api/match input... },
        "scheme_ids": ["pm-kisan", "..."],   // ids of the schemes shown to this user
        "history": [{"role": "user"|"assistant", "content": "..."}, ...],  // optional
        "language": "en" | "hi" | "hinglish"                              // optional
      }
    """
    body = request.get_json(force=True) or {}

    message = (body.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    message = message[:2000]  # basic guardrail against oversized input

    user = normalise_user(body.get("profile") or {})
    language = body.get("language") or user.get("language") or "en"

    scheme_ids = body.get("scheme_ids") or []
    if not scheme_ids and body.get("matches"):
        # Convenience: accept the /api/match response shape directly too.
        scheme_ids = [m.get("id") for m in body["matches"] if m.get("id")]

    history = body.get("history") or []
    if not isinstance(history, list):
        history = []

    context_schemes = build_chat_context(user, scheme_ids)

    ai_used = False
    try:
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("No ANTHROPIC_API_KEY configured")
        if not context_schemes:
            raise RuntimeError("No matched schemes in context")

        context_json = json.dumps(
            {
                "applicant": {k: v for k, v in user.items() if v not in (None, "")},
                "matched_schemes": context_schemes,
            },
            ensure_ascii=False,
        )
        system_prompt = CHAT_SYSTEM_PROMPT_TEMPLATE.format(
            lang_line=lang_instruction(language),
            context_json=context_json,
        )
        reply = call_anthropic_chat(system_prompt, history, message)
        if not reply:
            raise RuntimeError("Empty response from model")
        ai_used = True
    except Exception as exc:  # noqa: BLE001 — any failure falls back gracefully
        app.logger.warning("Chat falling back to templated response: %s", exc)
        reply = fallback_chat_response(message, context_schemes, language)

    return jsonify({"reply": reply, "ai_used": ai_used})


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
