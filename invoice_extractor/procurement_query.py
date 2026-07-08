import argparse
import json
import re
import sqlite3
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "procurement_index.sqlite"


def dict_rows(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [dict(row) for row in cursor.fetchall()]


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def money(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"RM {float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def quantity(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def extract_limit(question: str, default: int = 10) -> int:
    match = re.search(r"\btop\s+(\d+)\b|\bfirst\s+(\d+)\b|\blimit\s+(\d+)\b", question, re.I)
    if not match:
        return default
    return max(1, min(50, int(next(group for group in match.groups() if group))))


def extract_amount(question: str) -> float | None:
    match = re.search(r"(?:rm|above|over|more than|greater than)\s*([0-9][0-9,]*(?:\.\d+)?)", question, re.I)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def extract_search_term(question: str) -> str:
    quoted = re.search(r'"([^"]+)"|\'([^\']+)\'', question)
    if quoted:
        return next(group for group in quoted.groups() if group).strip()

    lowered = question.lower()
    for marker in [" for ", " from ", " supplier ", " item ", " called ", " named "]:
        if marker in lowered:
            index = lowered.rfind(marker) + len(marker)
            term = question[index:]
            term = re.sub(r"\b(in|on|during|for year|year)\s+20\d{2}\b.*$", "", term, flags=re.I)
            return term.strip(" ?.")
    return ""


def summary(connection: sqlite3.Connection) -> dict[str, Any]:
    counts = {}
    for table in [
        "source_documents",
        "purchase_orders",
        "material_requisitions",
        "line_items",
        "suppliers",
        "contacts",
        "review_issues",
    ]:
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


def top_items_by_quantity(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(i.canonical_name, li.raw_description) AS description,
                SUM(COALESCE(li.quantity_value, 0)) AS quantity,
                SUM(COALESCE(li.amount, 0)) AS spend
            FROM line_items li
            LEFT JOIN items i ON i.id = li.normalized_item_id
            WHERE li.review_status != 'rejected'
              AND COALESCE(li.raw_description, '') != ''
            GROUP BY COALESCE(li.normalized_item_id, LOWER(TRIM(li.raw_description)))
            ORDER BY quantity DESC, spend DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def top_items_by_spend(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(i.canonical_name, li.raw_description) AS description,
                SUM(COALESCE(li.quantity_value, 0)) AS quantity,
                SUM(COALESCE(li.amount, 0)) AS spend
            FROM line_items li
            LEFT JOIN items i ON i.id = li.normalized_item_id
            WHERE li.review_status != 'rejected'
              AND COALESCE(li.raw_description, '') != ''
            GROUP BY COALESCE(li.normalized_item_id, LOWER(TRIM(li.raw_description)))
            ORDER BY spend DESC, quantity DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def most_expensive_items(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(i.canonical_name, li.raw_description) AS description,
                li.unit_price,
                li.amount,
                sd.file_name AS source
            FROM line_items li
            LEFT JOIN items i ON i.id = li.normalized_item_id
            JOIN purchase_orders po ON po.id = li.purchase_order_id
            JOIN source_documents sd ON sd.id = po.source_document_id
            WHERE li.review_status != 'rejected'
              AND li.unit_price IS NOT NULL
            ORDER BY li.unit_price DESC, li.amount DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def supplier_spend(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(s.canonical_name, sd.supplier_name_from_filename, 'Unknown') AS supplier,
                COUNT(DISTINCT po.id) AS po_count,
                SUM(COALESCE(li.amount, 0)) AS spend
            FROM purchase_orders po
            JOIN source_documents sd ON sd.id = po.source_document_id
            LEFT JOIN suppliers s ON s.id = po.supplier_id
            LEFT JOIN line_items li ON li.purchase_order_id = po.id AND li.review_status != 'rejected'
            WHERE po.review_status != 'rejected'
            GROUP BY supplier
            ORDER BY spend DESC, po_count DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def contact_activity(connection: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(c.name, 'Unknown') AS contact,
                COUNT(DISTINCT po.id) AS po_count,
                SUM(COALESCE(li.amount, 0)) AS spend
            FROM purchase_orders po
            LEFT JOIN contacts c ON c.id = po.person_to_contact_id
            LEFT JOIN line_items li ON li.purchase_order_id = po.id AND li.review_status != 'rejected'
            WHERE po.review_status != 'rejected'
            GROUP BY contact
            ORDER BY po_count DESC, spend DESC
            LIMIT ?
            """,
            (limit,),
        )
    )


def monthly_spend(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                sd.month_code,
                COUNT(DISTINCT po.id) AS po_count,
                SUM(COALESCE(li.amount, 0)) AS spend
            FROM source_documents sd
            JOIN purchase_orders po ON po.source_document_id = sd.id
            LEFT JOIN line_items li ON li.purchase_order_id = po.id AND li.review_status != 'rejected'
            WHERE po.review_status != 'rejected'
            GROUP BY sd.month_code
            ORDER BY sd.month_code
            """
        )
    )


def purchases_above(connection: sqlite3.Connection, amount: float, limit: int) -> list[dict[str, Any]]:
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(i.canonical_name, li.raw_description) AS description,
                li.quantity_raw,
                li.unit_price,
                li.amount,
                COALESCE(s.canonical_name, sd.supplier_name_from_filename) AS supplier,
                sd.file_name AS source
            FROM line_items li
            LEFT JOIN items i ON i.id = li.normalized_item_id
            JOIN purchase_orders po ON po.id = li.purchase_order_id
            JOIN source_documents sd ON sd.id = po.source_document_id
            LEFT JOIN suppliers s ON s.id = po.supplier_id
            WHERE li.review_status != 'rejected'
              AND COALESCE(li.amount, 0) >= ?
            ORDER BY li.amount DESC
            LIMIT ?
            """,
            (amount, limit),
        )
    )


def search_supplier(connection: sqlite3.Connection, term: str, limit: int) -> list[dict[str, Any]]:
    like = f"%{term}%"
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(i.canonical_name, li.raw_description) AS description,
                li.quantity_raw,
                li.unit_price,
                li.amount,
                po.po_number,
                COALESCE(s.canonical_name, sd.supplier_name_from_filename) AS supplier,
                sd.file_name AS source
            FROM line_items li
            LEFT JOIN items i ON i.id = li.normalized_item_id
            JOIN purchase_orders po ON po.id = li.purchase_order_id
            JOIN source_documents sd ON sd.id = po.source_document_id
            LEFT JOIN suppliers s ON s.id = po.supplier_id
            WHERE li.review_status != 'rejected'
              AND (
                s.canonical_name LIKE ?
                OR sd.supplier_name_from_filename LIKE ?
              )
            ORDER BY sd.month_code, po.po_number, li.row_number
            LIMIT ?
            """,
            (like, like, limit),
        )
    )


def item_price_trend(connection: sqlite3.Connection, term: str, limit: int) -> list[dict[str, Any]]:
    like = f"%{term}%"
    return dict_rows(
        connection.execute(
            """
            SELECT
                COALESCE(i.canonical_name, li.raw_description) AS description,
                li.raw_description AS raw_description,
                li.quantity_raw,
                li.unit_price,
                li.amount,
                po.po_date,
                po.po_number,
                COALESCE(s.canonical_name, sd.supplier_name_from_filename) AS supplier,
                sd.file_name AS source
            FROM line_items li
            LEFT JOIN items i ON i.id = li.normalized_item_id
            JOIN purchase_orders po ON po.id = li.purchase_order_id
            JOIN source_documents sd ON sd.id = po.source_document_id
            LEFT JOIN suppliers s ON s.id = po.supplier_id
            WHERE li.review_status != 'rejected'
              AND (li.raw_description LIKE ? OR i.canonical_name LIKE ?)
            ORDER BY COALESCE(po.po_date, sd.month_code), po.po_number, li.id
            LIMIT ?
            """,
            (like, like, limit),
        )
    )


def answer_question(question: str, db_path: Path | str = DEFAULT_DB_PATH) -> dict[str, Any]:
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    clean_question = question.strip()
    lowered = clean_question.lower()
    limit = extract_limit(clean_question)

    with connect(db_path) as connection:
        if not clean_question or any(word in lowered for word in ["summary", "status", "count"]):
            counts = summary(connection)
            return {
                "intent": "summary",
                "answer": (
                    f"Database has {counts['source_documents']} documents, "
                    f"{counts['purchase_orders']} purchase orders, "
                    f"{counts['material_requisitions']} material requisitions, "
                    f"and {counts['line_items']} line items."
                ),
                "rows": [counts],
            }

        amount = extract_amount(clean_question)
        if amount is not None and any(word in lowered for word in ["above", "over", "more than", "greater than", "rm"]):
            rows = purchases_above(connection, amount, limit)
            return {
                "intent": "purchases_above",
                "answer": f"Found {len(rows)} purchase line(s) at or above {money(amount)}.",
                "rows": rows,
            }

        if "supplier" in lowered and any(word in lowered for word in ["top", "most", "spend", "spent", "bought"]):
            rows = supplier_spend(connection, limit)
            return {
                "intent": "supplier_spend",
                "answer": f"Top supplier by spend is {rows[0]['supplier']} at {money(rows[0]['spend'])}." if rows else "No supplier spend found.",
                "rows": rows,
            }

        if any(word in lowered for word in ["contact", "person", "requester", "requested"]):
            rows = contact_activity(connection, limit)
            return {
                "intent": "contact_activity",
                "answer": f"Top contact is {rows[0]['contact']} with {rows[0]['po_count']} P.O(s)." if rows else "No contact activity found.",
                "rows": rows,
            }

        if any(word in lowered for word in ["monthly", "month", "by month"]):
            rows = monthly_spend(connection)
            return {
                "intent": "monthly_spend",
                "answer": f"Monthly spend is available for {len(rows)} month code(s).",
                "rows": rows,
            }

        if any(word in lowered for word in ["trend", "history", "price for", "price of"]):
            term = extract_search_term(clean_question)
            if term:
                rows = item_price_trend(connection, term, limit)
                return {
                    "intent": "item_price_trend",
                    "answer": f"Found {len(rows)} matching price record(s) for {term}.",
                    "rows": rows,
                }

        if "from " in lowered:
            term = extract_search_term(clean_question)
            if term:
                rows = search_supplier(connection, term, limit)
                return {
                    "intent": "supplier_search",
                    "answer": f"Found {len(rows)} purchase line(s) from suppliers matching {term}.",
                    "rows": rows,
                }

        if any(word in lowered for word in ["expensive", "highest price", "unit price", "most costly"]):
            rows = most_expensive_items(connection, limit)
            return {
                "intent": "most_expensive_items",
                "answer": f"Most expensive unit price is {rows[0]['description']} at {money(rows[0]['unit_price'])}." if rows else "No unit prices found.",
                "rows": rows,
            }

        if any(word in lowered for word in ["spend", "spent", "highest amount", "total amount"]):
            rows = top_items_by_spend(connection, limit)
            return {
                "intent": "top_items_by_spend",
                "answer": f"Highest spend item is {rows[0]['description']} at {money(rows[0]['spend'])}." if rows else "No item spend found.",
                "rows": rows,
            }

        rows = top_items_by_quantity(connection, limit)
        return {
            "intent": "top_items_by_quantity",
            "answer": f"Most bought item is {rows[0]['description']} with quantity {quantity(rows[0]['quantity'])}." if rows else "No item quantities found.",
            "rows": rows,
        }


def format_table(rows: list[dict[str, Any]], limit: int = 10) -> str:
    rows = rows[:limit]
    if not rows:
        return ""
    columns = list(rows[0].keys())
    display_rows: list[dict[str, str]] = []
    for row in rows:
        display_row = {}
        for column in columns:
            value = row.get(column, "")
            if column in {"amount", "spend", "unit_price", "total_amount"}:
                value = money(value)
            elif column in {"quantity", "quantity_value"}:
                value = quantity(value)
            display_row[column] = str(value)
        display_rows.append(display_row)
    widths = {
        column: min(42, max(len(column), *(len(row.get(column, "")) for row in display_rows)))
        for column in columns
    }
    header = " | ".join(column.ljust(widths[column]) for column in columns)
    divider = "-+-".join("-" * widths[column] for column in columns)
    lines = [header, divider]
    for row in display_rows:
        values = []
        for column in columns:
            text = row.get(column, "")
            if len(text) > widths[column]:
                text = text[: widths[column] - 1] + "..."
            values.append(text.ljust(widths[column]))
        lines.append(" | ".join(values))
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask read-only questions about the procurement index.")
    parser.add_argument("question", nargs="*", help="Question to ask, for example: what item was bought most?")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--json", action="store_true", help="Print raw JSON response.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    question = " ".join(args.question).strip() or "summary"
    result = answer_question(question, args.db)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return
    print(result["answer"])
    table = format_table(result["rows"])
    if table:
        print()
        print(table)


if __name__ == "__main__":
    main()
