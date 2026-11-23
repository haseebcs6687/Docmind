"""Inspection script to load sample documents and verify unit parsing and citation metadata."""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.loaders import load_directory

SAMPLE_DIR = PROJECT_ROOT / "data" / "sample_docs"


def main() -> None:
    print(f"Loading sample documents from: {SAMPLE_DIR}\n")
    units, report = load_directory(SAMPLE_DIR)

    print("=" * 105)
    print(f"{'Filename':<40} | {'Type':<6} | {'Units':<6} | {'First Citation Label':<35} | {'Total Chars':<11}")
    print("-" * 105)

    # Group units by file
    files = report["loaded_files"]
    for fname in files:
        file_units = [u for u in units if u.source == fname]
        file_type = file_units[0].file_type if file_units else "N/A"
        count = len(file_units)
        first_citation = file_units[0].citation_label() if file_units else "N/A"
        total_chars = sum(len(u.text) for u in file_units)

        # Truncate citation if too long for display
        if len(first_citation) > 35:
            first_citation = first_citation[:32] + "..."

        print(f"{fname:<40} | {file_type:<6} | {count:<6} | {first_citation:<35} | {total_chars:<11}")

    print("=" * 105)
    print(f"\nTotal Loaded Files: {len(report['loaded_files'])} | Total Units: {report['total_units']}")

    if report["skipped_files"]:
        print("\nSkipped Files:")
        for sf, reason in report["skipped_files"].items():
            print(f"  - {sf}: {reason}")
    else:
        print("Skipped Files: None")


if __name__ == "__main__":
    main()
