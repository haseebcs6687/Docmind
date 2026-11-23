# Progress Log

## Step 1: Initial Project Setup
- **What was built**: Initial project directory structure, base placeholder files, `.gitignore`, `.env.example`, `requirements.txt`, `README.md`, `PROJECT_CONTEXT.md`, and Python virtual environment initialization.
- **Python Version**: Python 3.13.15
- **Files Touched**:
  - `app.py`
  - `src/__init__.py`
  - `src/config.py`
  - `src/loaders.py`
  - `src/chunking.py`
  - `src/vectorstore.py`
  - `src/rag.py`
  - `data/sample_docs/.gitkeep`
  - `eval/.gitkeep`
  - `tests/.gitkeep`
  - `requirements.txt`
  - `.env.example`
  - `.gitignore`
  - `README.md`
  - `PROJECT_CONTEXT.md`
  - `docs/PROGRESS.md`
- **How it was tested**:
  - Verified directory and file layout.
  - Checked `.gitignore` rules (ensured `.env` and `.venv/` are excluded while `.env.example` is tracked).
  - Validated Python virtual environment creation in `.venv`.
- **Decisions Made**:
  - Left dependencies unpinned in `requirements.txt` until specific components are integrated in subsequent steps.
  - Set default git branch to `main`.
  - Configured project rules and progress logging standards in `PROJECT_CONTEXT.md`.

## Step 2: Gemini SDK Setup, Config Loader & Model Check Script
- **What was built**:
  - Verified and installed the currently recommended official Google GenAI Python SDK (`google-genai`) alongside `python-dotenv`.
  - Pinned exact installed versions into `requirements.txt` (`google-genai==3.6.1`, `python-dotenv==1.2.4`).
  - Implemented `src/config.py` with dynamic `.env` loading, validation of `GEMINI_API_KEY` without secret leakage, and optional reads for `GEMINI_MODEL` and `GEMINI_EMBED_MODEL`.
  - Added `GEMINI_MODEL=` and `GEMINI_EMBED_MODEL=` to `.env.example` and created local untracked `.env`.
  - Created `scripts/check_gemini.py` supporting Mode A (listing generation and embedding models in formatted tables) and Mode B (testing generation with "Say hello in Urdu" and checking vector dimension length).
  - Added `docs/ui-reference/` to `.gitignore` and updated `PROJECT_CONTEXT.md` with UI visual styling and planned pages.
- **SDK Chosen and Why**:
  - SDK: `google-genai` (v3.6.1)
  - Why: This is the official, current unified SDK recommended by Google in the Gemini API documentation (`ai.google.dev quickstart`), replacing the legacy `google-generativeai` package.
- **Model Verification & Decisions**:
  - Tested and verified `gemini-3.5-flash-lite` for text generation via Mode B in `scripts/check_gemini.py` (Urdu greeting test succeeded; `gemini-2.5-flash` returned HTTP 404 "no longer available to new users"). `gemini-3.8-flash` noted as candidate to compare in evaluation step.
  - Tested and verified `gemini-embedding-001` for embeddings via Mode B (verified 3072-dimensional vector output).
  - Documented AI Studio free-tier rate limits (~15 RPM / ~250K TPM / ~500 RPD for generation; ~100 RPM / ~30K TPM / ~1000 RPD for embeddings; resets at midnight Pacific).
  - Established architectural guardrails: batch embedding with throttling/retry backoff, vector store disk persistence, user-friendly rate limit messaging, loading model configurations from `.env`.
  - Noted check on "Interactions API" vs `generate_content` prior to Step 6 RAG implementation.
- **Python Version**: Python 3.13.15
- **Files Touched**:
  - `.gitignore`
  - `PROJECT_CONTEXT.md`
  - `requirements.txt`
  - `src/config.py`
  - `.env.example`
  - `.env` (gitignored, untracked)
  - `scripts/check_gemini.py`
  - `docs/PROGRESS.md`
- **How it was tested**:
  - Verified compilation of all created Python modules using `python -m py_compile scripts/check_gemini.py src/config.py`.
  - Confirmed `.env` and `docs/ui-reference/` are properly ignored by Git (`git status`, `git check-ignore`).
  - Verified `git ls-files` tracks only `.env.example` and not `.env`.
- **Decisions Made**:
  - Used module-level `__getattr__` and `get_gemini_api_key()` in `src/config.py` for safe key retrieval with clear error messaging when unconfigured.
  - Formatted tables in `scripts/check_gemini.py` with standard library formatting without introducing unpinned external dependencies.

