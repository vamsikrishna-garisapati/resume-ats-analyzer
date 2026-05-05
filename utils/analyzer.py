import json
import os
import re
from datetime import date

from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError(
        "Missing Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in .env."
    )

client = genai.Client(api_key=api_key)
MODEL_ID = "gemini-2.5-flash"

PROMPT = """
You are an expert ATS resume reviewer.
Today is {today}.
Resume: {resume}
Job Description: {jd}

Critical rules:
- Do not fabricate facts, dates, or "assumed corrections".
- Do not mark a date range as "future" unless its start date is actually after Today.
- If dates are ambiguous, say they need confirmation instead of guessing exact replacements.
- Avoid words like "assume", "probably", or "likely" for factual corrections.

Return ONLY valid JSON:
{{
  "ats_score": 0-100,
  "section_scores": {{
    "skills": 0-100,
    "experience": 0-100,
    "projects": 0-100,
    "format": 0-100
  }},
  "overall_feedback": "string",
  "matched_skills": [],
  "missing_skills": [],
  "weak_sections": [],
  "improvement_suggestions": [],
  "recommended_keywords": [],
  "rewritten_summary": "string",
  "improved_bullets": [{{"original":"","improved":""}}],
  "final_recommendation": "string"
}}

You MUST include section_scores with exactly these four keys (lowercase): skills, experience, projects, format.
Each value must be an integer 0-100 that matches your critique (if ats_score is high, section scores cannot all be zero).
weak_sections may be strings or objects like {{"area": "Work Experience", "suggestion": "..."}}.
"""

_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _extract_month_year_dates(text: str) -> list[date]:
    matches = re.findall(
        r"\b("
        r"January|February|March|April|May|June|July|August|September|October|November|December"
        r")\s+(\d{4})\b",
        text,
        flags=re.IGNORECASE,
    )
    extracted = []
    for month_name, year_text in matches:
        month = _MONTH_MAP.get(month_name.lower())
        if month:
            extracted.append(date(int(year_text), month, 1))
    return extracted


def _suggestion_text(item) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("suggestion") or item.get("text") or None
    return None


def _looks_like_false_future_flag(text: str, today: date) -> bool:
    lower = text.lower()
    if "future" not in lower:
        return False

    mentioned_dates = _extract_month_year_dates(text)
    if not mentioned_dates:
        return False

    # Keep warning only if at least one mentioned date is genuinely in the future.
    has_true_future = any(d > today for d in mentioned_dates)
    return not has_true_future


def _post_validate_result(result: dict, today: date) -> dict:
    for key in ("improvement_suggestions", "weak_sections"):
        values = result.get(key, [])
        if not isinstance(values, list):
            continue
        kept = []
        for v in values:
            text = v if isinstance(v, str) else _suggestion_text(v)
            if isinstance(text, str) and _looks_like_false_future_flag(text, today):
                continue
            kept.append(v)
        result[key] = kept
    return result


def _canonical_section_key(key: str) -> str | None:
    k = str(key).lower().strip().replace(" ", "_").replace("-", "_")
    if k in ("skills", "skill"):
        return "skills"
    if k in ("experience", "work_experience", "work", "exp", "employment"):
        return "experience"
    if k in ("projects", "project"):
        return "projects"
    if k in ("format", "formatting", "layout", "presentation"):
        return "format"
    return None


def _coerce_score(val) -> int | None:
    if val is None:
        return None
    try:
        if isinstance(val, str) and val.strip() == "":
            return None
        if isinstance(val, str):
            s = val.strip()
            m = re.match(r"^(\d{1,3})\s*/\s*100\s*$", s, re.I)
            if m:
                return max(0, min(100, int(m.group(1))))
            m2 = re.match(r"^(\d{1,3})\s*$", s)
            if m2:
                return max(0, min(100, int(m2.group(1))))
        n = int(round(float(val)))
        return max(0, min(100, n))
    except (TypeError, ValueError):
        return None


