# Deployment Guide: Docker & Hugging Face Spaces

This guide explains how to package and deploy **DocMind** as a standalone Docker container to **Hugging Face Spaces** (or any OCI-compliant container platform).

---

## 1. Architecture & Container Specifications

DocMind runs as a containerized Streamlit web application with strict public demo guardrails and zero-API cold start capabilities.

| Parameter | Specification | Purpose |
| :--- | :--- | :--- |
| **Base Image** | `python:3.13-slim` | Lean, production-ready runtime environment. |
| **User ID** | UID `1000` (`user`) | Hugging Face Spaces non-root user security standard. |
| **Working Directory** | `/home/user/app` | Contained application source tree. |
| **Writable Storage** | `/home/user/data`, `/home/user/chroma_db` | User-owned paths for SQLite databases and vector collections. |
| **Port** | `7860` | Default Hugging Face Spaces ingress port. |
| **Streamlit Iframe Flags** | `--server.enableCORS false`<br>`--server.enableXsrfProtection false` | Avoids cross-origin blocking inside Hugging Face iframes. |
| **Startup Mode** | `DEMO_MODE=true` | Protects firm data and enforces daily quota ceilings. |

---

## 2. Prerequisites & Environment Secrets

### A. Hugging Face Access Token
Generate a write-enabled User Access Token in your Hugging Face account settings (`Settings -> Access Tokens`).
Export the token locally in your shell:
```bash
export HF_TOKEN="hf_your_write_token_here"
```
*(On Windows PowerShell)*:
```powershell
$env:HF_TOKEN = "hf_your_write_token_here"
```

> [!IMPORTANT]
> Never hardcode or pass tokens via CLI flags. `scripts/deploy_hf.py` strictly reads the token from the `HF_TOKEN` environment variable.

### B. Hugging Face Space Runtime Secrets
In your Space settings on Hugging Face (`Settings -> Variables and secrets`):
1. **`GEMINI_API_KEY`** (Secret): Your Google AI Studio Gemini API key.
2. **`DEMO_MODE`** (Variable): Set to `true` (already default in `Dockerfile`).

> [!NOTE]
> Hugging Face secrets are injected as environment variables at **runtime only**. They are not accessible during `docker build`, ensuring build logs remain clean.

---

## 3. Deployment Procedure

DocMind includes an automated deployment tool (`scripts/deploy_hf.py`) that manages pre-flight checks, secret scanning, `.dockerignore` pruning, and repo syncing.

### Step 1: Pre-Flight Dry Run & Secret Scan
Before uploading, run a dry run to inspect the staged payload and verify that no secrets or local environment files are included:
```bash
python scripts/deploy_hf.py --dry-run
```
The script will:
- Check that `.env` and sensitive files are excluded.
- Run regex scanners for Gemini keys (`AIza...`), HF tokens (`hf_...`), and key assignments.
- Calculate total payload size (typically ~2.1 MB).
- Prune evaluation outputs (`eval/results/`) and dev-only scripts.
- Print the generated Space `README.md` YAML metadata header.

### Step 2: Deploy to Space
Deploy the repository to your Hugging Face Space:
```bash
python scripts/deploy_hf.py --space <username>/<space-name> --message "Deploy DocMind"
```
If the Space does not yet exist, `deploy_hf.py` automatically initializes it as a public Docker Space (`sdk: docker`, `app_port: 7860`).

---

## 4. Live Health Check

Once the Space builds and enters the `Running` state, verify its health using the zero-API health probe:
```bash
python scripts/check_live.py --url https://<username>-<space-name>.hf.space
```
The probe tests `/_stcore/health` and confirms HTTP 200 with response body `'ok'`.

---

## 5. Public Demo Hardening & Guardrails

When deployed with `DEMO_MODE=true`, the application activates several protective layers:

1. **Zero-API Shared Index (`data/demo_index/`)**:
   - The 8 sample law firm documents (97 chunks) are loaded into Chroma at startup with **0 embedding API calls**.
2. **Session-Private In-Memory Storage**:
   - User document uploads remain ephemeral and private to the active browser session.
3. **Multi-Session Insights Isolation**:
   - Telemetry views in Knowledge Insights filter events strictly to synthetic demo data plus the visitor's current session. Other sessions' real queries never leak into cards, charts, gap clusters, or CSV exports.
   - Real events older than 24 hours (`DEMO_REAL_EVENT_RETENTION_HOURS=24`) are automatically purged.
4. **Daily Capacity Ceilings (Pacific Quota Day)**:
   - **Generation Budget**: Capped at 350 requests/day (`DEMO_DAILY_GENERATION_BUDGET=350`). At 85% capacity, a soft notice is displayed; when exhausted, the system returns a polite capacity notice with 0 API calls.
   - **Embed Budget**: Capped at 600 requests/day (`DEMO_DAILY_EMBED_BUDGET=600`).
   - Small-talk and answer cache hits bypass the LLM and consume 0 budget.
