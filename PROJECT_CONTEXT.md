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
- **User Interface**: Clean dark Streamlit UI.

## Tech Stack
- **Language**: Python
- **Frontend / App Framework**: Streamlit
- **LLM / Embeddings**: Gemini API (free tier)
- **Vector Database**: ChromaDB
- **Deployment**: Hugging Face Spaces via Docker SDK

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
├── tests/                  # Unit and integration tests (.gitkeep)
├── docs/
│   └── PROGRESS.md         # Progress tracking log for every development step
├── .env.example            # Environment variables template
├── .gitignore              # Ignored files (secrets, venv, vector stores, caches)
├── PROJECT_CONTEXT.md      # Project overview, guidelines, and rules
├── README.md               # Repository summary
└── requirements.txt        # Project dependencies (pinned in later steps)
```

## Coding Rules
- **Small focused edits only**: No big refactors or full-file rewrites.
- **Type hints & docstrings**: Every function and module must have type hints and concise docstrings.
- **Never hardcode secrets**: Read configuration from `.env` via `src/config.py`.
- **Error and rate-limit handling**: Handle API errors, timeouts, and rate limits gracefully.
- **UI Styling**: Neutral clean dark theme for now; Quxel violet-blue branding comes in a later step.
- **Progress Tracking Rule**: At the end of every step, update `docs/PROGRESS.md` (what was built, files touched, how it was tested, decisions made) and then git commit + push.
