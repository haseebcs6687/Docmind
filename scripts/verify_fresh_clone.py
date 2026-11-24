"""Fresh-clone simulation script for Step 17 E1."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load parent config before cloning
from src.config import get_gemini_api_key
PARENT_API_KEY = get_gemini_api_key()

def run_simulation():
    print("=" * 80)
    print(" STEP 17 E1: FRESH-CLONE SIMULATION & ZERO-API STARTUP PROBE")
    print("=" * 80)

    # Step 1: Create temp directory and git clone
    temp_dir = Path(tempfile.mkdtemp(prefix="docmind_clone_"))
    print(f"[1] Cloning current git repository to isolated temp directory: {temp_dir}")
    try:
        subprocess.run(
            ["git", "clone", str(PROJECT_ROOT), str(temp_dir)],
            check=True,
            capture_output=True,
            text=True,
        )

        # Copy working tree modifications (excluding .env*, .git, .venv)
        from scripts.deploy_hf import get_git_tracked_files
        for f in get_git_tracked_files():
            src_f = PROJECT_ROOT / f
            dst_f = temp_dir / f
            if src_f.exists() and not f.startswith(".env"):
                dst_f.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_f, dst_f)

        # Step 2: Confirm .env does NOT exist in clone
        env_file = temp_dir / ".env"
        assert not env_file.exists(), "SECURITY ERROR: .env file was cloned!"
        print("    ✓ Clean: No .env file exists in the fresh clone.")

        # Step 3: Run startup probe with DEMO_MODE=true and NO .env
        print("\n[2] Running Startup Probe without .env (DEMO_MODE=true)...")

        # Set up isolated sys.path and environment
        orig_sys_path = sys.path.copy()
        sys.path.insert(0, str(temp_dir))

        env_without_key = os.environ.copy()
        env_without_key.pop("GEMINI_API_KEY", None)
        env_without_key["DEMO_MODE"] = "true"
        env_without_key["CHROMA_DIR"] = str(temp_dir / "chroma_db")
        env_without_key["ANALYTICS_DB_PATH"] = str(temp_dir / "data" / "analytics.db")
        env_without_key["DEMO_LIMITS_DB_PATH"] = str(temp_dir / "data" / "demo_limits.db")

        # Run startup check script in subprocess with clean environment
        probe_code = """
import os, sys
from pathlib import Path
sys.path.insert(0, os.getcwd())

from src.config import DEMO_MODE, get_gemini_api_key
from src.vectorstore import VectorStore
from src.shared_index import ensure_shared_index
from src.analytics import AnalyticsStore, ensure_demo_activity

assert DEMO_MODE is True, "DEMO_MODE must be true"

# 1. Zero-API Shared Index Initialization
store = VectorStore(read_only=True)
seeded_idx = ensure_shared_index(store)
count = store.count()
sources = store.list_sources()
print(f"PROBE_INDEX: chunks={count}, docs={len(sources)}, seeded={seeded_idx}")
assert count == 97, f"Expected 97 chunks, got {count}"
assert len(sources) == 8, f"Expected 8 docs, got {len(sources)}"

# 2. Demo Activity Seeding
analytics = AnalyticsStore()
seeded_act = ensure_demo_activity(analytics)
counts = analytics.count()
print(f"PROBE_ANALYTICS: synthetic={counts['synthetic']}, live={counts['live']}")
assert counts['synthetic'] > 50, "Expected synthetic demo activity seeded"

# 3. Missing Key Handling
try:
    get_gemini_api_key()
    print("PROBE_KEY: UNEXPECTED_KEY_FOUND")
except ValueError as e:
    print(f"PROBE_KEY: CLEAN_ERROR - {e}")
"""
        probe_res = subprocess.run(
            [sys.executable, "-c", probe_code],
            cwd=str(temp_dir),
            env=env_without_key,
            capture_output=True,
            text=True,
        )
        print(probe_res.stdout)
        if probe_res.returncode != 0:
            print("STDERR:\n", probe_res.stderr)
            raise RuntimeError("Startup probe failed!")

        assert "PROBE_INDEX: chunks=97, docs=8" in probe_res.stdout
        assert "PROBE_KEY: CLEAN_ERROR" in probe_res.stdout
        print("    ✓ Startup probe successful: 8 docs / 97 chunks loaded with 0 API calls.")

        # Step 4: Run 1 live staff question with API key set
        api_key = PARENT_API_KEY

        print("\n[3] Running 1 Live Staff Question with Gemini API Key...")
        env_with_key = env_without_key.copy()
        env_with_key["GEMINI_API_KEY"] = api_key

        live_q_code = """
import os, sys
sys.path.insert(0, os.getcwd())

from src.vectorstore import VectorStore
from src.session_store import CompositeStore, get_session_store
from src.rag import ChatSession

shared_store = VectorStore(read_only=True)
session_store = get_session_store("fresh_clone_session")
composite = CompositeStore(shared=shared_store, session=session_store)

chat = ChatSession(store=composite, access_mode="staff", session_id="fresh_clone_session")
question = "What is the initial consultation fee and when is it waived?"
resp = chat.ask(question)

print("--- LIVE RESPONSE ---")
print("Question :", question)
print("Answer   :", resp.answer)
print("Found    :", resp.found)
print("Sources  :", [s.get('citation') for s in resp.sources])
print(f"Latency  : {resp.latency_ms:.1f} ms | Model: {resp.model_used}")
print("---------------------")

assert resp.found is True, "Question must be found"
assert "5,000" in resp.answer, "Fee PKR 5,000 must be in answer"
assert "7 days" in resp.answer or "seven days" in resp.answer.lower(), "Waiver condition (7 days) must be in answer"
"""
        live_res = subprocess.run(
            [sys.executable, "-c", live_q_code],
            cwd=str(temp_dir),
            env=env_with_key,
            capture_output=True,
            text=True,
        )
        print(live_res.stdout)
        if live_res.returncode != 0:
            print("STDERR:\n", live_res.stderr)
            raise RuntimeError("Live question failed!")

        print("    ✓ Live staff question answered accurately with citations!")
        print("\n[4] Fresh-clone simulation completed successfully!")
        print("=" * 80)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_simulation()
