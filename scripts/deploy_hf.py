"""Deploy DocMind to a Hugging Face Docker Space.

Features:
- Authenticates strictly using the HF_TOKEN environment variable.
- Scans all staged files for secrets (API keys, tokens) before upload.
- Respects .dockerignore and excludes tests, local caches, and scratch files.
- Generates Space README.md with standard YAML front matter.
- Supports --dry-run mode for pre-flight verification without uploading.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Regex patterns for secret detection
SECRET_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z_-]{35}"), "Google Gemini API Key (AIza...)"),
    (re.compile(r"hf_[A-Za-z0-9]{30,}"), "Hugging Face User Token (hf_...)"),
    (re.compile(r"GEMINI_API_KEY=\S+"), "GEMINI_API_KEY value assignment"),
]

SPACE_README_TEMPLATE = """---
title: DocMind
emoji: ⚖️
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# DocMind - Law Firm Knowledge Assistant

DocMind is a multi-turn, dual-audience (Client & Staff) legal knowledge assistant built for **Sterling & Rauf Law Associates** (fictional law firm, Lahore, Pakistan).

### Features
- **Client & Staff Role Isolation**: Role-based access control with field-level visibility filtering.
- **Dual Anti-Hallucination Guardrails**: Semantic threshold gating combined with structured LLM verification.
- **Quote-Verified Contract Analysis**: 10-point clause extraction strictly backed by exact quotes from contract text.
- **Client Reply Drafting**: Formats professional, policy-compliant client responses with customizable tone and urgency.
- **Knowledge Insights Dashboard**: Real-time telemetry, gap clustering, and usage analytics.
- **Zero-API Demo Initialization**: Pre-computed portable vector index enabling zero-API cold starts.

*Disclaimer: This is a fictional demonstration application. Documents, fees, policies, and personnel are entirely fictional and do not constitute real legal advice.*
"""


def get_git_tracked_files() -> List[str]:
    """Return list of files tracked by git in the repository."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip().replace("\\", "/") for f in res.stdout.splitlines() if f.strip()]
    except Exception as exc:
        print(f"Error running git ls-files: {exc}")
        # Fallback to local walk
        files = []
        for p in PROJECT_ROOT.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(PROJECT_ROOT)).replace("\\", "/")
                files.append(rel)
        return files


def load_dockerignore_rules() -> List[str]:
    """Read .dockerignore rules."""
    di_path = PROJECT_ROOT / ".dockerignore"
    if not di_path.exists():
        return []
    rules = []
    for line in di_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            rules.append(line)
    return rules


def is_ignored(rel_path: str, rules: List[str]) -> bool:
    """Check if rel_path matches any dockerignore or deployment exclusion rule."""
    # Strict deployment exclusions
    if rel_path.startswith(".env") or "/.env" in rel_path:
        return True
    if rel_path.startswith(".git") or "/.git" in rel_path:
        return True
    if rel_path.startswith(".venv") or "/.venv" in rel_path:
        return True
    if rel_path.startswith("tests/") or rel_path == "tests":
        return True
    if rel_path.startswith("scratch/") or rel_path == "scratch":
        return True
    if rel_path.startswith("docs/screenshots/") or rel_path.startswith("docs/ui-reference/"):
        return True
    if rel_path.endswith(".pyc") or "__pycache__" in rel_path:
        return True
    if rel_path.startswith("chroma_db/") or rel_path == "chroma_db":
        return True
    if rel_path.startswith("data/analytics.db") or rel_path.startswith("data/demo_limits.db"):
        return True

    # Rule checks
    for rule in rules:
        clean_rule = rule.rstrip("/")
        if rel_path == clean_rule or rel_path.startswith(clean_rule + "/"):
            return True
        if clean_rule.startswith("*.") and rel_path.endswith(clean_rule[1:]):
            return True
    return False


def scan_file_for_secrets(rel_path: str) -> List[Tuple[str, str]]:
    """Scan a staged file for prohibited secrets. Returns [(pattern_name, line_snippet)]."""
    p = Path(rel_path)
    abs_path = p if p.is_absolute() else (PROJECT_ROOT / rel_path)
    findings = []
    try:
        content = abs_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    for pattern, desc in SECRET_PATTERNS:
        match = pattern.search(content)
        if match:
            matched_text = match.group(0)
            masked = matched_text[:6] + "..." + matched_text[-4:] if len(matched_text) > 10 else "***"
            findings.append((desc, masked))
    return findings


