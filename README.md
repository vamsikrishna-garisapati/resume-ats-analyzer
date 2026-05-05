# Resume ATS Analyzer

A small **Streamlit** app that uploads a resume (**PDF** or **DOCX**), compares it to a job description, and uses **Google Gemini** to produce an ATS-style report: scores, skill gaps, rewrites, cover letter, and a downloadable PDF.

## Features

- **Resume parsing** — `pdfplumber` (PDF) and `python-docx` (DOCX)
- **AI analysis** — structured JSON via `google-genai` (default model: `gemini-2.5-flash`)
- **Overall ATS score** plus **section scores** (skills, experience, projects, format)
- **Matched / missing skills**, recommended keywords, weak sections, improvement tips
- **Bullet rewrites** and **rewritten summary**
- **Cover letter** generator (separate prompt) with **TXT download**
- **PDF report** export (`fpdf2`), with Unicode-friendly fonts when available on your OS

## Requirements

- **Python 3.11+** (3.13 works)
- A **Gemini API key** from [Google AI Studio](https://aistudio.google.com/apikey)

## Quick start

### 1. Clone and enter the project

```bash
git clone https://github.com/vamsikrishna-garisapati/resume-ats-analyzer.git
cd resume-ats-analyzer
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

**Windows (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy the example file and add your key:

```bash
copy .env.example .env
```

On macOS/Linux use `cp .env.example .env`.

Edit `.env`:

```env
GEMINI_API_KEY=your_key_here
```

Alternatively you can set `GOOGLE_API_KEY` — the app accepts either name.

### 5. Run the app

```bash
streamlit run streamlit_app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`).

## Project layout

```text
.
├── streamlit_app.py       # Streamlit UI (matches Streamlit Cloud default name)
├── requirements.txt       # Direct Python dependencies
├── .env.example           # Example env (no secrets)
├── utils/
│   ├── parser.py          # PDF / DOCX → text
│   ├── analyzer.py      # Gemini: structured analysis + normalization
│   ├── cover_letter.py  # Gemini: cover letter text
│   └── export.py        # PDF export
└── README.md
```

## Deploying (Streamlit Community Cloud)

1. Push this repo to GitHub (so `streamlit_app.py` exists on the branch you select).
2. In [Streamlit Cloud](https://share.streamlit.io/), create an app and set **Main file path** to **`streamlit_app.py`** (Streamlit’s default).
3. Under **Settings → Secrets**, add:

   ```toml
   GEMINI_API_KEY = "your_key_here"
   ```

4. Redeploy if prompted.

> **Note:** `python-dotenv` loads `.env` locally. On Streamlit Cloud, use **Secrets** instead of committing `.env`.

## Git: “dubious ownership” on Windows

If `git add` fails with *detected dubious ownership*, allow this directory once:

```bash
git config --global --add safe.directory E:/Resume
```

Use your actual project path if different.

## Security

- **Never commit `.env`** — it is listed in `.gitignore`.
- Rotate your API key if it was ever committed or shared.

## License

Use or adapt for your portfolio; add a `LICENSE` file if you want a formal terms.
