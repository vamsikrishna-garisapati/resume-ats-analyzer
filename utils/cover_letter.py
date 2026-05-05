from utils.analyzer import MODEL_ID, client


def generate_cover_letter(summary: str, jd_text: str) -> str:
    prompt = f"""
Write a concise, professional cover letter based on:
- Candidate summary: {summary}
- Job description: {jd_text}

Keep it to 250-350 words. Use a strong opening, relevant achievements, and a clear close.
Return plain text only.
"""
    response = client.models.generate_content(model=MODEL_ID, contents=prompt)
    return (response.text or "").strip()
