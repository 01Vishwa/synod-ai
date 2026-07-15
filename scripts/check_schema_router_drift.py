#!/usr/bin/env python3
"""
scripts/check_schema_router_drift.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CI guard: scan the backend for known ghost field names that previously caused
AttributeError at runtime because a router accessed a Pydantic attribute that
doesn't exist on the request schema.

Background
----------
In July 2026 the router accessed ``req.pinned_chairman_member_id`` while the
canonical field on ``SessionCreateRequest`` is ``chairman_member_id``.
The ghost name was never on the schema, so it only surfaced as a 500 at
runtime, not at import time.

This script acts as a compile-time substitute: it greps `app/` for any of the
known ghost names and fails with a non-zero exit code if any are found, so
the CI pipeline catches the regression immediately rather than in production.

Usage
-----
    python scripts/check_schema_router_drift.py          # pass/fail
    python scripts/check_schema_router_drift.py --quiet  # suppress OK lines

Exit codes
----------
    0  — no ghost names found
    1  — one or more ghost names found (CI should treat this as a build failure)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ── Configuration ─────────────────────────────────────────────────────────────

# Root of the backend source tree (relative to this script's location)
_BACKEND_ROOT = Path(__file__).resolve().parent.parent / "app"

# File extensions to scan
_SCAN_EXTENSIONS = {".py"}

# Ghost field names: attributes that must NEVER appear in app/ source code
# because they don't exist on any Pydantic schema.
# Add new entries here whenever a schema field is renamed.
_GHOST_NAMES: list[str] = [
    "pinned_chairman_member_id",   # renamed to chairman_member_id (2026-07-13)
    # "old_field_name_here",       # template for future additions
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _scan(root: Path, ghost_names: list[str], quiet: bool) -> list[tuple[Path, int, str]]:
    """
    Walk *root* recursively and return every (file, lineno, line) tuple
    where any ghost name appears as a token boundary match.
    """
    hits: list[tuple[Path, int, str]] = []
    patterns = [re.compile(rf"\b{re.escape(name)}\b") for name in ghost_names]

    for path in sorted(root.rglob("*")):
        if path.suffix not in _SCAN_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in patterns:
                if pat.search(line):
                    hits.append((path, lineno, line.rstrip()))

    return hits


# ── Entry point ───────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress 'OK — no ghost names found' output.",
    )
    parser.add_argument(
        "--root", type=Path, default=_BACKEND_ROOT,
        help="Backend source root to scan (default: app/ next to this script).",
    )
    args = parser.parse_args(argv)

    hits = _scan(args.root, _GHOST_NAMES, quiet=args.quiet)

    if hits:
        print(
            "[FAIL] Schema/router drift detected -- ghost field names found in source:\n",
            file=sys.stderr,
        )
        for path, lineno, line in hits:
            rel = path.relative_to(args.root.parent)
            print(f"  {rel}:{lineno}:  {line}", file=sys.stderr)
        print(
            "\nFix: use the canonical field name instead of the ghost name.\n"
            "If a field was intentionally renamed, update _GHOST_NAMES in this script.",
            file=sys.stderr,
        )
        return 1

    if not args.quiet:
        print("[OK] No ghost field names found -- schema/router names are in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
