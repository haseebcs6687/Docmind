"""Verify that staff canary strings appear only in staff documents and never in client documents."""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.loaders import load_file

def main():
    sample_dir = Path("data/sample_docs")
    with open(sample_dir / "manifest.json", "r", encoding="utf-8") as f:
        manifest = json.load(f)

    canaries = [
        "Data Protection Officer",
        "AES-256",
        "Tier 1: Frontline",
    ]

    all_passed = True
    for canary in canaries:
        print(f"\n=== Canary: '{canary}' ===")
        found_in_client = []
        found_in_staff = []

        for file_path in sorted(sample_dir.iterdir()):
            if file_path.suffix.lower() not in (".pdf", ".docx", ".txt"):
                continue
            vis = manifest.get(file_path.name, {}).get("visibility", "unknown")
            units = load_file(file_path)
            full_text = " ".join(u.text for u in units)

            if canary.lower() in full_text.lower():
                print(f"  [FOUND] in {file_path.name} (visibility: {vis})")
                if vis == "client":
                    found_in_client.append(file_path.name)
                else:
                    found_in_staff.append(file_path.name)
            else:
                print(f"  [absent] {file_path.name} (visibility: {vis})")

        if found_in_client:
            print(f"  FAILED: Canary '{canary}' was found in client documents: {found_in_client}")
            all_passed = False
        elif not found_in_staff:
            print(f"  FAILED: Canary '{canary}' was NOT found in any staff document!")
            all_passed = False
        else:
            print(f"  SUCCESS: Canary '{canary}' strictly isolated to staff documents: {found_in_staff}")

    print("\nOVERALL CANARY VERIFICATION RESULT:", "PASSED" if all_passed else "FAILED")

if __name__ == "__main__":
    main()
