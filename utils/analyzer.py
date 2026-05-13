import json
import os
import re
import time
from random import random
from datetime import date
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

try:
    from google.genai.errors import APIError, ServerError
except Exception:  # pragma: no cover
    APIError = Exception  # type: ignore[misc,assignment]
    ServerError = Exception  # type: ignore[misc,assignment]

from utils.analysis_schema import (
    MAX_EVIDENCE_ROWS,
    MAX_IMPROVED_BULLETS,
    MAX_SKILL_ROADMAPS,
    ATSResult,
)

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError(
        "Missing Gemini API key. Set GEMINI_API_KEY (or GOOGLE_API_KEY) in .env."
    )

client = genai.Client(api_key=api_key)
MODEL_ID = "gemini-2.5-flash"


def _genai_json_config() -> types.GenerateContentConfig:
    # Omit response_schema: Gemini often returns 400 "too many states" for nested
    # Pydantic JSON Schemas. Prompt defines shape; ATSResult validates after parse.
    return types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json",
    )


def _generate_content_with_retry(
    *,
    prompt: str,
    model: str,
    config: types.GenerateContentConfig,
    max_attempts: int = 3,
) -> Any:
    """
    Calls Gemini with a small retry loop for transient 5xx/server errors.

    The google-genai SDK already retries internally, but Streamlit Cloud users
    still see occasional ServerError; this makes the user-visible experience
    more resilient.
    """
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )
        except ServerError as e:
            last_err = e
        except APIError as e:
            # Retry only when it's likely transient (5xx / server-side).
            status = getattr(e, "status_code", None)
            if isinstance(status, int) and 500 <= status <= 599:
                last_err = e
            else:
                raise

        if attempt < max_attempts:
            # Exponential backoff with a little jitter.
            delay_s = (2 ** (attempt - 1)) + (random() * 0.25)
            time.sleep(delay_s)

    raise RuntimeError(
        "Gemini API failed with a transient server error after multiple retries. "
        "Please try again in a moment."
    ) from last_err


