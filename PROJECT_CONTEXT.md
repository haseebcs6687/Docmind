# DocMind - Project Context

## Project Goal and Use-Case
DocMind is a Retrieval-Augmented Generation (RAG) "Chat With Your Documents" knowledge agent.
- **Demo Use-Case**: Fictional law firm (dummy data only).
- **Users**: Law firm staff and clients.
- **Workflow**: Users upload documents (engagement letters, fee structures, policies, SOPs, FAQs) and ask questions.

## Core Features
- **Source Citation**: Answers must cite sources explicitly (file name + page number).
- **Anti-Hallucination Guardrails**: If the answer is not present in the ingested documents, the application must clearly state so without fabricating facts.
- **Multilingual Support**: Supports Urdu, Roman Urdu, and English. The agent must respond in the user's language.
- **Follow-up Handling**: Maintains conversational context to answer sequential follow-up questions accurately.
- **User Interface**: Clean modern Streamlit UI (dark sidebar + light grey workspace).

## Tech Stack
- **Language**: Python
- **Frontend / App Framework**: Streamlit
- **LLM / Embeddings**: Gemini API (free tier) via official `google-genai` SDK
- **Vector Database**: ChromaDB
- **Deployment**: Hugging Face Spaces via Docker SDK

## Model Decisions & Limits
- **Generation**: `gemini-3.5-flash-lite` (verified working; `gemini-2.5-flash` returns 404 "no longer available to new users"). `gemini-3.8-flash` is a candidate to compare in the evaluation step.
- **Embeddings**: `gemini-embedding-001` (3072-dim, verified working).
- **Approx Free-Tier Limits (AI Studio)**:
  - Generation: ~15 RPM / ~250K TPM / ~500 RPD.
  - Embedding: ~100 RPM / ~30K TPM / ~1000 RPD.
  - RPD resets at midnight Pacific.
- **Design Rules**:
  - Embed in batches with throttling + retry/backoff on HTTP 429.
  - Persist the vector store to disk so documents are never re-embedded unnecessarily.
  - Show friendly messages on rate-limit errors.
  - Model names always come from `.env` via `src/config.py`.
- **Note on API Evolution**: The API error suggested the newer "Interactions API"; we currently use `generate_content` which works. Before writing the RAG code in Step 6, check the official docs (`ai.google.dev`) for the currently recommended approach and tell me what you chose and why.

## UI Design & Direction
- **Sidebar**: Dark near-black sidebar with navigation items and active pill highlight. Planned pages: Chat, Documents, Sources, Evaluation, Settings.
- **Main Workspace**: Light grey main area with white rounded cards with soft borders.
- **Visual Elements**: Soft pastel tinted stat cards, indigo/violet primary accent (approx #4F46E5), top bar with search, clean modern sans font, small status chips.
- **Branding**: Quxel violet-blue branding comes in a later step.

## Repository Structure
```
Docmind/
├── app.py                  # Main Streamlit application entry point
├── src/
│   ├── __init__.py         # Package initializer
│   ├── config.py           # Configuration and environment settings
│   ├── loaders.py          # Document parsers and loaders
│   ├── chunking.py         # Text chunking and splitting strategies
│   ├── vectorstore.py      # ChromaDB setup and index management
│   └── rag.py              # RAG orchestration and retrieval chain
├── data/
│   └── sample_docs/        # Sample dummy legal documents (.gitkeep)
├── eval/                   # Evaluation scripts and test queries (.gitkeep)
├── scripts/                # Helper and diagnostic scripts (e.g., check_gemini.py)
├── tests/                  # Unit and integration tests (.gitkeep)
├── docs/
│   ├── PROGRESS.md         # Progress tracking log for every development step
│   └── ui-reference/       # UI screenshots (gitignored)
├── .env                    # Local environment variables (gitignored)
├── .env.example            # Environment variables template
├── .gitignore              # Ignored files (secrets, venv, vector stores, caches, ui-ref)
├── PROJECT_CONTEXT.md      # Project overview, guidelines, and rules
├── README.md               # Repository summary
└── requirements.txt        # Pinned project dependencies
```

## Coding Rules
- **Small focused edits only**: No big refactors or full-file rewrites.
- **Type hints & docstrings**: Every function and module must have type hints and concise docstrings.
- **Never hardcode secrets**: Read configuration from `.env` via `src/config.py`. Never log or print keys.
- **Error and rate-limit handling**: Handle API errors, timeouts, and rate limits gracefully.
- **UI Styling**: Follow the UI design direction (dark sidebar, light workspace, indigo/violet accent #4F46E5); Quxel branding comes in a later step.
- **Progress Tracking Rule**: At the end of every step, update `docs/PROGRESS.md` (what was built, files touched, how it was tested, decisions made) and then git commit + push.
