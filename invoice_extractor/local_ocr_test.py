import argparse
from pathlib import Path

from dotenv import load_dotenv

from invoice_bot import BASE_DIR, LocalOCRUnavailable, extract_invoice_with_local_ocr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test local OCR extraction on one invoice image.")
    parser.add_argument("image", type=Path, help="Path to an invoice image.")
    return parser.parse_args()


def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    args = parse_args()
    image_path = args.image
    if not image_path.is_absolute():
        image_path = (Path.cwd() / image_path).resolve()

    try:
        result = extract_invoice_with_local_ocr(image_path)
    except LocalOCRUnavailable as exc:
        print(f"Local OCR unavailable: {exc}")
        return

    print(f"Accepted: {result.accepted}")
    print(f"Confidence: {result.average_confidence:.1f}")
    print(f"Reason: {result.reason}")
    print(f"Tax Invoice: {result.data.get('tax_invoice')}")
    print(f"Date: {result.data.get('invoice_date')}")
    print(f"Line items: {len(result.data.get('line_items', []))}")
    for item in result.data.get("line_items", []):
        print(
            f"{item.get('item_no')}. {item.get('description')} | "
            f"Qty: {item.get('quantity')} {item.get('quantity_unit') or ''}".strip()
            + f" | Unit: {item.get('unit_price')} | Amount: {item.get('line_total')}"
        )


if __name__ == "__main__":
    main()