def _coerce_ats_value(val) -> int:
    if val is None:
        return 0
    c = _coerce_score(val)
    return c if c is not None else 0


def _is_missing_or_empty(val) -> bool:
    if val is None or val == "" or val == [] or val == {}:
        return True
    return False


def _merge_key_aliases(d: dict) -> dict:
    """Map common alternate JSON keys from the model (camelCase, etc.)."""
    out = dict(d)
    aliases = (
        ("atsScore", "ats_score"),
        ("ATS_Score", "ats_score"),
        ("ats", "ats_score"),
        ("sectionScores", "section_scores"),
        ("section_scores_detail", "section_scores"),
    )
    for alt, canonical in aliases:
        if alt in out and (
            canonical not in out or _is_missing_or_empty(out.get(canonical))
        ):
            out[canonical] = out[alt]
    return out


def _unwrap_nested_payload(d: dict) -> dict:
    """Merge fields from common wrapper objects (e.g. {\"analysis\": {...}})."""
    out = dict(d)
    for wrap in ("data", "result", "analysis", "response", "output"):
        inner = out.get(wrap)
        if not isinstance(inner, dict):
            continue
        for k, v in inner.items():
            if k not in out or _is_missing_or_empty(out.get(k)):
                out[k] = v
        del out[wrap]
    return out


def _parse_section_scores_raw(raw) -> dict[str, int]:
    """Accept dict (any key casing), or list of {{section, score}} objects."""
    out: dict[str, int] = {}
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = (
                item.get("section")
                or item.get("name")
                or item.get("area")
                or item.get("key")
                or item.get("title")
            )
            score = (
                item.get("score")
                if "score" in item
                else item.get("value")
                if "value" in item
                else item.get("rating")
            )
            canon = _canonical_section_key(str(name)) if name is not None else None
            if canon:
                c = _coerce_score(score)
                if c is not None:
                    out[canon] = c
        return out

    if isinstance(raw, dict):
        for key, val in raw.items():
            canon = _canonical_section_key(str(key))
            if not canon:
                continue
            if isinstance(val, dict):
                c = _coerce_score(
                    val.get("score", val.get("value", val.get("rating")))
                )
            else:
                c = _coerce_score(val)
            if c is not None:
                out[canon] = c
    return out


def _normalize_section_scores(result: dict) -> dict:
    defaults = {"skills": 0, "experience": 0, "projects": 0, "format": 0}
    raw = result.get("section_scores")
    parsed = _parse_section_scores_raw(raw) if raw is not None else {}

    normalized = dict(defaults)
    for key in defaults:
        if key in parsed:
            normalized[key] = parsed[key]

    ats = _coerce_ats_value(result.get("ats_score"))

    # Model often omits section_scores or uses wrong shape → all zeros. Align with overall score.
    if ats > 0 and all(v == 0 for v in normalized.values()):
        normalized = {k: ats for k in defaults}

    result["section_scores"] = normalized
    return result


def finalize_analysis_result(result: dict) -> dict:
    """
    Normalize keys, ATS, and section scores. Safe to call on fresh API output or stale
    Streamlit session_state so the UI never shows all-zero sections when ATS > 0.
    """
    if not isinstance(result, dict):
        return result
    out = _unwrap_nested_payload(_merge_key_aliases(result))
    out["ats_score"] = _coerce_ats_value(out.get("ats_score"))
    _normalize_section_scores(out)
    return out


def analyze(resume_text: str, jd_text: str) -> dict:
    today = date.today()
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=PROMPT.format(
            today=today.isoformat(), resume=resume_text, jd=jd_text
        ),
    )
    raw = response.text.strip().removeprefix("```json").removesuffix("```").strip()
    parsed = json.loads(raw)
    parsed = finalize_analysis_result(parsed)
    return _post_validate_result(parsed, today)
