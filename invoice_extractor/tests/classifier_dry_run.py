#!/usr/bin/env python3
"""
Classifier dry-run test for Phase 1.

Runs the weighted classifier scorer against OCR text from every golden-set image.
Asserts every TUJU invoice classifies as tuju_galaxy_invoice and every DO as
tuju_galaxy_delivery_order with no ambiguous results.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from document_profiles import load_profiles, classify_best_profile, score_profile_classifier
from invoice_bot import IMAGE_DIR, create_ocr_ready_image, ocr_text_and_confidence

GOLDEN_DIR = PROJECT_ROOT / "tests" / "regression" / "golden"
PROFILES_DIR = PROJECT_ROOT / "data" / "document_profiles"


def get_ocr_text(image_id: str) -> str:
    image_path = IMAGE_DIR / f"{image_id}.jpg"
    ocr_path = create_ocr_ready_image(image_path)
    text, _confidence = ocr_text_and_confidence(ocr_path)
    return text


def main() -> int:
    print("=" * 60)
    print("Classifier Dry-Run Test")
    print("=" * 60)
    print()

    profiles = load_profiles(PROFILES_DIR)
    print(f"Loaded {len(profiles)} profiles:")
    for p in profiles:
        markers = p.classifier.markers if p.classifier else []
        thr = p.classifier.match_threshold if p.classifier else "N/A"
        print(f"  {p.id}: {len(markers)} markers, threshold={thr}")
    print()

    golden_files = sorted(GOLDEN_DIR.glob("*.json"))
    print(f"Testing against {len(golden_files)} golden images")
    print()

    passes = 0
    failures = 0
    ambiguous = 0
    skipped = 0

    for gf in golden_files:
        with open(gf) as f:
            golden = json.load(f)

        image_id = gf.stem
        expected_type = golden.get("document_type", "")

        if expected_type == "invoice":
            expected_profile_id = "tuju_galaxy_invoice"
        elif expected_type == "delivery_order":
            expected_profile_id = "tuju_galaxy_delivery_order"
        else:
            print(f"  SKIP {image_id}: unknown type '{expected_type}'")
            skipped += 1
            continue

        print(f"  OCR: {image_id}...", end=" ", flush=True)
        try:
            text = get_ocr_text(image_id)
        except Exception as exc:
            print(f"FAIL (OCR error: {exc})")
            failures += 1
            continue

        scores = {}
        for p in profiles:
            scores[p.id] = score_profile_classifier(p, text)

        best_id, status, score, runner_up = classify_best_profile(profiles, text)

        score_str = " ".join(f"{k}={v}" for k, v in sorted(scores.items()))
        print(f"score={score} runner_up={runner_up} status={status} best={best_id}")

        if status == "matched" and best_id == expected_profile_id:
            passes += 1
        elif status == "ambiguous":
            print(f"    !! AMBIGUOUS: expected {expected_profile_id}, runner_up={runner_up}")
            ambiguous += 1
        elif status == "below_threshold":
            print(f"    !! BELOW THRESHOLD: expected {expected_profile_id}, scores={score_str}")
            failures += 1
        else:
            print(f"    !! WRONG: expected {expected_profile_id}, got {best_id} (status={status})")
            failures += 1

    print()
    print("=" * 60)
    print(f"Results: {passes} passed, {failures} failed, {ambiguous} ambiguous, {skipped} skipped")
    print("=" * 60)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())