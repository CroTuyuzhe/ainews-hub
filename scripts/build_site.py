#!/usr/bin/env python3
"""
Build static site for market sentiment dashboard.
Validates data.json, copies static assets, generates version info.
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DIST_DIR = BASE_DIR / "dist"

DATA_FILE = DATA_DIR / "data.json"
INDEX_SRC = BASE_DIR / "index.html"
INDEX_DST = DIST_DIR / "index.html"


def validate_data(data: dict) -> list:
    """Validate required fields. Returns list of warnings."""
    warnings = []

    required_keys = ["update_time", "a_share", "us_market"]
    for k in required_keys:
        if k not in data:
            warnings.append(f"Missing top-level key: {k}")

    a_share = data.get("a_share", {})
    for field in ["indexes", "market_sentiment", "panic_index", "north_flow", "volume"]:
        if field not in a_share:
            warnings.append(f"Missing a_share.{field}")

    us_market = data.get("us_market", {})
    for field in ["vix", "sp500"]:
        if field not in us_market:
            warnings.append(f"Missing us_market.{field}")

    # Check history arrays
    panic = a_share.get("panic_index", {})
    if len(panic.get("history", [])) < 2:
        warnings.append("panic_index.history has fewer than 2 entries")

    return warnings


def build():
    # Ensure dist dir
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Load data
    if not DATA_FILE.exists():
        print("[ERROR] data.json not found. Run fetch_data.py first.", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid data.json: {e}", file=sys.stderr)
        sys.exit(1)

    # Validate
    warnings = validate_data(data)
    for w in warnings:
        print(f"[WARN] {w}")

    # Copy index.html
    if INDEX_SRC.exists():
        html = INDEX_SRC.read_text(encoding="utf-8")
        INDEX_DST.write_text(html, encoding="utf-8")
        print(f"[OK] Copied index.html to {INDEX_DST}")
    else:
        print(f"[ERROR] index.html not found at {INDEX_SRC}", file=sys.stderr)
        sys.exit(1)

    # Copy data.json to dist
    import shutil
    shutil.copy2(DATA_FILE, DIST_DIR / "data.json")
    print(f"[OK] Copied data.json to {DIST_DIR / 'data.json'}")

    # Summary
    print(f"\n{'='*50}")
    print(f"Build Summary")
    print(f"{'='*50}")
    print(f"  Update time:  {data.get('update_time', 'N/A')}")
    print(f"  Warnings:     {len(warnings)}")
    if warnings:
        for w in warnings:
            print(f"    ⚠ {w}")
    if not warnings:
        print(f"  Status:       ✅ All checks passed")
    print(f"{'='*50}")


if __name__ == "__main__":
    build()
