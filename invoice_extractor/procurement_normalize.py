import argparse
import re
import shutil
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "procurement_index.sqlite"
BACKUP_DIR = BASE_DIR / "data" / "backups"

SUPPLIER_ALIASES = {
    "MENG SOON HUAT": "MENG SOON HUAT ELECTRICAL SDN BHD",
}


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def item_key(description: str) -> str:
    text = normalized_text(description).upper()
    text = text.replace("²", "2")
    text = text.replace("×", "X")
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"\b(\d+)\s*KG\s*/\s*BAG\b", r"\1KG/BAG", text)
    text = re.sub(r"\b(\d+)\s*BOX\b", r"\1 BOX", text)
    text = re.sub(r"\bX\s*(\d+)\s*KG\b", r"X \1KG", text)
    text = re.sub(r"\bMM\s*2\b", "MM2", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def supplier_key(name: str) -> str:
    text = normalized_text(name).upper()
    return SUPPLIER_ALIASES.get(text, text)


def choose_canonical(rows: list[sqlite3.Row]) -> str:
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            int(row["line_count"] or 0),
            float(row["quantity"] or 0),
            -len(str(row["raw_description"] or "")),
        ),
        reverse=True,
    )
    return normalized_text(sorted_rows[0]["raw_description"])


def backup_database(db_path: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = BACKUP_DIR / f"{db_path.stem}_pre_normalization_{stamp}.sqlite"
    shutil.copy2(db_path, backup_path)
    return backup_path


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS supplier_aliases (
            id INTEGER PRIMARY KEY,
            supplier_id INTEGER NOT NULL,
            alias_text TEXT NOT NULL UNIQUE,
            confidence REAL NOT NULL,
            approved INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS normalization_runs (
            id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            item_groups INTEGER NOT NULL,
            item_aliases INTEGER NOT NULL,
            supplier_groups INTEGER NOT NULL,
            supplier_aliases INTEGER NOT NULL,
            backup_path TEXT
        );
        """
    )


def normalize_items(connection: sqlite3.Connection) -> tuple[int, int]:
    rows = connection.execute(
        """
        SELECT
            raw_description,
            COUNT(*) AS line_count,
            SUM(COALESCE(quantity_value, 0)) AS quantity
        FROM line_items
        WHERE COALESCE(raw_description, '') != ''
        GROUP BY raw_description
        """
    ).fetchall()

    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[item_key(row["raw_description"])].append(row)

    connection.execute("DELETE FROM item_aliases")
    connection.execute("DELETE FROM items")

    item_id_by_key: dict[str, int] = {}
    now = datetime.now(timezone.utc).isoformat()
    for key, grouped_rows in sorted(groups.items()):
        canonical = choose_canonical(grouped_rows)
        connection.execute("INSERT INTO items (canonical_name, created_at) VALUES (?, ?)", (canonical, now))
        item_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
        item_id_by_key[key] = item_id
        aliases = {normalized_text(row["raw_description"]) for row in grouped_rows}
        aliases.add(key)
        for alias in sorted(alias for alias in aliases if alias):
            connection.execute(
                "INSERT OR IGNORE INTO item_aliases (item_id, alias_text, confidence, approved) VALUES (?, ?, ?, ?)",
                (item_id, alias, 0.95, 1),
            )

    line_rows = connection.execute("SELECT id, raw_description FROM line_items").fetchall()
    for row in line_rows:
        item_id = item_id_by_key[item_key(row["raw_description"])]
        connection.execute("UPDATE line_items SET normalized_item_id = ? WHERE id = ?", (item_id, row["id"]))

    alias_count = connection.execute("SELECT COUNT(*) FROM item_aliases").fetchone()[0]
    return len(groups), int(alias_count)


def normalize_suppliers(connection: sqlite3.Connection) -> tuple[int, int]:
    rows = connection.execute("SELECT id, canonical_name, raw_name FROM suppliers").fetchall()
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[supplier_key(row["canonical_name"])].append(row)

    connection.execute("DELETE FROM supplier_aliases")

    now = datetime.now(timezone.utc).isoformat()
    supplier_id_by_key: dict[str, int] = {}
    for key, grouped_rows in sorted(groups.items()):
        canonical_row = next((row for row in grouped_rows if row["canonical_name"] == key), grouped_rows[0])
        supplier_id = int(canonical_row["id"])
        supplier_id_by_key[key] = supplier_id
        connection.execute(
            "UPDATE suppliers SET canonical_name = ?, raw_name = ? WHERE id = ?",
            (key, key, supplier_id),
        )
        aliases = {normalized_text(row["canonical_name"]) for row in grouped_rows}
        aliases.update(normalized_text(row["raw_name"]) for row in grouped_rows)
        aliases.add(key)
        for alias in sorted(alias for alias in aliases if alias):
            connection.execute(
                "INSERT OR IGNORE INTO supplier_aliases (supplier_id, alias_text, confidence, approved) VALUES (?, ?, ?, ?)",
                (supplier_id, alias, 0.95, 1),
            )
        for row in grouped_rows:
            if int(row["id"]) != supplier_id:
                connection.execute("UPDATE purchase_orders SET supplier_id = ? WHERE supplier_id = ?", (supplier_id, row["id"]))
                connection.execute("DELETE FROM suppliers WHERE id = ?", (row["id"],))

    alias_count = connection.execute("SELECT COUNT(*) FROM supplier_aliases").fetchone()[0]
    supplier_count = connection.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
    connection.execute(
        """
        INSERT INTO normalization_runs (
            created_at, item_groups, item_aliases, supplier_groups, supplier_aliases, backup_path
        )
        VALUES (?, 0, 0, ?, ?, '')
        """,
        (now, supplier_count, alias_count),
    )
    return int(supplier_count), int(alias_count)


def normalize_database(db_path: Path, dry_run: bool = False) -> dict[str, Any]:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_path = None if dry_run else backup_database(db_path)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        ensure_schema(connection)
        connection.execute("BEGIN")
        item_groups, item_aliases = normalize_items(connection)
        supplier_groups, supplier_aliases = normalize_suppliers(connection)
        if dry_run:
            connection.rollback()
        else:
            connection.execute(
                """
                UPDATE normalization_runs
                SET item_groups = ?, item_aliases = ?, backup_path = ?
                WHERE id = (SELECT MAX(id) FROM normalization_runs)
                """,
                (item_groups, item_aliases, str(backup_path)),
            )
            connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return {
        "database": str(db_path),
        "backup": str(backup_path) if backup_path else None,
        "dry_run": dry_run,
        "item_groups": item_groups,
        "item_aliases": item_aliases,
        "supplier_groups": supplier_groups,
        "supplier_aliases": supplier_aliases,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize procurement item and supplier aliases.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = normalize_database(args.db, dry_run=args.dry_run)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
