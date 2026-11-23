# DocMind

A RAG "Chat With Your Documents" knowledge agent for legal workflows with strict source citations and zero hallucination.

DocMind is configured with a fictional law firm demo dataset (**Sterling & Rauf Law Associates**, Lahore, Pakistan). Staff and clients can query legal documents (fee schedules, brochures, SOPs, policies, engagement letters, and FAQs) and receive precise answers citing exact files and pages. If a topic is not in the documents, DocMind clearly states it cannot find the answer rather than hallucinating.

---

## Key Features

- **Strict Source Citations**: Every factual claim is backed by citations to specific document files and page/section numbers.
- **Dual Anti-Hallucination Guardrails**: Retrieval similarity score gating (threshold 0.65) combined with structured JSON schema verification (`found: bool`, `used_sources: list[int]`).
- **Multi-Turn Chat with Query Rewriting**: Follow-up questions referencing previous context ("what about associates?", "is it refundable?") are automatically resolved into standalone search queries.
- **Rule-Based Small-Talk Filter**: Instant canned responses for greetings, thanks, goodbyes, and capabilities with 0 latency and 0 API calls.
- **Incremental & Deterministic Indexing**: Files are fingerprinted with SHA-256 hashes to prevent redundant embeddings.
- **Modern Streamlit UI**: Clean dashboard theme featuring a near-black sidebar (`#0F1117`) with workspace navigation pills and live corpus stats, light grey workspace (`#F5F6F8`), white rounded cards, pastel stat cards, responsive chat interface with starter questions, expandable source previews with relevance percentage chips, and document management with multi-file upload.
- **Privacy & Safety**: Automatic redaction prevents API keys or stack traces from leaking to client UI or application logs.

---

## Tech Stack

- **Python**: 3.13+
- **LLM & Embeddings**: Google Gemini API (`gemini-3.5-flash-lite`, `gemini-embedding-001` via `google-genai==3.6.1`)
- **Vector Store**: ChromaDB (`chromadb==1.5.9`) with cosine similarity
- **Parsers**: `pypdf==7.1.1`, `python-docx==1.2.0`
- **Web UI**: Streamlit (`streamlit==1.67.0`)
- **Testing**: `pytest==9.2.0` with `streamlit.testing.v1.AppTest`

---

## Quickstart

### 1. Clone & Set Up Virtual Environment

```bash
git clone <repo-url>
cd Docmind
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux / macOS
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

*(Optional: install dev dependencies if regenerating sample documents)*:
```bash
pip install -r requirements-dev.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the project root (see `.env.example`):

```ini
GEMINI_API_KEY=your_actual_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash-lite
GEMINI_EMBED_MODEL=gemini-embedding-001
MAX_UPLOAD_MB=20
CHROMA_DIR=chroma_db
CHUNK_SIZE=1000
CHUNK_OVERLAP=150
EMBED_BATCH_SIZE=20
EMBED_BATCH_SLEEP_SECONDS=1.0
TOP_K=5
SCORE_THRESHOLD=0.65
GEN_TEMPERATURE=0.1
GEN_MAX_RETRIES=5
HISTORY_TURNS=4
```

### 4. Build or Inspect the Vector Index

Index the pre-generated sample legal documents into the local ChromaDB store:

```bash
python scripts/build_index.py
```

To re-generate sample documents from scratch:
```bash
python scripts/generate_sample_docs.py
```

### 5. Run the Streamlit Application

```bash
streamlit run app.py
```

Navigate to `http://localhost:8501` in your browser.
- **Chat Page**: Submit questions, use suggested starter buttons, view answers with source citations, relevance percentages, and snippet previews.
- **Documents Page**: View indexed document metrics, load sample documents, upload custom PDF/DOCX/TXT files, or manage/delete sources.

---

## Command-Line Scripts

- **Ask a single question**:
  ```bash
  python scripts/ask.py "What is the initial consultation fee and when is it waived?"
  ```
- **Run multi-turn conversational demo**:
  ```bash
  python scripts/chat_demo.py
  ```
- **Inspect Gemini models & test API key**:
  ```bash
  python scripts/check_gemini.py --list
  python scripts/check_gemini.py --test
  ```

---

## Running Tests

Run the offline pytest test suite (42 tests, 0 real API calls):

```bash
python -m pytest
```

---

## Disclaimer

DocMind contains demo data for the fictional law firm **Sterling & Rauf Law Associates**. It is intended solely for technical demonstration and educational purposes and does not constitute real legal advice.
