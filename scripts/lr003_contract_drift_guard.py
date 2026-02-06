#!/usr/bin/env python3
"""
LR-003 Contract Drift Guard

Protects critical contract files from unauthorized drift using SHA256 fingerprints.
CI-enforced fail-closed gate for contract governance.

Protected Files:
- services/risk/reason_codes.py (8 RC constants)
- tests/contract/test_decision_contract.py (16 contract tests)
- docs/contracts/market_data.schema.json (Market Data Contract v1.0)
- docs/contracts/signal.schema.json (Trading Signal Contract v1.0)

Usage:
  Generate fingerprint:  python scripts/lr003_contract_drift_guard.py --generate
  Check drift:           python scripts/lr003_contract_drift_guard.py --check

Exit Codes:
  0: Success (no drift or fingerprint generated)
  1: Drift detected or error
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


# Protected files (hardcoded scope)
PROTECTED_FILES = [
    "docs/contracts/market_data.schema.json",
    "docs/contracts/signal.schema.json",
    "services/risk/reason_codes.py",
    "tests/contract/test_decision_contract.py",
]

# Fingerprint file location
FINGERPRINT_PATH = "docs/live-readiness/LR-003-FINGERPRINT.json"


class FileFingerprint(TypedDict):
    """Per-file fingerprint entry."""
    path: str
    sha256: str


class Fingerprint(TypedDict):
    """Complete fingerprint structure."""
    version: str
    generated_at: str
    protected_files: list[FileFingerprint]
    combined_sha256: str


def compute_sha256(file_path: Path) -> str:
    """
    Compute SHA256 hash of file contents.

    Uses binary read with 64KB chunks for cross-platform consistency.

    Args:
        file_path: Path to file

    Returns:
        Hexadecimal SHA256 digest
    """
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def generate_fingerprint(repo_root: Path, output_path: Path) -> None:
    """
    Generate fingerprint file for protected contract files.

    Creates JSON file with per-file SHA256 hashes and combined hash.
    Files are sorted alphabetically for deterministic output.

    Args:
        repo_root: Repository root directory
        output_path: Path to write fingerprint JSON
    """
    print("Generating contract fingerprint...")
    print(f"Protected files: {len(PROTECTED_FILES)}")
    print()

    # Compute per-file hashes (sorted)
    file_fingerprints: list[FileFingerprint] = []
    all_hashes: list[str] = []

    for rel_path in sorted(PROTECTED_FILES):
        file_path = repo_root / rel_path

        if not file_path.exists():
            print(f"ERROR: Protected file not found: {rel_path}", file=sys.stderr)
            sys.exit(1)

        sha256 = compute_sha256(file_path)
        file_fingerprints.append({"path": rel_path, "sha256": sha256})
        all_hashes.append(sha256)

        print(f"[OK] {rel_path}")
        print(f"  SHA256: {sha256[:12]}...")

    # Compute combined hash (concatenate all individual hashes)
    combined_input = "".join(all_hashes)
    combined_sha256 = hashlib.sha256(combined_input.encode("utf-8")).hexdigest()

    # Create fingerprint structure
    fingerprint: Fingerprint = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protected_files": file_fingerprints,
        "combined_sha256": combined_sha256,
    }

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(fingerprint, indent=2) + "\n", encoding="utf-8")

    print()
    print("[OK] Fingerprint generated successfully")
    print(f"  Combined SHA256: {combined_sha256[:12]}...")
    print(f"  Output: {output_path.relative_to(repo_root)}")


def check_drift(repo_root: Path, fingerprint_path: Path) -> bool:
    """
    Check for drift in protected files against fingerprint.

    Computes current hashes and compares with stored fingerprint.
    Returns True if no drift, False if drift detected.

    Args:
        repo_root: Repository root directory
        fingerprint_path: Path to fingerprint JSON file

    Returns:
        True if no drift, False if drift detected
    """
    print("Checking contract fingerprints...")
    print()

    # Load fingerprint
    if not fingerprint_path.exists():
        print(f"ERROR: Fingerprint file not found: {fingerprint_path}", file=sys.stderr)
        print("Run: python scripts/lr003_contract_drift_guard.py --generate", file=sys.stderr)
        return False

    try:
        fingerprint_data = json.loads(fingerprint_path.read_text(encoding="utf-8"))
        expected_fingerprint: Fingerprint = fingerprint_data
    except (json.JSONDecodeError, KeyError) as e:
        print(f"ERROR: Invalid fingerprint file: {e}", file=sys.stderr)
        return False

    # Build expected hashes lookup
    expected_hashes: dict[str, str] = {
        entry["path"]: entry["sha256"]
        for entry in expected_fingerprint["protected_files"]
    }

    # Compute current hashes
    drift_detected = False
    current_hashes: list[str] = []

    for rel_path in sorted(PROTECTED_FILES):
        file_path = repo_root / rel_path

        if not file_path.exists():
            print(f"[FAIL] {rel_path}")
            print(f"  Status: MISSING")
            drift_detected = True
            continue

        current_sha256 = compute_sha256(file_path)
        current_hashes.append(current_sha256)
        expected_sha256 = expected_hashes.get(rel_path)

        if expected_sha256 is None:
            print(f"[FAIL] {rel_path}")
            print(f"  Status: NOT IN FINGERPRINT")
            drift_detected = True
        elif current_sha256 != expected_sha256:
            print(f"[FAIL] {rel_path}")
            print(f"  Expected: {expected_sha256[:12]}...")
            print(f"  Actual:   {current_sha256[:12]}...")
            print(f"  Status:   MODIFIED")
            drift_detected = True
        else:
            print(f"[OK] {rel_path}")

    # Check combined hash
    combined_input = "".join(current_hashes)
    current_combined = hashlib.sha256(combined_input.encode("utf-8")).hexdigest()
    expected_combined = expected_fingerprint["combined_sha256"]

    if current_combined != expected_combined:
        print()
        print("[FAIL] Combined fingerprint mismatch")
        print(f"  Expected: {expected_combined[:12]}...")
        print(f"  Actual:   {current_combined[:12]}...")
        drift_detected = True
    else:
        print()
        print("[OK] Combined fingerprint matches")

    print()

    if drift_detected:
        print("=" * 50)
        print("=== CONTRACT DRIFT DETECTED ===")
        print("=" * 50)
        print()
        print("Protected contract files have been modified without")
        print("updating the fingerprint file.")
        print()
        print("ACTION REQUIRED:")
        print("1. Review changes in protected files")
        print("2. If changes are intentional:")
        print("   python scripts/lr003_contract_drift_guard.py --generate")
        print("3. Commit updated LR-003-FINGERPRINT.json")
        print("4. Re-push to trigger CI")
        print()
        print("Protected files are under contract governance.")
        print("Unauthorized changes are blocked by CI.")
        print("=" * 50)
        return False
    else:
        print("[OK] All protected files match fingerprint")
        return True


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="LR-003 Contract Drift Guard - Protect critical contract files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate/update fingerprint file",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift (default)",
    )
    parser.add_argument(
        "--fingerprint-path",
        type=Path,
        default=FINGERPRINT_PATH,
        help=f"Path to fingerprint file (default: {FINGERPRINT_PATH})",
    )

    args = parser.parse_args()

    # Default to --check if neither specified
    if not args.generate and not args.check:
        args.check = True

    # Find repository root (directory containing .git)
    repo_root = Path.cwd()
    while not (repo_root / ".git").exists():
        if repo_root.parent == repo_root:
            print("ERROR: Not in a git repository", file=sys.stderr)
            sys.exit(1)
        repo_root = repo_root.parent

    fingerprint_path = repo_root / args.fingerprint_path

    if args.generate:
        generate_fingerprint(repo_root, fingerprint_path)
        sys.exit(0)
    elif args.check:
        if check_drift(repo_root, fingerprint_path):
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
