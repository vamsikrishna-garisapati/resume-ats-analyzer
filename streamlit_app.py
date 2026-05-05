import streamlit as st

from utils.analyzer import analyze, finalize_analysis_result
from utils.cover_letter import generate_cover_letter
from utils.export import export_pdf
from utils.parser import extract_text

st.set_page_config(page_title="AI Resume Analyzer", layout="wide")
st.title("AI Resume Analyzer")

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


def show_report(result: dict, job_description: str):
    result = finalize_analysis_result(dict(result))
    st.session_state["analysis_result"] = result

    score = int(result.get("ats_score", 0))
    color = "green" if score >= 70 else "orange" if score >= 50 else "red"
    st.markdown(f"## ATS Score: :{color}[{score}/100]")
    st.progress(max(0, min(score, 100)) / 100)
    st.info(result.get("overall_feedback", "No overall feedback provided."))

    st.subheader("Section scores")
    ss = result.get("section_scores") or {}
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        s = int(ss.get("skills", 0))
        st.metric("Skills", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)
    with c2:
        s = int(ss.get("experience", 0))
        st.metric("Experience", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)
    with c3:
        s = int(ss.get("projects", 0))
        st.metric("Projects", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)
    with c4:
        s = int(ss.get("format", 0))
        st.metric("Format", f"{s}/100")
        st.progress(max(0, min(s, 100)) / 100)

    col_a, col_b = st.columns(2)
    with col_a:
        st.success("Matched Skills")
        for skill in result.get("matched_skills", []):
            st.write(f"- {skill}")
    with col_b:
        st.error("Missing Skills")
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

    st.subheader("Improvement Suggestions")
    for idx, tip in enumerate(result.get("improvement_suggestions", []), 1):
        st.write(f"{idx}. {tip}")

    st.subheader("Bullet Point Rewrites")
    for bullet in result.get("improved_bullets", []):
        st.markdown(f"**Before:** {bullet.get('original', '')}")
        st.markdown(f"**After:** `{bullet.get('improved', '')}`")
        st.divider()

    st.subheader("Rewritten Summary")
    rewritten_summary = result.get("rewritten_summary", "")
    st.write(rewritten_summary)

    st.subheader("Final recommendation")
    st.write(result.get("final_recommendation", "") or "—")

    if st.button("Generate Cover Letter"):
        with st.spinner("Writing cover letter..."):
            st.session_state["cover_letter"] = generate_cover_letter(
                rewritten_summary, job_description
            )

    cover = st.session_state.get("cover_letter")
    if cover:
        st.text_area("Cover Letter", cover, height=400)
        st.download_button(
            label="Download cover letter (TXT)",
            data=cover,
            file_name="cover_letter.txt",
            mime="text/plain",
            key="download_cover_letter",
        )

    pdf_bytes = export_pdf(result)
    st.download_button(
        "Download Report (PDF)",
        pdf_bytes,
        "resume_report.pdf",
        key="download_report_pdf",
    )


if st.button("Analyze") and file and jd:
    with st.spinner("Analyzing..."):
        resume_text = extract_text(file)
        result = analyze(resume_text, jd)
    st.session_state["analysis_result"] = result
    st.session_state["cover_letter"] = ""
    st.session_state["last_jd"] = jd

if st.session_state.get("analysis_result"):
    show_report(st.session_state["analysis_result"], st.session_state.get("last_jd", ""))
