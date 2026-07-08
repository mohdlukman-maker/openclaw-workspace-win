"""
OpenCV-based invoice image preprocessing pipeline.

Pipeline steps:
  1. Load and preserve the original raw image.
  2. Fix image orientation (EXIF + content-based heuristics).
  3. Detect and crop the document/invoice area.
  4. Apply perspective correction if the photo is taken at an angle.
  5. Deskew the document.
  6. Convert to grayscale.
  7. Apply denoising.
  8. Improve contrast.
  9. Apply thresholding where suitable.
 10. Save all processed output images for debugging.

Six enhanced versions are created after the main pipeline:
  - clean         — grayscale + contrast enhancement (CLAHE)
  - sharp         — grayscale + sharpening (unsharp mask)
  - denoised      — grayscale + denoising (NL-Means)
  - threshold     — adaptive thresholding (Gaussian)
  - shadow_removed — background normalisation / shadow removal
  - table_friendly — contrast enhancement while preserving table lines
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

def preprocess_invoice(image_path: Path, output_dir: Path) -> dict[str, Path]:
    """
    Run the full OpenCV preprocessing pipeline on an invoice image.

    Args:
        image_path: Path to the raw downloaded image (jpg/png).
        output_dir: Directory where enhanced outputs will be saved.

    Returns:
        Dict mapping version names to their saved file paths.
        Always includes 'original', 'preprocessed', and 'preprocessed_ocr'.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. Load image ────────────────────────────────────────────────
    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    # Save original (preserved exactly as received)
    orig_path = output_dir / "original.jpg"
    cv2.imwrite(str(orig_path), img)
    logger.info("Saved original to %s", orig_path)

    # ── 2. Fix orientation ───────────────────────────────────────────
    img = _fix_orientation(img)

    # ── 3. Detect and crop document area ─────────────────────────────
    img, doc_contour = _detect_and_crop_document(img)

    # ── 4. Perspective correction ────────────────────────────────────
    if doc_contour is not None:
        img = _perspective_correct(img, doc_contour)

    # ── 5. Deskew ────────────────────────────────────────────────────
    img = _deskew(img)

    # Save preprocessed (colour, perspective-corrected, deskewed)
    preprocessed_path = output_dir / "preprocessed.jpg"
    cv2.imwrite(str(preprocessed_path), img)

    # ── 6. Grayscale ─────────────────────────────────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ── 7. Denoise (base) ────────────────────────────────────────────
    denoised_base = cv2.fastNlMeansDenoising(
        gray, h=10, templateWindowSize=7, searchWindowSize=21,
    )

    # ── 8. Contrast enhancement (base) ───────────────────────────────
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast_base = clahe.apply(denoised_base)

    # ── 9. Thresholding (base) ───────────────────────────────────────
    _, threshold_base = cv2.threshold(
        contrast_base, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )

    # ═════════════════════════════════════════════════════════════════
    #  Create 6 enhanced versions (each as a standalone function)
    # ═════════════════════════════════════════════════════════════════

    versions: dict[str, Path] = {}

    # 1. Clean version — grayscale + contrast enhancement
    clean = _create_clean_version(gray, denoised_base, contrast_base)
    clean_path = output_dir / "clean.jpg"
    cv2.imwrite(str(clean_path), clean)
    versions["clean"] = clean_path

    # 2. Sharp version — grayscale + sharpening
    sharp = _create_sharp_version(gray, denoised_base)
    sharp_path = output_dir / "sharp.jpg"
    cv2.imwrite(str(sharp_path), sharp)
    versions["sharp"] = sharp_path

    # 3. Denoised version — grayscale + denoising
    denoised = _create_denoised_version(gray)
    denoised_path = output_dir / "denoised.jpg"
    cv2.imwrite(str(denoised_path), denoised)
    versions["denoised"] = denoised_path

    # 4. Threshold version — adaptive thresholding
    threshold = _create_threshold_version(gray, denoised_base, contrast_base, threshold_base)
    threshold_path = output_dir / "threshold.jpg"
    cv2.imwrite(str(threshold_path), threshold)
    versions["threshold"] = threshold_path

    # 5. Shadow-removed version — background normalisation / shadow removal
    shadow = _create_shadow_removed_version(gray)
    shadow_path = output_dir / "shadow_removed.jpg"
    cv2.imwrite(str(shadow_path), shadow)
    versions["shadow_removed"] = shadow_path

    # 6. Table-friendly version — contrast enhancement while preserving table lines
    table = _create_table_friendly_version(gray, denoised_base, contrast_base)
    table_path = output_dir / "table_friendly.jpg"
    cv2.imwrite(str(table_path), table)
    versions["table_friendly"] = table_path

    # The "best" OCR version (clean) is the one we'll pass downstream
    best_path = output_dir / "preprocessed_ocr.jpg"
    cv2.imwrite(str(best_path), clean)

    result = {
        "original": orig_path,
        "preprocessed": preprocessed_path,
        "preprocessed_ocr": best_path,
        **versions,
    }

    logger.info(
        "Preprocessing complete. Saved %d versions to %s",
        len(result), output_dir,
    )
    return result


