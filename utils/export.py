import os
import platform
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from utils.analyzer import finalize_analysis_result


def _unicode_font_candidates() -> list[Path]:
    system = platform.system()
    if system == "Windows":
        fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        return [
            fonts / "arialuni.ttf",
            fonts / "segoeui.ttf",
            fonts / "seguisym.ttf",
        ]
    if system == "Darwin":
        return [
            Path("/Library/Fonts/Arial Unicode.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        ]
    return [
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
    ]


def _register_unicode_font(pdf: FPDF, size: int = 12) -> bool:
    for path in _unicode_font_candidates():
        if path.is_file():
            pdf.add_font("ReportUnicode", "", str(path))
            pdf.set_font("ReportUnicode", size=size)
            return True
    pdf.set_font("Helvetica", size=size)
    return False


def _safe_text(text: str) -> str:
    """Fallback when no Unicode TTF is available (core fonts are Latin-1 only)."""
    replacements = {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "--",
        "\u2026": "...",
        "\u00a0": " ",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


def _weak_line(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        area = item.get("area") or ""
        sug = item.get("suggestion") or ""
        if area and sug:
            return f"{area}: {sug}"
        return sug or area or ""
    return str(item)


def _fresher_insight_lines(fi: dict) -> list[str]:
    if not isinstance(fi, dict):
        return []
    lines: list[str] = [
        "Fresher / profile insights:",
        f"  Profile type: {fi.get('profile_type', '')}",
        f"  Strongest section: {fi.get('strongest_section', '')}",
    ]
    why = fi.get("strongest_section_why") or ""
    if why:
        lines.append(f"  Why: {why}")
    sub = fi.get("experience_substitute") or ""
    if sub:
        lines.append(f"  Proof focus: {sub}")
    notes = fi.get("per_section_notes") or {}
    if isinstance(notes, dict):
        for key, label in (
            ("projects", "Projects"),
            ("internships", "Internships"),
            ("certifications", "Certifications"),
            ("technical_skills", "Technical skills"),
            ("education", "Education"),
            ("links_github_linkedin", "Links"),
        ):
            val = notes.get(key)
            if isinstance(val, str) and val.strip():
                lines.append(f"  {label}: {val.strip()}")
    actions = fi.get("priority_actions") or []
    if isinstance(actions, list) and actions:
        lines.append("  Priority actions:")
        for i, a in enumerate(actions, 1):
            lines.append(f"    {i}. {a}")
    return lines


def _evidence_lines(rows: list) -> list[str]:
    lines: list[str] = ["Resume evidence match:", ""]
    if not rows:
        lines.append("  (none listed)")
        return lines
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"  {i}. [{row.get('match_status', '')}] {row.get('requirement', '')}"
        )
        lines.append(f"     Where: {row.get('where_in_resume', '')}")
        lines.append(f"     Evidence: {row.get('resume_evidence', '')}")
        lines.append("")
    return lines


def _roadmap_lines(roadmaps: list) -> list[str]:
    lines: list[str] = ["Skill gap roadmaps:", ""]
    if not roadmaps:
        lines.append("  (none listed)")
        return lines
    for i, rm in enumerate(roadmaps, 1):
        if not isinstance(rm, dict):
            continue
        title = rm.get("skill_or_requirement") or f"Item {i}"
        lines.append(f"  {i}. {title}")
        why = rm.get("why_it_matters_for_this_role") or ""
        if why:
            lines.append(f"     Why it matters: {why}")
        plan = rm.get("learning_plan") or []
        if isinstance(plan, list) and plan:
            lines.append("     Learning plan:")
            for step in plan[:10]:
                lines.append(f"       - {step}")
        mp = rm.get("mini_project") or {}
        if isinstance(mp, dict):
            if mp.get("title"):
                lines.append(f"     Project: {mp.get('title')}")
            if mp.get("description"):
                lines.append(f"     {mp.get('description')}")
            stack = mp.get("suggested_stack") or []
            if isinstance(stack, list) and stack:
                lines.append("     Stack: " + ", ".join(str(s) for s in stack))
            if mp.get("demo_idea"):
                lines.append(f"     Demo: {mp.get('demo_idea')}")
        bullet = rm.get("honest_resume_bullet_after_completion") or ""
        if bullet:
            lines.append(f"     Bullet after completion: {bullet}")
        lines.append("")
    return lines

def _write_blocks(pdf: FPDF, usable_w: float, using_unicode: bool, blocks: list[str]) -> None:
    for block in blocks:
        if block == "":
            pdf.ln(4)
            continue
        pdf.set_x(pdf.l_margin)
        text = block if using_unicode else _safe_text(block)
        pdf.multi_cell(
            w=usable_w,
            h=8,
            text=text,
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )


def export_pdf(result: dict) -> bytes:
    if isinstance(result, dict):
        result = finalize_analysis_result(dict(result))
    else:
        result = finalize_analysis_result({})

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.add_page()
    using_unicode = _register_unicode_font(pdf, size=12)
    usable_w = pdf.epw

    ss = result.get("section_scores") or {}
    skills = ss.get("skills", 0)
    exp = ss.get("experience", 0)
    proj = ss.get("projects", 0)
    fmt = ss.get("format", 0)

    weak_lines = [_weak_line(w) for w in result.get("weak_sections", [])]
    weak_lines = [w for w in weak_lines if w]

    bullets = result.get("improved_bullets") or []
    bullet_lines: list[str] = []
    for i, b in enumerate(bullets, 1):
        if not isinstance(b, dict):
            continue
        o = b.get("original", "")
        imp = b.get("improved", "")
        bullet_lines.append(f"{i}. Before: {o}")
        bullet_lines.append(f"   After: {imp}")

    suggestions = result.get("improvement_suggestions") or []
    sug_lines = []
    for i, s in enumerate(suggestions, 1):
        sug_lines.append(f"{i}. {s}")

    blocks: list[str] = [
        "FresherFit AI — report",
        "",
        f"Overall job fit score: {result.get('ats_score', 'N/A')}/100",
        "",
        "Section scores (0-100):",
        f"  Skills: {skills}",
        f"  Experience (includes internships/projects when relevant): {exp}",
        f"  Projects: {proj}",
        f"  Format: {fmt}",
        "",
        "Overall feedback:",
        str(result.get("overall_feedback", "")),
        "",
    ]
    blocks.extend(_fresher_insight_lines(result.get("fresher_insights") or {}))
    blocks.append("")
    blocks.extend(_evidence_lines(result.get("evidence_matches") or []))
    blocks.append("")
    blocks.extend(_roadmap_lines(result.get("skill_gap_roadmaps") or []))
    blocks.extend(
        [
            "Matched skills: " + ", ".join(result.get("matched_skills", []) or []),
            "Missing skills: " + ", ".join(result.get("missing_skills", []) or []),
            "",
            "Recommended keywords: "
            + ", ".join(result.get("recommended_keywords", []) or []),
            "",
            "Weak sections:",
        ]
    )
    if weak_lines:
        blocks.extend(weak_lines)
    else:
        blocks.append("  (none listed)")
    blocks.extend(
        [
            "",
            "Improvement suggestions:",
        ]
    )
    if sug_lines:
        blocks.extend(sug_lines)
    else:
        blocks.append("  (none listed)")
    blocks.extend(
        [
            "",
            "Bullet point rewrites:",
        ]
    )
    if bullet_lines:
        blocks.extend(bullet_lines)
    else:
        blocks.append("  (none listed)")
    blocks.extend(
        [
            "",
            "Rewritten summary:",
            str(result.get("rewritten_summary", "")),
            "",
            "Final recommendation:",
            str(result.get("final_recommendation", "")),
        ]
    )

    _write_blocks(pdf, usable_w, using_unicode, blocks)
    return bytes(pdf.output(dest="S"))
