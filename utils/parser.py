import docx
import pdfplumber


def extract_text(file) -> str:
    if file.name.endswith(".pdf"):
        with pdfplumber.open(file) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    if file.name.endswith(".docx"):
        doc = docx.Document(file)
        return "\n".join(paragraph.text for paragraph in doc.paragraphs)
    return ""
