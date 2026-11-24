"""Live health probe check for deployed DocMind Streamlit instance.

Tests the Streamlit health endpoint (/_stcore/health).
Expects HTTP 200 with response body 'ok'.
Performs exactly 0 Gemini API calls.
"""

import argparse
import sys
import time
import urllib.request
import urllib.error


def check_live(base_url: str) -> bool:
    clean_url = base_url.rstrip("/")
    health_url = f"{clean_url}/_stcore/health"

    print("=" * 70)
    print(" DOCMIND LIVE HEALTH PROBE")
    print("=" * 70)
    print(f"Target Health URL: {health_url}")

    req = urllib.request.Request(
        health_url,
        headers={"User-Agent": "DocMind-HealthProbe/1.0"},
    )

    t_start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            duration_ms = (time.perf_counter() - t_start) * 1000.0
            status_code = resp.status
            body = resp.read().decode("utf-8").strip()

            print(f"HTTP Status Code : {status_code}")
            print(f"Response Time    : {duration_ms:.1f} ms")
            print(f"Response Body    : '{body}'")

            if status_code == 200 and body.lower() == "ok":
                print("\nPROBE RESULT: HEALTHY (Streamlit server is live and responsive)")
                print("=" * 70)
                return True
            else:
                print(f"\nPROBE RESULT: UNHEALTHY (Expected 'ok', received '{body}')")
                print("=" * 70)
                return False

    except urllib.error.HTTPError as exc:
        duration_ms = (time.perf_counter() - t_start) * 1000.0
        print(f"HTTP Error       : {exc.code} {exc.reason}")
        print(f"Response Time    : {duration_ms:.1f} ms")
        print("\nPROBE RESULT: FAILED")
        print("=" * 70)
        return False
    except urllib.error.URLError as exc:
        duration_ms = (time.perf_counter() - t_start) * 1000.0
        print(f"Connection Error : {exc.reason}")
        print(f"Response Time    : {duration_ms:.1f} ms")
        print("\nPROBE RESULT: FAILED (Cannot connect to host)")
        print("=" * 70)
        return False
    except Exception as exc:
        print(f"Unexpected Error : {exc}")
        print("\nPROBE RESULT: FAILED")
        print("=" * 70)
        return False


def main():
    parser = argparse.ArgumentParser(description="Check health of a live DocMind Streamlit instance.")
    parser.add_argument("--url", type=str, required=True, help="Base URL of the running DocMind instance (e.g. http://localhost:8501).")
    args = parser.parse_args()

    success = check_live(args.url)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
