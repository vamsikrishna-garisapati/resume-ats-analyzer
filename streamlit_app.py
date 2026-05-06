import streamlit as st

from utils.analyzer import analyze, finalize_analysis_result
from utils.cover_letter import generate_cover_letter
from utils.export import export_pdf
from utils.parser import extract_text

st.set_page_config(page_title="FresherFit AI", layout="wide")

st.title("FresherFit AI")
st.caption(
    "Turn your student resume into a job-ready application package — proof mapping, "
    "honest rewrites, and skill gap roadmaps (not just keyword matching)."
)

if "fresher_mode" not in st.session_state:
    st.session_state["fresher_mode"] = True
if "indian_context" not in st.session_state:
    st.session_state["indian_context"] = False
if "last_fresher_mode" not in st.session_state:
    st.session_state["last_fresher_mode"] = True

col_opts1, col_opts2 = st.columns(2)
with col_opts1:
    fresher_mode = st.toggle(
        "Fresher / student mode",
        value=st.session_state["fresher_mode"],
        help="Weights projects, internships, certifications, and coursework instead of only full-time jobs.",
    )
    st.session_state["fresher_mode"] = fresher_mode
with col_opts2:
    indian_context = st.toggle(
        "Indian campus / entry context",
        value=st.session_state["indian_context"],
        help="Tailors guidance for campus placements and entry-level tech roles in India — without inventing credentials.",
    )
    st.session_state["indian_context"] = indian_context

col1, col2 = st.columns(2)
with col1:
    file = st.file_uploader("Upload Resume (PDF/DOCX)", type=["pdf", "docx"])
with col2:
    jd = st.text_area("Paste Job Description", height=300)