## Step 3: Fictional Law Firm Demo Dataset Generation
- **What was built**:
  - Dev dependencies file `requirements-dev.txt` with pinned versions (`reportlab==5.1.0`, `python-docx==1.2.0`). Production `requirements.txt` remained untouched.
  - Generator script `scripts/generate_sample_docs.py` creating the complete fictional dataset for "Sterling & Rauf Law Associates" in `data/sample_docs/`:
    1. `Fee_Schedule_2026.pdf` (4 pages): consultation fees, hourly rates, retainers by practice area, fixed fees, payment terms, late fees, refund policy.
    2. `Practice_Areas_Brochure.pdf` (3 pages): practice areas (corporate, property, family, civil litigation, contracts, IP), leadership team, approach, explicit non-handled areas.
    3. `Client_Intake_SOP.pdf` (4 pages): staff procedures from first contact to engagement, intake form, conflict check, KYC checklists (individual & corporate), appointment booking, escalation tiers.
    4. `Confidentiality_and_Data_Policy.pdf` (3 pages): advocate-client privilege, physical & digital security, 7-year retention schedule, internal 24-hr breach notification protocol.
    5. `Client_Engagement_Letter_Template.docx` (multi-page DOCX template): comprehensive clauses covering scope, rates, retainers, billing, refunds, KYC, communication, confidentiality, termination, and signature blocks.
    6. `Client_FAQ.txt` (UTF-8): 18 English Q&As and 5 Urdu script Q&As reflecting all core facts.
  - Every document includes the mandatory disclaimer: `"Fictional demo document - not real legal advice"` and running headers/footers with dynamic page counts (`Page X of Y`).
  - Ground truth evaluation answer key `eval/dataset_facts.md` mapping 41 distinct facts with columns `Fact Description | Exact Value | Source File | Page / Section`, along with explicit negative test cases (excluded topics).
- **Excluded Topics Verified**:
  - Confirmed via automated regex grep that none of the 5 out-of-scope topics (parking, mobile wallets like JazzCash/Easypaisa, Karachi/Islamabad branch offices, staff salaries, tax-return filing) appear anywhere in the generated corpus.
- **How to Regenerate**:
  - Run `.\.venv\Scripts\python.exe scripts\generate_sample_docs.py`. The generator is idempotent and overwrites files in `data/sample_docs/`.
- **Files Touched**:
  - `requirements-dev.txt`
  - `scripts/generate_sample_docs.py`
  - `data/sample_docs/Fee_Schedule_2026.pdf`
  - `data/sample_docs/Practice_Areas_Brochure.pdf`
  - `data/sample_docs/Client_Intake_SOP.pdf`
  - `data/sample_docs/Confidentiality_and_Data_Policy.pdf`
  - `data/sample_docs/Client_Engagement_Letter_Template.docx`
  - `data/sample_docs/Client_FAQ.txt`
  - `eval/dataset_facts.md`
  - `docs/PROGRESS.md`
- **Decisions Made**:
  - Separated development-only document generation libraries into `requirements-dev.txt` to keep the production runtime dependencies lean in `requirements.txt`.
  - Implemented a two-pass `NumberedCanvas` in ReportLab to dynamically calculate total page counts without external PDF parsing tools.
  - Formatted the ground truth answer key with exact page and section locations to prepare for RAG evaluation citations in later stages.

## Step 4: Document Loaders (PDF, DOCX, TXT) with Source Metadata
- **What was built**:
  - Implemented `src/loaders.py` with `DocUnit` dataclass and source citation helper `citation_label()`.
  - Added robust parsing handlers:
    - PDF: Page-level extraction using `pypdf`, preserving 1-based page numbers. Detects scanned/unextractable PDFs gracefully without crashing.
    - DOCX: Heading-guided unit segmentation using `python-docx`'s `iter_inner_content()` to preserve sequential ordering of headings, paragraphs, and tables. Fallback to block grouping if headings are absent.
    - TXT: UTF-8 BOM-aware decoding with fallback, parsing Q&A pairs (both English `Q:` and Urdu `سوال:`) into coherent blocks with section tracking (`Q&A 1`, etc.).
    - Whitespace normalization preserving non-Latin scripts (Urdu characters preserved without mangling).
  - Added `MAX_UPLOAD_MB` configuration setting (default: 20 MB) in `src/config.py`.
  - Implemented `load_file` (supporting paths, bytes, and file-like objects for Streamlit uploads) and `load_directory` (with comprehensive loaded/skipped reporting).
  - Pinned `pypdf==7.1.1` and `python-docx==1.2.0` in `requirements.txt`; pinned `pytest==9.2.0` in `requirements-dev.txt`.
  - Created test suite in `tests/test_loaders.py` covering all 6 sample documents, page counts, fact verification, DOCX headings, Urdu preservation, error handling, and bytes inputs.
  - Created diagnostic inspection utility in `scripts/inspect_loaders.py`.
- **Library Choice & Rationale**:
  - Selected `pypdf` (v7.1.1) and `python-docx` (v1.2.0): pure-Python, actively maintained, zero C/system runtime dependencies, enabling lightweight, reliable builds in Hugging Face Docker environments.
- **Test Results**:
  - `pytest`: 8/8 tests passed in 0.84s.
  - `scripts/inspect_loaders.py`: All 6 demo documents loaded into 51 total `DocUnit` instances (0 skipped).
- **Known Limitations**:
  - No OCR support: purely scanned image-based PDFs without an embedded text layer cannot be parsed and will raise a friendly error indicating OCR is not supported.
  - Urdu text extraction from PDFs depends on whether the generating engine embedded proper Unicode cmap/fonts (standard text files and well-encoded PDFs extract reliably).
- **Files Touched**:
  - `.gitignore`
  - `requirements.txt`
  - `requirements-dev.txt`
  - `src/config.py`
  - `src/loaders.py`
  - `scripts/inspect_loaders.py`
  - `tests/test_loaders.py`
  - `docs/PROGRESS.md`
- **Decisions Made**:
  - Structured `DocUnit` with optional `page` (for PDFs) and `section` (for DOCX headings / TXT Q&As) so citation formatting adapts naturally per document format.
  - Used `iter_inner_content()` in `python-docx` to ensure tables and paragraphs maintain their natural inter-document reading order within their respective sections.