_EVALUATOR_RULES = """You are an expert ATS resume evaluator, career coach, and resume optimization specialist.

Your task is to evaluate a candidate's resume against a specific job description and return ONLY valid JSON with the object shape and field rules below. Do not include markdown, explanations, commentary, or code fences.

Today is {today_iso}.

Context for this request:
- Fresher mode: {fresher_mode} (when true, treat projects, internships, coursework, certifications, hackathons, volunteering, and academic work as valid proof of capability.)
- Maximum evidence rows: {max_evidence}
- Maximum skill roadmaps: {max_roadmaps}
- Maximum improved bullets: {max_bullets}

{indian_context_section}

{fresher_mode_section}

Evaluation rules:
1. Compare the resume directly against the job description.
2. Prioritize the most important job requirements first in evidence_matches.
3. For fresher/student candidates (fresher mode true), treat projects, internships, coursework, certifications, hackathons, volunteering, and academic work as valid proof of capability.
4. If fresher mode is false, still include fresher_insights, but set profile_type to "general" unless the resume is clearly student or intern focused.
5. Do not treat keyword mentions as strong evidence unless the resume shows usage, context, project work, scope, or measurable impact.
6. Do not upgrade vague claims such as "familiar with" into strong proficiency.
7. Keep feedback practical, specific, and tailored to this exact job.
8. weak_sections must be an array of strings only (each string names a weak area or section in plain language).

Scoring guidance:
- ats_score: Overall job-match score from 0 to 100.
- skills: Relevance and coverage of required technical/domain skills.
- experience: Work, internship, project, coursework, or practical proof relevant to the JD.
- projects: Strength, relevance, clarity, and impact of projects.
- format: ATS readability, structure, clarity, section organization, keyword placement, and bullet quality.

Match status rules for evidence_matches:
- "yes": Clear evidence exists in the resume.
- "weak": Skill is mentioned or implied, but lacks concrete proof, scope, project usage, or measurable detail.
- "no": Requirement is not evidenced in the resume.

Date and factual integrity:
- Do not fabricate facts, dates, or assumed corrections.
- Do not mark a date range as future unless its start date is actually after Today.
- If dates are ambiguous, say they need confirmation instead of guessing exact replacements.
- Avoid words like assume, probably, or likely for factual corrections.

Honesty (all modes):
- Do not fabricate skills, companies, projects, internships, metrics, URLs, certifications, or experience.
- Every match must be traceable to the resume text.
- resume_evidence must come only from the resume; if absent, use: Not evidenced.
- If a GitHub, LinkedIn, portfolio, or repo is not present in the resume text, do not claim it exists.
- Do not invent GitHub/LinkedIn evidence unless URLs or handles appear in the resume text.
- honest_resume_bullet_after_completion must be a bullet the candidate may add only after completing the mini-project; do not present it as employment or fake experience.
- If the resume has thin experience and fresher mode is true, do not punish unfairly; evaluate internships, projects, coursework, and certifications as practical evidence.
- Keep all suggestions realistic, ethical, and achievable.

Hard constraints:
- section_scores must contain exactly these lowercase keys: skills, experience, projects, format. All score values must be integers from 0 to 100.
- evidence_matches must contain at most {max_evidence} rows.
- skill_gap_roadmaps must contain at most {max_roadmaps} items and must address only missing or weak JD requirements reflected in evidence_matches.
- improved_bullets must contain at most {max_bullets} pairs and must rewrite only bullets that already exist in the resume.
- Each skill_gap_roadmaps[].learning_plan must contain between 3 and 7 strings (inclusive).
- weak_sections entries must be plain strings (not objects).

Output shape (critical):
- Use these exact snake_case root keys so parsers can read your JSON: ats_score, section_scores,
  overall_feedback, matched_skills, missing_skills, weak_sections, improvement_suggestions,
  recommended_keywords, rewritten_summary, improved_bullets, final_recommendation,
  fresher_insights, evidence_matches, skill_gap_roadmaps.
- Each skill_gap_roadmaps[] object MUST include the string field "skill_or_requirement" (name the JD gap),
  plus "learning_plan" (array of 3-7 short steps), "why_it_matters_for_this_role", "mini_project"
  (object with title, description, suggested_stack, demo_idea), and "honest_resume_bullet_after_completion".
- If any evidence_matches row has match_status "weak" or "no", include at least one skill_gap_roadmaps
  item for that gap (up to the max), unless every requirement is clearly matched.
- recommended_keywords: include 5-15 short phrases taken from the JD (skills, tools, domains) the
  candidate could truthfully align with; do not leave this array empty unless the JD has no skills text.
- improved_bullets: each entry must have non-empty "original" (verbatim from the resume) and non-empty
  "improved"; if none qualify, use an empty array [] — do not emit placeholder objects.

The resume text and job description follow this message under the headings "## Resume text" and "## Job description".
"""


def build_analysis_prompt(
    *,
    today_iso: str,
    resume: str,
    jd: str,
    fresher_mode: bool,
    indian_context: bool,
) -> str:
    if fresher_mode:
        fresher_mode_section = (
            "FRESHER/STUDENT MODE IS ON: Prioritize projects, internships, certifications, "
            "coursework, hackathons, academic achievements, final-year or mini projects, and any "
            "GitHub or LinkedIn URLs or handles present in the resume text. Do not judge the "
            "candidate like a mid-career professional when formal work experience is sparse. "
            "For section_scores.experience, internships plus relevant projects and volunteering "
            "count as experience."
        )
    else:
        fresher_mode_section = (
            "FRESHER MODE IS OFF: Use a balanced professional lens. Still fill evidence_matches "
            "and skill_gap_roadmaps. Set fresher_insights.profile_type to \"general\" unless the "
            "resume is clearly student or intern focused."
        )

    if indian_context:
        indian_context_section = (
            "INDIAN CAMPUS / ENTRY CONTEXT: Prefer clarity for campus placements, internships, "
            "and service-based or startup entry roles (for example clear CGPA if stated, project "
            "depth, technologies used). Do not invent TCS, Infosys, Wipro, or other employer "
            "experience or credentials."
        )
    else:
        indian_context_section = ""

    rules = _EVALUATOR_RULES.format(
        today_iso=today_iso,
        fresher_mode="true" if fresher_mode else "false",
        indian_context_section=indian_context_section,
        fresher_mode_section=fresher_mode_section,
        max_evidence=MAX_EVIDENCE_ROWS,
        max_roadmaps=MAX_SKILL_ROADMAPS,
        max_bullets=MAX_IMPROVED_BULLETS,
    )
    return (
        rules
        + "\n\n## Resume text\n\n"
        + resume
        + "\n\n## Job description\n\n"
        + jd
    )