def _weak_item_label(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        area = item.get("area") or ""
        sug = item.get("suggestion") or ""
        if area and sug:
            return f"**{area}** — {sug}"
        return sug or area or ""
    return str(item)


def _status_badge(status: str) -> str:
    s = (status or "").lower()
    if s == "yes":
        return "yes"
    if s == "weak":
        return "weak"
    return "no"


def _show_fresher_insights(fi: dict, fresher_on: bool):
    st.subheader("Fresher insights" if fresher_on else "Profile notes")
    if not isinstance(fi, dict):
        st.caption("No insights available.")
        return
    st.write(
        f"**Profile type:** `{fi.get('profile_type', 'general')}`  "
        f"**Strongest section:** {fi.get('strongest_section', '—')}"
    )
    why = fi.get("strongest_section_why") or ""
    if why:
        st.write(why)
    sub = fi.get("experience_substitute") or ""
    if sub:
        st.markdown(f"**Where your proof lives:** {sub}")
    notes = fi.get("per_section_notes") or {}
    if isinstance(notes, dict) and any(str(v).strip() for v in notes.values()):
        st.markdown("**Section notes**")
        labels = {
            "projects": "Projects",
            "internships": "Internships",
            "certifications": "Certifications",
            "technical_skills": "Technical skills",
            "education": "Education",
            "links_github_linkedin": "GitHub / LinkedIn",
        }
        for key, label in labels.items():
            text = notes.get(key) if isinstance(notes, dict) else ""
            if isinstance(text, str) and text.strip():
                with st.expander(label):
                    st.write(text.strip())
    actions = fi.get("priority_actions") or []
    if isinstance(actions, list) and actions:
        st.markdown("**Priority actions (for this job)**")
        for i, a in enumerate(actions, 1):
            st.write(f"{i}. {a}")


def _show_evidence_table(rows: list):
    st.subheader("Resume evidence match")
    st.caption(
        "Each row ties a job requirement to what is actually evidenced in your resume — "
        "not keyword stuffing."
    )
    if not rows:
        st.caption("No evidence rows returned.")
        return
    st.dataframe(
        {
            "Job requirement": [r.get("requirement", "") for r in rows],
            "Match": [_status_badge(r.get("match_status", "")) for r in rows],
            "Resume evidence": [r.get("resume_evidence", "") for r in rows],
            "Where in resume": [r.get("where_in_resume", "") for r in rows],
        },
        use_container_width=True,
        hide_index=True,
    )


def _show_skill_roadmaps(roadmaps: list):
    st.subheader("Skill gap roadmaps")
    st.caption(
        "Mini-projects and learning steps you can do next. "
        "Suggested bullets are for after you complete the work — we do not invent past experience."
    )
    if not roadmaps:
        st.caption("No roadmaps returned.")
        return
    for i, rm in enumerate(roadmaps, 1):
        if not isinstance(rm, dict):
            continue
        title = rm.get("skill_or_requirement") or f"Gap {i}"
        with st.expander(f"{i}. {title}", expanded=(i <= 2)):
            why = rm.get("why_it_matters_for_this_role") or ""
            if why:
                st.write(why)
            plan = rm.get("learning_plan") or []
            if isinstance(plan, list) and plan:
                st.markdown("**Learning plan**")
                for step in plan:
                    st.write(f"- {step}")
            mp = rm.get("mini_project") or {}
            if isinstance(mp, dict) and (
                mp.get("title") or mp.get("description")
            ):
                st.markdown("**Suggested mini-project**")
                if mp.get("title"):
                    st.write(f"*{mp.get('title')}*")
                if mp.get("description"):
                    st.write(mp.get("description"))
                stack = mp.get("suggested_stack") or []
                if isinstance(stack, list) and stack:
                    st.write("**Stack:** " + ", ".join(str(s) for s in stack))
                if mp.get("demo_idea"):
                    st.write(f"**Demo idea:** {mp.get('demo_idea')}")
            bullet = rm.get("honest_resume_bullet_after_completion") or ""
            if bullet:
                st.markdown("**Honest resume bullet (after you complete the project)**")
                st.code(bullet, language=None)


def show_report(result: dict, job_description: str):
    result = finalize_analysis_result(dict(result))
    st.session_state["analysis_result"] = result

    score = int(result.get("ats_score", 0))
    color = "green" if score >= 70 else "orange" if score >= 50 else "red"
    st.markdown(f"## Job fit score: :{color}[{score}/100]")
    st.caption("Scores reflect overlap and proof quality for this job description — not a generic keyword count.")
    st.progress(max(0, min(score, 100)) / 100)
    st.info(result.get("overall_feedback", "No overall feedback provided."))

    st.subheader("Section scores")
    ss = result.get("section_scores") or {}
    exp_label = (
        "Experience / internships"
        if st.session_state.get("last_fresher_mode", True)
        else "Experience"
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        s = int(ss.get("skills", 0))
        st.metric("Skills", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)
    with c2:
        s = int(ss.get("experience", 0))
        st.metric(exp_label, f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)
    with c3:
        s = int(ss.get("projects", 0))
        st.metric("Projects", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)
    with c4:
        s = int(ss.get("format", 0))
        st.metric("Format", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)

    fi = result.get("fresher_insights") or {}
    _show_fresher_insights(fi, st.session_state.get("last_fresher_mode", True))

    _show_evidence_table(result.get("evidence_matches") or [])

    _show_skill_roadmaps(result.get("skill_gap_roadmaps") or [])

    st.divider()
    st.markdown("### More detail")

    col_a, col_b = st.columns(2)
    with col_a:
        st.success("Matched skills")
        for skill in result.get("matched_skills", []):
            st.write(f"- {skill}")
    with col_b:
        st.error("Missing or weak skills (summary)")
        for skill in result.get("missing_skills", []):
            st.write(f"- {skill}")

    st.subheader("Recommended keywords")
    kws = result.get("recommended_keywords") or []
    if kws:
        st.write(", ".join(str(k) for k in kws))
    else:
        st.caption("No keywords suggested.")

    st.subheader("Weak sections")
    weak = result.get("weak_sections") or []
    if weak:
        for w in weak:
            st.markdown(f"- {_weak_item_label(w)}")
    else:
        st.caption("No weak sections flagged.")

    st.subheader("Improvement suggestions")
    for idx, tip in enumerate(result.get("improvement_suggestions", []), 1):
        st.write(f"{idx}. {tip}")

    st.subheader("Bullet point rewrites (honest)")
    for bullet in result.get("improved_bullets", []):
        st.markdown(f"**Before:** {bullet.get('original', '')}")
        st.markdown(f"**After:** `{bullet.get('improved', '')}`")
        st.divider()

    st.subheader("Rewritten summary")
    rewritten_summary = result.get("rewritten_summary", "")
    st.write(rewritten_summary)

    st.subheader("Final recommendation")
    st.write(result.get("final_recommendation", "") or "—")

    if st.button("Generate cover letter"):
        with st.spinner("Writing cover letter..."):
            st.session_state["cover_letter"] = generate_cover_letter(
                rewritten_summary, job_description
            )

    cover = st.session_state.get("cover_letter")
    if cover:
        st.text_area("Cover letter", cover, height=400)
        st.download_button(
            label="Download cover letter (TXT)",
            data=cover,
            file_name="cover_letter.txt",
            mime="text/plain",
            key="download_cover_letter",
        )

    pdf_bytes = export_pdf(result)
    st.download_button(
        "Download report (PDF)",
        pdf_bytes,
        "fresherfit_report.pdf",
        key="download_report_pdf",
    )


if st.button("Analyze") and file and jd:
    with st.spinner("Analyzing..."):
        resume_text = extract_text(file)
        result = analyze(
            resume_text,
            jd,
            fresher_mode=st.session_state.get("fresher_mode", True),
            indian_context=st.session_state.get("indian_context", False),
        )
    st.session_state["analysis_result"] = result
    st.session_state["cover_letter"] = ""
    st.session_state["last_jd"] = jd
    st.session_state["last_fresher_mode"] = st.session_state.get("fresher_mode", True)

if st.session_state.get("analysis_result"):
    show_report(st.session_state["analysis_result"], st.session_state.get("last_jd", ""))
