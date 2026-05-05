import os
import platform
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos


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
        "Resume analysis report",
        "",
        f"Overall ATS score: {result.get('ats_score', 'N/A')}/100",
        "",
        "Section scores (0-100):",
        f"  Skills: {skills}",
        f"  Experience: {exp}",
        f"  Projects: {proj}",
        f"  Format: {fmt}",
        "",
        "Overall feedback:",
        str(result.get("overall_feedback", "")),
        "",
        "Matched skills: " + ", ".join(result.get("matched_skills", []) or []),
        "Missing skills: " + ", ".join(result.get("missing_skills", []) or []),
        "",
        "Recommended keywords: "
        + ", ".join(result.get("recommended_keywords", []) or []),
        "",
        "Weak sections:",
    ]
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
