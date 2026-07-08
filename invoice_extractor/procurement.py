import logging
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


def safe_folder_name(value: Any, fallback: str) -> str:
    source = str(value or "").strip() or fallback
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", source)
    stem = re.sub(r"\s+", " ", stem)
    stem = stem.strip(" ._")
    return stem[:100] or fallback


def procurement_invoice_folder(
    procurement_dir: Path,
    supplier_name: str,
    invoice_number: Any,
    po_reference: Any,
) -> Path:
    supplier = safe_folder_name(supplier_name, "UNKNOWN SUPPLIER")
    invoice_folder = safe_folder_name(invoice_number, "UNKNOWN")
    po_folder = safe_folder_name(po_reference, invoice_folder)
    return procurement_dir / supplier / invoice_folder / po_folder


def convert_image_to_pdf(image_path: Path, pdf_path: Path) -> None:
    if not image_path.exists():
        raise RuntimeError(f"Source image was not found: {image_path}")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        image = ImageOps.exif_transpose(image)
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(pdf_path, "PDF", resolution=150.0)


def copy_pdf_to_procurement(source_path: Path | None, target_path: Path) -> None:
    if not source_path:
        raise RuntimeError(f"Source PDF for {target_path.name} was not created.")
    if not source_path.exists():
        raise RuntimeError(f"Source PDF was not found: {source_path}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, target_path)


def create_procurement_bundle(
    procurement_dir: Path,
    supplier_name: str,
    invoice_number: Any,
    po_reference: Any,
    po_pdf_path: Path | None,
    mr_pdf_path: Path | None,
    invoice_image_path: Path | None,
    delivery_order_image_path: Path | None,
) -> tuple[Path, list[Path], list[str]]:
    folder = procurement_invoice_folder(procurement_dir, supplier_name, invoice_number, po_reference)
    created: list[Path] = []
    issues: list[str] = []

    tasks: list[tuple[str, Any]] = [
        ("1. MR.pdf", lambda target: copy_pdf_to_procurement(mr_pdf_path, target)),
        ("2. PO.pdf", lambda target: copy_pdf_to_procurement(po_pdf_path, target)),
        ("3. Invoice.pdf", lambda target: convert_image_to_pdf(invoice_image_path or Path(""), target)),
        ("4. D.O.pdf", lambda target: convert_image_to_pdf(delivery_order_image_path or Path(""), target)),
    ]
    for filename, action in tasks:
        target = folder / filename
        try:
            action(target)
            created.append(target)
        except Exception as exc:
            logging.exception("Procurement bundle item failed: %s", filename)
            issues.append(f"{filename}: {exc}")

    return folder, created, issues
