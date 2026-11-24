"""Verify headless Streamlit app startup in DEMO_MODE for Step 17 E4."""

import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def verify_startup():
    print("=" * 70)
    print(" STEP 17 E4: HEADLESS STREAMLIT STARTUP (DEMO_MODE=true)")
    print("=" * 70)

    env = os.environ.copy()
    env["DEMO_MODE"] = "true"
    env["STREAMLIT_SERVER_PORT"] = "8599"
    env["STREAMLIT_SERVER_HEADLESS"] = "true"
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    cmd = [
        sys.executable,
        "-m", "streamlit", "run", "app.py",
        "--server.port", "8599",
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
    ]

    print("Launching Streamlit app on port 8599...")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    time.sleep(3.0)

    # Health probe check via scripts/check_live.py
    from scripts.check_live import check_live
    health_ok = False
    for attempt in range(1, 6):
        print(f"Health check attempt {attempt}/5...")
        if check_live("http://localhost:8599"):
            health_ok = True
            break
        time.sleep(2.0)

    print(f"\nApp remained running for 10 seconds...")
    time.sleep(5.0)

    # Terminate process cleanly
    proc.terminate()
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        proc.kill()

    print(f"Process terminated cleanly. Health check result: {health_ok}")
    print("=" * 70)
    assert health_ok, "Streamlit health check must succeed!"


if __name__ == "__main__":
    verify_startup()
