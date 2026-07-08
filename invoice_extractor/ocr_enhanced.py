#!/usr/bin/env python3
"""
Multi-version OCR comparison for invoice images.

After the OpenCV pipeline creates multiple enhanced versions of an invoice
image, this module runs the existing Tesseract OCR engine on each version,
scores the results, selects the best one, and saves a comparison report.

Usage (from invoice_bot.py)::

    from ocr_enhanced import run_multi_ocr_comparison

    # After preprocess_invoice() has run...
    best_text, best_result = run_multi_ocr_comparison(
        enhanced_dir=enhanced_dir,
        ocr_func=ocr_single_text_and_confidence,
    )

Functions
---------
- run_ocr_on_versions    — OCR all 7 enhanced image versions
- score_ocr_result       — Score a single OCR result for invoice relevance
- select_best_ocr_result — Pick the best from a dict of scored results
- run_multi_ocr_comparison — All of the above + save ocr_comparison.json
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── version list ──────────────────────────────────────────────────────
# Order matters only for tie-breaking (first in list wins ties).
ENHANCED_VERSIONS = [
    "preprocessed_ocr",
    "clean",
    "sharp",
    "denoised",
    "threshold",
    "shadow_removed",
    "table_friendly",
]

# Keywords checked in every OCR result
INVOICE_KEYWORDS = [
    "invoice",
    "tax invoice",
    "date",
    "total",
    "amount",
    "supplier",
    "bill to",
    "rm",
    "sst",
    "delivery order",
    "contact",
    "quantity",
    "unit price",
    "subtotal",
]


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

def run_ocr_on_versions(
    enhanced_dir: Path,
    ocr_func: Callable[[Path], tuple[str, float]],
) -> dict[str, dict[str, Any]]:
    """Run OCR on every available enhanced image version.

    Parameters
    ----------
    enhanced_dir:
        Directory containing ``<version>.jpg`` files.
    ocr_func:
        A callable ``(image_path) -> (text, confidence)``.  Typically
        ``ocr_single_text_and_confidence`` from ``invoice_bot``.

    Returns
    -------
    A dict keyed by version name, each value containing:
    ``image_version``, ``image_path``, ``text``, ``confidence``,
    ``word_count``, ``keyword_matches``, and ``error`` (or ``None``).
    """
    ocr_results: dict[str, dict[str, Any]] = {}

    for version in ENHANCED_VERSIONS:
        image_file = enhanced_dir / f"{version}.jpg"
        if not image_file.exists():
            logger.warning("Enhanced image not found, skipping: %s", image_file)
            continue

        try:
            text, confidence = ocr_func(image_file)
            word_count = len(re.findall(r"\S+", text))

            keyword_matches: dict[str, bool] = {}
            text_lower = text.lower()
            for kw in INVOICE_KEYWORDS:
                keyword_matches[kw] = kw in text_lower

            ocr_results[version] = {
                "image_version": version,
                "image_path": str(image_file.resolve()),
                "text": text,
                "confidence": round(confidence, 2),
                "word_count": word_count,
                "keyword_matches": keyword_matches,
                "error": None,
            }

            logger.info(
                "OCR version=%-20s  confidence=%5.1f  words=%4d",
                version, confidence, word_count,
            )
        except Exception as exc:
            logger.warning("OCR failed for version=%s: %s", version, exc)
            ocr_results[version] = {
                "image_version": version,
                "image_path": str(image_file.resolve()),
                "text": "",
                "confidence": 0.0,
                "word_count": 0,
                "keyword_matches": {},
                "error": str(exc),
            }

    return ocr_results


def score_ocr_result(result: dict[str, Any]) -> float:
    """Score a single OCR result for invoice-document quality.

    The scoring function considers (in order of weight):

    1. Presence of currency / amount expressions (RM, total, subtotal).
    2. Presence of a date pattern.
    3. Presence of an invoice / D.O number pattern.
    4. The ``total`` keyword.
    5. Supplier or company-related text.
    6. Number of readable words — longer, substantive results score higher.
    7. OCR confidence value.
    8. A per-keyword bonus for each matched invoice keyword.
    """
    text = result.get("text", "")
    confidence = result.get("confidence", 0.0)
    word_count = result.get("word_count", 0)
    keywords = result.get("keyword_matches", {})

    score = 0.0

    # ── 1. Amount / RM detected ──────────────────────────────────────
    if re.search(r"\brm\b", text, re.IGNORECASE):
        score += 15
    if re.search(r"rm\s*\d+[\d,.]*", text, re.IGNORECASE):
        score += 10
    if re.search(
        r"\b(?:total|amount|subtotal|grand total|balance due)\b.*?\d",
        text,
        re.IGNORECASE,
    ):
        score += 10

    # ── 2. Date detected ─────────────────────────────────────────────
    date_patterns = [
        r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b",
        r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
        r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\b",
    ]
    for pattern in date_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            score += 15
            break

    # ── 3. Invoice / D.O number pattern detected ─────────────────────
    if re.search(
        r"(?:invoice|tax\s*invoice|do|delivery\s*order)\s*(?:no|number|#)?\s*[:.]?\s*[\w-]+",
        text,
        re.IGNORECASE,
    ):
        score += 15
    if re.search(r"(?:TG|INV|DO)[-/\s]?\w{4,}", text, re.IGNORECASE):
        score += 10

    # ── 4. "total" keyword ───────────────────────────────────────────
    if keywords.get("total", False):
        score += 10
    if re.search(r"\btotal\b", text, re.IGNORECASE):
        score += 5

    # ── 5. Supplier / company text ───────────────────────────────────
    if keywords.get("supplier", False):
        score += 10
    if keywords.get("bill to", False):
        score += 8
    if re.search(
        r"\b(?:company|sdn\s+bhd|bhd|llc|ltd|inc|pty|gmbh)\b",
        text,
        re.IGNORECASE,
    ):
        score += 8

    # ── 6. Word count — more words → more signal ─────────────────────
    if word_count >= 200:
        score += 20
    elif word_count >= 100:
        score += 15
    elif word_count >= 50:
        score += 10
    elif word_count >= 20:
        score += 5

    # ── 7. OCR confidence ────────────────────────────────────────────
    if confidence >= 80:
        score += 20
    elif confidence >= 60:
        score += 15
    elif confidence >= 40:
        score += 10
    elif confidence >= 20:
        score += 5

    # ── Penalty for near-empty results ───────────────────────────────
    if word_count < 5:
        score *= 0.3

    # ── 8. Keyword coverage bonus ────────────────────────────────────
    keyword_count = sum(1 for v in keywords.values() if v)
    score += keyword_count * 2

    return round(score, 1)


def select_best_ocr_result(
    scored_results: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    """Return ``(best_version, best_result)`` from a scored results dict.

    Every result dict is expected to have a ``score`` key (set by caller
    after calling :func:`score_ocr_result`).  Ties are broken by the
    original order in ``ENHANCED_VERSIONS``.
    """
    if not scored_results:
        raise ValueError("No OCR results to select from")

    best_version = max(
        ENHANCED_VERSIONS,
        key=lambda v: scored_results.get(v, {}).get("score", -1.0),
    )
    best_result = scored_results[best_version]

    logger.info(
        "Best OCR version=%-20s  score=%5.1f  confidence=%5.1f  words=%4d",
        best_version,
        best_result.get("score", 0.0),
        best_result.get("confidence", 0.0),
        best_result.get("word_count", 0),
    )

    return best_version, best_result


def save_ocr_comparison(
    scored_results: dict[str, dict[str, Any]],
    best_version: str,
    output_dir: Path,
) -> Path:
    """Write ``ocr_comparison.json`` inside ``output_dir``.

    The file contains a compact summary of every version's score,
    confidence, word count, keyword hits, text length, and errors.
    """
    comparison: dict[str, Any] = {
        "best_version": best_version,
        "best_score": scored_results.get(best_version, {}).get("score", 0.0),
        "total_versions_tested": len(scored_results),
        "versions": {
            v: {
                "score": r.get("score", 0.0),
                "confidence": r.get("confidence", 0.0),
                "word_count": r.get("word_count", 0),
                "keyword_hits": sum(
                    1 for vv in r.get("keyword_matches", {}).values() if vv
                ),
                "text_length": len(r.get("text", "")),
                "error": r.get("error"),
            }
            for v, r in scored_results.items()
        },
    }

    comparison_path = output_dir / "ocr_comparison.json"
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump(comparison, fh, indent=2, ensure_ascii=False)

    logger.info("OCR comparison saved to %s", comparison_path)
    return comparison_path


def run_multi_ocr_comparison(
    enhanced_dir: Path,
    ocr_func: Callable[[Path], tuple[str, float]],
) -> tuple[str, dict[str, Any]]:
    """Convenience: run OCR on all versions, score, select best, save JSON.

    Parameters
    ----------
    enhanced_dir:
        Directory containing ``<version>.jpg`` files.
    ocr_func:
        A callable ``(image_path) -> (text, confidence)``.

    Returns
    -------
    ``(best_text, best_result_dict)``.

    Side effect
    -----------
    Writes ``enhanced_dir / ocr_comparison.json``.
    """
    ocr_results = run_ocr_on_versions(enhanced_dir, ocr_func)

    if not ocr_results:
        logger.warning("No OCR results from any enhanced version")
        return "", {}

    for version, result in ocr_results.items():
        result["score"] = score_ocr_result(result)

    best_version, best_result = select_best_ocr_result(ocr_results)
    save_ocr_comparison(ocr_results, best_version, enhanced_dir)

    return best_result.get("text", ""), best_result