#!/usr/bin/env python3
"""
Test script for the OpenCV invoice image enhancement pipeline.

Usage:
    python test_image_processor.py path/to/invoice.jpg

Runs preprocess_invoice() on the given image, saves all enhanced versions
to a test output folder, and reports which files were created.

This script does NOT call OCR or interact with Telegram.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

from image_processor import preprocess_invoice


def configure_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s %(levelname)s: %(message)s",
        level=logging.INFO,
        handlers=[logging.StreamHandler()],
    )


def main() -> int:
    configure_logging()
    logger = logging.getLogger("test_image_processor")

    parser = argparse.ArgumentParser(
        description="Test the OpenCV invoice image enhancement pipeline.",
    )
    parser.add_argument(
        "image_path",
        type=str,
        help="Path to the invoice image file (jpg/png) to test.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=(
            "Output directory for enhanced versions. "
            "Defaults to 'test_outputs/<timestamp>/'."
        ),
    )
    args = parser.parse_args()

    # ── Validate input image ─────────────────────────────────────────
    image_path = Path(args.image_path)
    if not image_path.exists():
        logger.error("File not found: %s", image_path)
        return 1
    if not image_path.is_file():
        logger.error("Not a file: %s", image_path)
        return 1

    # ── Determine output directory ───────────────────────────────────
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_dir = Path(__file__).resolve().parent / "test_outputs" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Run the pipeline ─────────────────────────────────────────────
    logger.info("Input:  %s", image_path.resolve())
    logger.info("Output: %s", output_dir.resolve())
    logger.info("Size:   %.1f KB", image_path.stat().st_size / 1024)
    logger.info("Running preprocess_invoice() ...")

    start_time = time.perf_counter()

    try:
        result = preprocess_invoice(image_path, output_dir)
    except Exception as exc:
        logger.exception("Pipeline failed with an exception")
        return 1

    elapsed = time.perf_counter() - start_time

    # ── Report results ────────────────────────────────────────────────
    expected_versions = {
        "original",
        "preprocessed",
        "preprocessed_ocr",
        "clean",
        "sharp",
        "denoised",
        "threshold",
        "shadow_removed",
        "table_friendly",
    }

    print("")
    print("=" * 60)
    print("  IMAGE ENHANCEMENT PIPELINE — RESULTS")
    print("=" * 60)
    print(f"  Input file:     {image_path.name}")
    print(f"  Output folder:  {output_dir}")
    print(f"  Elapsed time:   {elapsed:.2f}s")
    print("")

    all_ok = True
    for version in sorted(expected_versions):
        path = result.get(version)
        if path and path.exists():
            size_kb = path.stat().st_size / 1024
            status = "OK"
        elif path:
            size_kb = 0
            status = "MISSING (path exists but file not found)"
            all_ok = False
        else:
            status = "MISSING (not in result dict)"
            all_ok = False

        if status == "OK":
            print(f"  [ {status:>7} ]  {version:<20s}  {path.name:<30s}  {size_kb:>8.1f} KB")
        else:
            print(f"  [{status}]  {version:<20s}")

    # Check for unexpected extra files
    extra_keys = set(result.keys()) - expected_versions
    if extra_keys:
        print("")
        print(f"  Extra unexpected keys: {', '.join(sorted(extra_keys))}")

    print("")
    print("=" * 60)

    if all_ok:
        print("  All 9 versions created successfully.")
        print(f"  OpenCV pipeline completed in {elapsed:.2f}s.")
        print("=" * 60)
        return 0
    else:
        print("  Some outputs are missing — check the log above.")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())