# ═══════════════════════════════════════════════════════════════════════
#  Step 2 — Orientation
# ═══════════════════════════════════════════════════════════════════════

def _fix_orientation(img: np.ndarray) -> np.ndarray:
    """Fix image orientation using EXIF-style content-based heuristics.

    Rotates landscape images to portrait, then checks whether the
    document is upside-down by comparing brightness of the top vs.
    bottom halves (headers are typically darker).
    """
    h, w = img.shape[:2]

    # Landscape → rotate to portrait
    if w > h:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        h, w = img.shape[:2]

    # Detect upside-down by comparing brightness of top vs bottom half.
    # In a typical document the top (header) has more text → darker.
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    top_half = gray[: h // 2, :]
    bottom_half = gray[h // 2 :, :]

    top_mean = float(cv2.mean(top_half)[0])
    bottom_mean = float(cv2.mean(bottom_half)[0])

    # Bottom is significantly darker → image is upside-down
    if bottom_mean < top_mean - 15:
        img = cv2.rotate(img, cv2.ROTATE_180)
        logger.info("Rotated 180° (image was upside-down)")

    return img


# ═══════════════════════════════════════════════════════════════════════
#  Step 3 — Document area detection
# ═══════════════════════════════════════════════════════════════════════

def _detect_and_crop_document(
    img: np.ndarray,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Detect the largest rectangular document region and crop to it.

    Uses Canny edge detection, dilation, and contour approximation.
    Falls back to the full image when no suitable quadrilateral is found.

    Returns:
        (cropped_image, document_contour_or_None)
    """
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Blur to reduce noise before edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Edge detection
    edged = cv2.Canny(blurred, 50, 150)

    # Dilate edges to close gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    dilated = cv2.dilate(edged, kernel, iterations=2)

    # Find contours
    contours, _ = cv2.findContours(
        dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
    )

    if not contours:
        logger.warning("No contours found; using full image")
        return img, None

    # Sort by area descending
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    doc_contour: np.ndarray | None = None
    for contour in contours[:10]:
        area = cv2.contourArea(contour)
        if area < 0.3 * w * h:
            continue

        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        if len(approx) == 4:
            doc_contour = approx
            logger.info(
                "Document contour detected: area=%.1f%% of image",
                100.0 * area / (w * h),
            )
            break

    if doc_contour is None:
        # Fallback: use the largest contour (may not be a perfect quad)
        largest = contours[0]
        if cv2.contourArea(largest) > 0.1 * w * h:
            rect = cv2.minAreaRect(largest)
            doc_contour = cv2.boxPoints(rect)
            doc_contour = np.int32(doc_contour)
            logger.info("Using min-area rectangle as fallback document contour")
        else:
            logger.warning("No large contour found; using full image")
            return img, None

    return img, doc_contour


# ═══════════════════════════════════════════════════════════════════════
#  Step 4 — Perspective correction
# ═══════════════════════════════════════════════════════════════════════

def _perspective_correct(img: np.ndarray, contour: np.ndarray) -> np.ndarray:
    """Apply perspective transform to obtain a top-down view of the document."""
    # Order points: top-left, top-right, bottom-right, bottom-left
    rect = _order_points(contour.reshape(4, 2))
    tl, tr, br, bl = rect

    # Compute target width
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = max(int(width_a), int(width_b))

    # Compute target height
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = max(int(height_a), int(height_b))
    if max_width <= 0 or max_height <= 0:
        logger.warning("Perspective correction rejected invalid contour dimensions; using full image")
        return img
    short_side = min(max_width, max_height)
    long_side = max(max_width, max_height)
    if short_side < 0.45 * long_side:
        logger.warning(
            "Perspective correction rejected thin crop %dx%d; using full image",
            max_width,
            max_height,
        )
        return img

    dst = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1],
    ], dtype=np.float32)

    matrix = cv2.getPerspectiveTransform(rect.astype(np.float32), dst)
    warped = cv2.warpPerspective(img, matrix, (max_width, max_height))

    logger.info(
        "Perspective corrected: %dx%d → %dx%d",
        img.shape[1], img.shape[0], max_width, max_height,
    )
    return warped


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 corner points: TL → TR → BR → BL."""
    rect = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # top-left    (smallest sum)
    rect[2] = pts[np.argmax(s)]   # bottom-right (largest sum)

    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]   # top-right    (smallest diff)
    rect[3] = pts[np.argmax(diff)]   # bottom-left  (largest diff)

    return rect


# ═══════════════════════════════════════════════════════════════════════
#  Step 5 — Deskew
# ═══════════════════════════════════════════════════════════════════════

def _deskew(img: np.ndarray) -> np.ndarray:
    """Detect and correct skew angle using the MinAreaRect of text pixels."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bitwise_not(gray)

    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = np.column_stack(np.where(binary > 0))

    if len(coords) == 0:
        logger.warning("No text pixels found for deskew; skipping")
        return img

    angle = cv2.minAreaRect(coords)[-1]

    if angle < -45:
        angle = 90 + angle
    elif angle > 45:
        angle -= 90

    if abs(angle) < 0.5:
        logger.info("Skew angle %.2f° negligible; skipping", angle)
        return img

    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)

    matrix[0, 2] += (new_w / 2) - center[0]
    matrix[1, 2] += (new_h / 2) - center[1]

    rotated = cv2.warpAffine(
        img, matrix, (new_w, new_h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )

    logger.info("Deskew applied: angle=%.2f°", angle)
    return rotated


# ═══════════════════════════════════════════════════════════════════════
#  Enhanced version generators (one function per version)
# ═══════════════════════════════════════════════════════════════════════

def _create_clean_version(
    gray: np.ndarray,
    denoised: np.ndarray,
    contrast: np.ndarray,
) -> np.ndarray:
    """Clean version — grayscale + CLAHE contrast enhancement."""
    return contrast


def _create_sharp_version(
    gray: np.ndarray,
    denoised: np.ndarray,
) -> np.ndarray:
    """Sharp version — grayscale + unsharp masking."""
    kernel = np.array([
        [0, -1,  0],
        [-1,  5, -1],
        [0, -1,  0],
    ], dtype=np.float32)
    sharp = cv2.filter2D(denoised, -1, kernel)
    return np.clip(sharp, 0, 255).astype(np.uint8)


def _create_denoised_version(gray: np.ndarray) -> np.ndarray:
    """Denoised version — grayscale + NL-Means denoising with stronger filtering."""
    return cv2.fastNlMeansDenoising(
        gray, h=15, templateWindowSize=7, searchWindowSize=21,
    )


def _create_threshold_version(
    gray: np.ndarray,
    denoised: np.ndarray,
    contrast: np.ndarray,
    otsu: np.ndarray,
) -> np.ndarray:
    """Threshold version — adaptive Gaussian thresholding for binarized text."""
    return cv2.adaptiveThreshold(
        contrast, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        11,  # block size
        2,   # constant subtracted from mean
    )


def _create_shadow_removed_version(gray: np.ndarray) -> np.ndarray:
    """Shadow-removed version — background normalisation via morphological operations.

    Works by estimating the background illumination with a large dilation
    and blur, then using division to flatten uneven lighting.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated = cv2.morphologyEx(gray, cv2.MORPH_DILATE, kernel)
    background = cv2.GaussianBlur(dilated, (31, 31), 0)

    # Avoid division by zero
    background = np.where(background < 1, 1, background).astype(np.float32)

    shadow_removed = cv2.divide(
        gray.astype(np.float32), background, scale=255,
    )
    shadow_removed = np.clip(shadow_removed, 0, 255).astype(np.uint8)

    # Final contrast stretch
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    return clahe.apply(shadow_removed)


def _create_table_friendly_version(
    gray: np.ndarray,
    denoised: np.ndarray,
    contrast: np.ndarray,
) -> np.ndarray:
    """Table-friendly version — edge-preserving contrast enhancement.

    Uses bilateral filtering to keep table grid lines sharp, then applies
    moderate CLAHE and blends with an adaptive-threshold overlay to
    emphasise both text and table structure.
    """
    # Bilateral filter preserves edges while smoothing noise
    bilateral = cv2.bilateralFilter(denoised, 9, 75, 75)

    # Moderate CLAHE for contrast
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(bilateral)

    # Mean adaptive threshold preserves table grid structure better
    # than Gaussian for this use case
    adaptive = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_MEAN_C,
        cv2.THRESH_BINARY,
        15,  # larger block to capture table lines
        3,
    )

    # Blend: keep continuous-tone appearance while emphasising lines
    result = cv2.addWeighted(enhanced, 0.7, adaptive, 0.3, 0)
    return result.astype(np.uint8)