def deploy_hf(space_id: str, dry_run: bool = False, message: str = "Deploy DocMind to Hugging Face Spaces"):
    print("=" * 80)
    print(" DOCMIND HUGGING FACE SPACES DEPLOYMENT")
    print("=" * 80)
    print(f"Target Space: {space_id}")
    print(f"Dry Run Mode: {dry_run}")

    # 1. Verify token
    token = os.getenv("HF_TOKEN", "").strip()
    if not dry_run and not token:
        print("\nERROR: HF_TOKEN environment variable is missing or empty.")
        print("Please set the HF_TOKEN environment variable with a write-enabled Hugging Face access token.")
        sys.exit(1)

    # 2. Collect files to stage
    tracked = get_git_tracked_files()
    ignore_rules = load_dockerignore_rules()

    staged_files: List[str] = []
    for f in tracked:
        if not is_ignored(f, ignore_rules):
            staged_files.append(f)

    # Ensure Dockerfile and requirements.txt are included
    if "Dockerfile" not in staged_files and (PROJECT_ROOT / "Dockerfile").exists():
        staged_files.append("Dockerfile")
    if "requirements.txt" not in staged_files and (PROJECT_ROOT / "requirements.txt").exists():
        staged_files.append("requirements.txt")

    staged_files = sorted(list(set(staged_files)))

    # Assert no .env files are staged
    for f in staged_files:
        if f.startswith(".env") or f == ".env":
            print(f"\nCRITICAL SECURITY ERROR: Prohibited env file detected in staged files: {f}")
            sys.exit(1)

    print(f"\n[1] File Staging: {len(staged_files)} files selected for upload.")

    # 3. Secret Scanner
    print("[2] Running Pre-flight Secret Scanner across staged files...")
    secret_violations = {}
    for f in staged_files:
        violations = scan_file_for_secrets(f)
        if violations:
            secret_violations[f] = violations

    if secret_violations:
        print("\nCRITICAL SECURITY CHECK FAILED: Potential secrets detected in staged files!")
        for f, viols in secret_violations.items():
            for desc, masked in viols:
                print(f"  - {f}: {desc} ({masked})")
        print("\nDeployment aborted to prevent secret leakage.")
        sys.exit(1)
    else:
        print("    ✓ Clean: No API keys, credentials, or personal tokens detected.")

    # 4. Calculate total size
    total_bytes = 0
    file_details = []
    for f in staged_files:
        p = PROJECT_ROOT / f
        sz = p.stat().st_size if p.exists() else 0
        total_bytes += sz
        file_details.append((f, sz))

    total_mb = total_bytes / (1024 * 1024)
    print(f"\n[3] Total Payload Size: {total_mb:.2f} MB across {len(staged_files)} files.")

    # 5. Dry-run summary
    if dry_run:
        print("\n[4] DRY-RUN FILE MANIFEST:")
        for f, sz in file_details:
            print(f"    - {f:<45} ({sz / 1024:.1f} KB)")

        print("\n--- GENERATED SPACE README.MD YAML FRONTMATTER ---")
        lines = SPACE_README_TEMPLATE.strip().split("\n")
        header = "\n".join(lines[:9])
        print(header)
        print("--------------------------------------------------\n")
        print("Dry run completed successfully. No changes made to remote Space.")
        return

    # 6. Real upload via huggingface_hub
    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("\nERROR: huggingface_hub is not installed in the environment.")
        print("Please install it via: pip install huggingface_hub")
        sys.exit(1)

    api = HfApi(token=token)
    print("\n[4] Connecting to Hugging Face API...")
    try:
        space_info = api.space_info(space_id)
        print(f"    - Space found: {space_info.id} (SDK: {space_info.sdk or 'unknown'})")
    except Exception:
        print(f"    - Space '{space_id}' does not exist or is private. Creating new Docker Space...")
        api.create_repo(
            repo_id=space_id,
            repo_type="space",
            space_sdk="docker",
            private=False,
            exist_ok=True,
        )

    # Prepare temporary folder for upload
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        for f in staged_files:
            src_p = PROJECT_ROOT / f
            dst_p = tmp_root / f
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_p, dst_p)

        # Write generated Space README.md
        readme_dst = tmp_root / "README.md"
        readme_dst.write_text(SPACE_README_TEMPLATE, encoding="utf-8")

        print(f"\n[5] Uploading {len(staged_files) + 1} files to Space '{space_id}'...")
        api.upload_folder(
            folder_path=str(tmp_root),
            repo_id=space_id,
            repo_type="space",
            commit_message=message,
        )

    print(f"\nSUCCESS: Deployed to Hugging Face Space: https://huggingface.co/spaces/{space_id}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Deploy DocMind to Hugging Face Spaces.")
    parser.add_argument("--space", type=str, default="user/docmind", help="Target Hugging Face Space (e.g. username/docmind).")
    parser.add_argument("--dry-run", action="store_true", help="Perform pre-flight file staging and secret scan without uploading.")
    parser.add_argument("--message", type=str, default="feat: deploy DocMind to Hugging Face Space", help="Commit message.")
    args = parser.parse_args()

    deploy_hf(space_id=args.space, dry_run=args.dry_run, message=args.message)


if __name__ == "__main__":
    main()