_STRUCTURED_REPAIR_PROMPT = """Fix the JSON so it validates as the ATS analysis object (snake_case keys from the evaluator prompt).

Rules:
- Return only valid JSON (no markdown fences, no commentary).
- Preserve the intended meaning of the original where possible.
- Fill missing required fields with honest empty strings or empty arrays where appropriate.
- Do not invent resume evidence or employers.
- evidence_matches: at most {max_evidence} items.
- skill_gap_roadmaps: at most {max_roadmaps} items; each learning_plan must have 3 to 7 steps.
- improved_bullets: at most {max_bullets} items.

Validation error:
{error}

Invalid or partial JSON:
---
{invalid_json}
---
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


def _strip_json_fences(text: str) -> str:
    t = text.strip()
    t = t.removeprefix("```json").removeprefix("```JSON").removeprefix("```")
    t = t.removesuffix("```").strip()
    return t


def _parse_and_validate_ats(text: str) -> ATSResult:
    raw = _strip_json_fences(text)
    return ATSResult.model_validate_json(raw)


def _repair_structured_response(invalid_text: str, error: str) -> ATSResult:
    prompt = _STRUCTURED_REPAIR_PROMPT.format(
        error=error[:8000],
        invalid_json=invalid_text[:120000],
        max_evidence=MAX_EVIDENCE_ROWS,
        max_roadmaps=MAX_SKILL_ROADMAPS,
        max_bullets=MAX_IMPROVED_BULLETS,
    )
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=_genai_json_config(),
    )
    return _parse_and_validate_ats(response.text or "{}")


def _minimal_parse_failure_result(message: str) -> dict:
    return finalize_analysis_result(
        {
            "ats_score": 0,
            "overall_feedback": message,
            "matched_skills": [],
            "missing_skills": [],
            "weak_sections": [],
            "improvement_suggestions": [],
            "recommended_keywords": [],
            "rewritten_summary": "",
            "improved_bullets": [],
            "final_recommendation": "Try analyzing again. If this persists, shorten the resume or job description.",
        }
    )


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


def _weak_section_to_str(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        area = item.get("area") or ""
        sug = item.get("suggestion") or ""
        if area and sug:
            return f"{area}: {sug}"
        return str(sug or area or "")
    return str(item)


def _looks_like_false_future_flag(text: str, today: date) -> bool:
    lower = text.lower()
    if "future" not in lower:
        return False

    mentioned_dates = _extract_month_year_dates(text)
    if not mentioned_dates:
        return False

    has_true_future = any(d > today for d in mentioned_dates)
    return not has_true_future


def _normalize_weak_sections_list(result: dict) -> None:
    raw = result.get("weak_sections")
    if not isinstance(raw, list):
        result["weak_sections"] = []
        return
    result["weak_sections"] = [_weak_section_to_str(v) for v in raw]


def _post_validate_result(result: dict, today: date) -> dict:
    _normalize_weak_sections_list(result)
    for key in ("improvement_suggestions", "weak_sections"):
        values = result.get(key, [])
        if not isinstance(values, list):
            continue
        kept = []
        for v in values:
            if key == "weak_sections":
                text = v if isinstance(v, str) else _weak_section_to_str(v)
                if isinstance(text, str) and _looks_like_false_future_flag(text, today):
                    continue
                kept.append(text)
            else:
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
    out = dict(d)
    aliases = (
        ("atsScore", "ats_score"),
        ("ATS_Score", "ats_score"),
        ("ats", "ats_score"),
        ("sectionScores", "section_scores"),
        ("section_scores_detail", "section_scores"),
        ("overallFeedback", "overall_feedback"),
        ("matchedSkills", "matched_skills"),
        ("missingSkills", "missing_skills"),
        ("weakSections", "weak_sections"),
        ("improvementSuggestions", "improvement_suggestions"),
        ("recommendedKeywords", "recommended_keywords"),
        ("rewrittenSummary", "rewritten_summary"),
        ("improvedBullets", "improved_bullets"),
        ("finalRecommendation", "final_recommendation"),
        ("fresherInsights", "fresher_insights"),
        ("evidenceMatches", "evidence_matches"),
        ("skillGapRoadmaps", "skill_gap_roadmaps"),
    )
    for alt, canonical in aliases:
        if alt in out and (
            canonical not in out or _is_missing_or_empty(out.get(canonical))
        ):
            out[canonical] = out[alt]
    return out


def _unwrap_nested_payload(d: dict) -> dict:
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

    if ats > 0 and all(v == 0 for v in normalized.values()):
        normalized = {k: ats for k in defaults}

    result["section_scores"] = normalized
    return result


def _canonical_match_status(raw) -> str:
    if raw is None:
        return "no"
    s = str(raw).lower().strip()
    if s in ("yes", "y", "true", "matched", "strong", "full"):
        return "yes"
    if s in ("weak", "partial", "low", "maybe", "limited"):
        return "weak"
    if s in ("no", "n", "false", "missing", "none", "not"):
        return "no"
    if "weak" in s:
        return "weak"
    if "yes" in s or "match" in s:
        return "yes"
    return "no"


def _default_per_section_notes() -> dict[str, str]:
    return {
        "projects": "",
        "internships": "",
        "certifications": "",
        "technical_skills": "",
        "education": "",
        "links_github_linkedin": "",
    }


def _default_fresher_insights() -> dict:
    return {
        "profile_type": "general",
        "strongest_section": "",
        "strongest_section_why": "",
        "experience_substitute": "",
        "per_section_notes": _default_per_section_notes(),
        "priority_actions": [],
    }


def _normalize_fresher_insights(raw) -> dict:
    base = _default_fresher_insights()
    if not isinstance(raw, dict):
        return base
    out = dict(base)
    pt = raw.get("profile_type")
    if isinstance(pt, str) and pt.strip():
        out["profile_type"] = pt.strip()
    for key in (
        "strongest_section",
        "strongest_section_why",
        "experience_substitute",
    ):
        v = raw.get(key)
        if isinstance(v, str):
            out[key] = v.strip()
    notes = raw.get("per_section_notes")
    pn = _default_per_section_notes()
    if isinstance(notes, dict):
        for k in pn:
            val = notes.get(k)
            if isinstance(val, str):
                pn[k] = val.strip()
    out["per_section_notes"] = pn
    pa = raw.get("priority_actions")
    if isinstance(pa, list):
        out["priority_actions"] = [
            str(x).strip() for x in pa if str(x).strip()
        ]
    return out


def _normalize_evidence_matches(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    rows = []
    for item in raw[:MAX_EVIDENCE_ROWS]:
        if not isinstance(item, dict):
            continue
        req = item.get("requirement") or item.get("jd_requirement") or ""
        rows.append(
            {
                "requirement": str(req).strip(),
                "match_status": _canonical_match_status(
                    item.get("match_status") or item.get("status")
                ),
                "resume_evidence": str(
                    item.get("resume_evidence") or item.get("evidence") or ""
                ).strip(),
                "where_in_resume": str(
                    item.get("where_in_resume")
                    or item.get("location")
                    or item.get("section")
                    or ""
                ).strip(),
            }
        )
    return [r for r in rows if r["requirement"]]


def _normalize_skill_gap_roadmaps(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw[:MAX_SKILL_ROADMAPS]:
        if not isinstance(item, dict):
            continue
        skill = (
            item.get("skill_or_requirement")
            or item.get("skillOrRequirement")
            or item.get("skill")
            or item.get("gap")
            or item.get("gap_title")
            or item.get("requirement")
            or item.get("title")
            or item.get("topic")
            or ""
        )
        skill = str(skill).strip()
        if not skill:
            continue
        mp = item.get("mini_project")
        if not isinstance(mp, dict):
            mp = {}
        stack = mp.get("suggested_stack") or mp.get("stack") or []
        if not isinstance(stack, list):
            stack = [str(stack)]
        stack = [str(s).strip() for s in stack if str(s).strip()]
        plan = item.get("learning_plan") or item.get("steps") or []
        if isinstance(plan, str):
            plan = [plan]
        if not isinstance(plan, list):
            plan = []
        plan = [str(p).strip() for p in plan if str(p).strip()]
        out.append(
            {
                "skill_or_requirement": skill,
                "why_it_matters_for_this_role": str(
                    item.get("why_it_matters_for_this_role") or ""
                ).strip(),
                "learning_plan": plan[:10],
                "mini_project": {
                    "title": str(mp.get("title") or "").strip(),
                    "description": str(mp.get("description") or "").strip(),
                    "suggested_stack": stack[:12],
                    "demo_idea": str(mp.get("demo_idea") or "").strip(),
                },
                "honest_resume_bullet_after_completion": str(
                    item.get("honest_resume_bullet_after_completion")
                    or item.get("resume_bullet_after_completion")
                    or ""
                ).strip(),
            }
        )
    return out


def _cap_improved_bullets(result: dict) -> dict:
    bullets = result.get("improved_bullets")
    if not isinstance(bullets, list):
        result["improved_bullets"] = []
        return result
    capped = []
    for b in bullets[:MAX_IMPROVED_BULLETS]:
        if not isinstance(b, dict):
            continue
        orig = str(b.get("original", b.get("before", ""))).strip()
        imp = str(b.get("improved", b.get("after", ""))).strip()
        if not orig:
            continue
        capped.append({"original": orig, "improved": imp})
    result["improved_bullets"] = capped
    return result


def finalize_analysis_result(result: dict) -> dict:
    """
    Normalize keys, ATS, section scores, fresher_insights, evidence_matches,
    and skill_gap_roadmaps. Safe for fresh API output or stale session_state.
    """
    if not isinstance(result, dict):
        return result
    out = _unwrap_nested_payload(_merge_key_aliases(result))
    out["ats_score"] = _coerce_ats_value(out.get("ats_score"))
    _normalize_section_scores(out)
    _normalize_weak_sections_list(out)
    out["fresher_insights"] = _normalize_fresher_insights(out.get("fresher_insights"))
    out["evidence_matches"] = _normalize_evidence_matches(out.get("evidence_matches"))
    out["skill_gap_roadmaps"] = _normalize_skill_gap_roadmaps(
        out.get("skill_gap_roadmaps")
    )
    _cap_improved_bullets(out)
    return out


def analyze(
    resume_text: str,
    jd_text: str,
    *,
    fresher_mode: bool = True,
    indian_context: bool = False,
) -> dict:
    today = date.today()
    today_iso = today.isoformat()
    prompt = build_analysis_prompt(
        today_iso=today_iso,
        resume=resume_text,
        jd=jd_text,
        fresher_mode=fresher_mode,
        indian_context=indian_context,
    )
    cfg = _genai_json_config()
    response = _generate_content_with_retry(prompt=prompt, model=MODEL_ID, config=cfg)
    text = (response.text or "").strip()

    try:
        ats = _parse_and_validate_ats(text)
    except (json.JSONDecodeError, ValidationError, ValueError) as e:
        try:
            ats = _repair_structured_response(text, str(e))
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError, AttributeError):
            parsed = _minimal_parse_failure_result(
                "The model returned invalid or incomplete JSON. A schema repair pass also failed."
            )
            return _post_validate_result(parsed, today)

    parsed = finalize_analysis_result(ats.model_dump(mode="python"))
    return _post_validate_result(parsed, today)
