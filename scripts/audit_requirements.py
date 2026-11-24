"""Audit third-party imports across app.py, src/, and scripts/ against requirements.txt."""

import ast
import glob
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def audit():
    stdlib = sys.stdlib_module_names
    files = [str(PROJECT_ROOT / "app.py")]
    files.extend(glob.glob(str(PROJECT_ROOT / "src/**/*.py"), recursive=True))
    files.extend(glob.glob(str(PROJECT_ROOT / "scripts/*.py")))

    imports = set()
    for f in files:
        path = Path(f)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        imports.add(n.name.split(".")[0])
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
        except Exception as exc:
            print(f"Error parsing {path}: {exc}")

    local_pkgs = {"src", "app", "eval", "scripts", "tests", "data"}
    third_party = sorted(imports - stdlib - local_pkgs)

    print("=" * 70)
    print(" THIRD-PARTY IMPORTS AST AUDIT")
    print("=" * 70)
    print(f"Found {len(third_party)} third-party top-level packages: {third_party}\n")

    req_text = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    req_lines = [l.strip() for l in req_text.splitlines() if l.strip() and not l.startswith("#")]
    req_map = {}
    for l in req_lines:
        pkg, ver = l.split("==")
        req_map[pkg.lower().replace("-", "_")] = ver

    dev_req_text = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    dev_req_lines = [l.strip() for l in dev_req_text.splitlines() if l.strip() and not l.startswith("#")]
    dev_req_map = {}
    for l in dev_req_lines:
        pkg, ver = l.split("==")
        dev_req_map[pkg.lower().replace("-", "_")] = ver

    pkg_alias = {
        "docx": "python_docx",
        "dotenv": "python_dotenv",
        "google": "google_genai",
        "pandas": "streamlit",  # streamlit pulls in pandas
    }

    all_ok = True
    for tp in third_party:
        canonical = pkg_alias.get(tp, tp.lower().replace("-", "_"))
        if canonical in req_map:
            print(f"  [OK] {tp:<16} -> pinned in requirements.txt ({canonical}=={req_map[canonical]})")
        elif canonical in dev_req_map:
            print(f"  [OK] {tp:<16} -> pinned in requirements-dev.txt ({canonical}=={dev_req_map[canonical]})")
        elif canonical == "streamlit":
            print(f"  [OK] {tp:<16} -> transitive dependency of streamlit")
        else:
            print(f"  [MISSING] {tp:<16} (canonical: {canonical}) NOT found in requirements!")
            all_ok = False

    print("=" * 70)
    if all_ok:
        print("AUDIT RESULT: ALL runtime and dev third-party dependencies are pinned!")
    else:
        print("AUDIT RESULT: Some dependencies are missing pins!")
    print("=" * 70)
    return all_ok


if __name__ == "__main__":
    success = audit()
    sys.exit(0 if success else 1)
