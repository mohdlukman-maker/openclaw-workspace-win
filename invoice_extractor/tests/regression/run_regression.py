#!/usr/bin/env python3
"""
Regression test harness for invoice extractor.

Loads golden extraction JSONs from tests/regression/golden/,
re-runs the offline extractable portions of the pipeline on
the source images, and compares results against golden records.

Usage:
    python run_regression.py              # run all tests, report fails
    python run_regression.py --update     # overwrite golden files (use after intentional changes)
    python run_regression.py --verbose    # show all comparisons
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from invoice_bot import (
    BASE_DIR,
    DATA_DIR,
    IMAGE_DIR,
    OCR_DIR,
    extract_invoice_with_local_ocr,
    LocalOCRUnavailable,
    UnknownDocumentFormat,
    normalize_text,
    normalize_invoice_number,
)

GOLDEN_DIR = PROJECT_ROOT / "tests" / "regression" / "golden"

# Fields that can be compared offline (local OCR pipeline)
COMPARABLE_FIELDS = [
    "tax_invoice",
    "invoice_date",
    "contact_person",
    "document_type",
]

# █████████████████████████████████████████████████████████████████████
#  Helpers
# █████████████████████████████████████████████████████████████████████


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_line_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a line items list for comparison."""
    result = []
    for item in items:
        normalized = {}
        for key in ("item_no", "description", "quantity", "quantity_unit", "unit_price", "line_total"):
            val = item.get(key)
            if isinstance(val, float):
                val = round(val, 4)
            normalized[key] = val
        result.append(normalized)
    return result


def items_match(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> bool:
    """Compare two line-items lists structurally."""
    if len(a) != len(b):
        return False
    for ia, ib in zip(a, b):
        for key in ("item_no", "description", "quantity", "quantity_unit", "unit_price", "line_total"):
            va = ia.get(key)
            vb = ib.get(key)
            if isinstance(va, float) and isinstance(vb, float):
                va = round(va, 4)
                vb = round(vb, 4)
            if va != vb:
                return False
    return True


# █████████████████████████████████████████████████████████████████████
#  Core comparison
# █████████████████████████████████████████████████████████████████████


def compare_extraction(
    golden_path: Path,
    verbose: bool = False,
) -> tuple[bool, list[str]]:
    """Compare a golden extraction against re-running local OCR.

    Returns (passed, list_of_issue_descriptions).
    """
    issues: list[str] = []

    # Load golden
    with open(golden_path, "r", encoding="utf-8") as f:
        golden = json.load(f)

    golden_id = golden_path.stem  # e.g. I20260707055911172176

    # Find source image
    image_path = IMAGE_DIR / f"{golden_id}.jpg"
    if not image_path.exists():
        # Try data/images/ directly
        image_path = DATA_DIR / "images" / f"{golden_id}.jpg"
    if not image_path.exists():
        issues.append(f"Source image not found: {golden_id}.jpg")
        return False, issues

    # Verify golden has required fields
    required = ["tax_invoice", "document_type", "line_items", "local_ocr_verification"]
    for field in required:
        if field not in golden:
            issues.append(f"Golden missing required field: {field}")

    if issues:
        return False, issues

    # Verify golden structure is valid
    for item in golden.get("line_items", []):
        for key in ("item_no", "description"):
            if key not in item:
                issues.append(f"Golden line item missing key: {key}")

    # Re-run local OCR
    try:
        local_result = extract_invoice_with_local_ocr(image_path)
    except LocalOCRUnavailable as exc:
        issues.append(f"Local OCR unavailable: {exc}")
        return False, issues
    except UnknownDocumentFormat:
        issues.append("Local OCR returned UnknownDocumentFormat")
        return False, issues
    except Exception as exc:
        issues.append(f"Local OCR failed: {exc}")
        return False, issues

    # Compare local OCR verification fields
    local_ocr = golden.get("local_ocr_verification", {})
    for field in ("tax_invoice", "invoice_date"):
        golden_val = local_ocr.get(field)
        local_val = local_result.data.get(field)

        # Normalize for comparison
        if golden_val and local_val:
            golden_norm = normalize_invoice_number(golden_val) if field == "tax_invoice" else str(golden_val).strip()
            local_norm = normalize_invoice_number(local_val) if field == "tax_invoice" else str(local_val).strip()
            if golden_norm != local_norm:
                issues.append(
                    f"Local OCR mismatch for {field}: golden={golden_val!r} local={local_val!r}"
                )
        elif golden_val and not local_val:
            issues.append(f"Local OCR null for {field}, golden={golden_val!r}")
        elif local_val and not golden_val:
            issues.append(f"Local OCR has value for {field} but golden has null: local={local_val!r}")

    # Compare document type
    golden_type = golden.get("document_type", "")
    local_type = local_result.data.get("document_type", "")
    if golden_type and local_type and golden_type != local_type:
        issues.append(f"Document type mismatch: golden={golden_type} local={local_type}")

    # Compare line item count
    golden_items = golden.get("line_items", [])
    local_items = local_result.data.get("line_items", [])
    if len(golden_items) != len(local_items):
        issues.append(
            f"Line item count mismatch: golden={len(golden_items)} local={len(local_items)}"
        )

    # Compare line items structurally
    if not items_match(golden_items, local_items):
        # Only flag if counts match but content differs
        if len(golden_items) == len(local_items):
            issues.append("Line item content mismatch (descriptions, quantities, or units differ)")

    # Compare source image hash
    golden_hash = golden.get("source_image_hash")
    if golden_hash:
        actual_hash = file_sha256(image_path)
        if golden_hash != actual_hash:
            issues.append(f"Source image hash mismatch: golden={golden_hash[:16]}... actual={actual_hash[:16]}...")

    passed = len(issues) == 0
    if verbose:
        print(f"  {'PASS' if passed else 'FAIL'} {golden_id}: {len(issues)} issues")

    return passed, issues


# █████████████████████████████████████████████████████████████████████
#  Main
# █████████████████████████████████████████████████████████████████████


def main() -> int:
    parser = argparse.ArgumentParser(description="Invoice extractor regression harness")
    parser.add_argument("--update", action="store_true", help="Update golden files (not implemented in offline mode)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all comparison results")
    args = parser.parse_args()

    if not GOLDEN_DIR.exists():
        print(f"Golden directory not found: {GOLDEN_DIR}")
        return 1

    golden_files = sorted(GOLDEN_DIR.glob("*.json"))
    if not golden_files:
        print(f"No golden files found in {GOLDEN_DIR}")
        return 1

    print(f"Running regression on {len(golden_files)} golden files...", flush=True)
    print(f"Local OCR pipeline: running (verifies local_ocr_verification + structure)", flush=True)
    print(flush=True)

    pass_count = 0
    fail_count = 0
    all_issues: list[tuple[str, list[str]]] = []

    # Test all golden files
    for gf in golden_files:
        if args.verbose:
            print(f"Testing: {gf.name}", flush=True)
        passed, issues = compare_extraction(gf, verbose=args.verbose)
        if passed:
            pass_count += 1
        else:
            fail_count += 1
            all_issues.append((gf.name, issues))

    print(flush=True)
    print(f"Results: {pass_count} passed, {fail_count} failed out of {len(golden_files)}", flush=True)

    if fail_count > 0:
        print(flush=True)
        print("Failed tests:", flush=True)
        for name, issues in all_issues:
            print(f"  {name}:")
            for issue in issues:
                print(f"    - {issue}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())