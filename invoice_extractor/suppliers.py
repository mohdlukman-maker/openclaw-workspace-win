import json
import logging
import re
from typing import Any


DEFAULT_SUPPLIER_ALIASES = {
    "TUJU GALAXY": [
        "tuju galaxy",
        "tuju galaksi",
        "tuju",
        "tg-",
    ],
}


def normalized_text(value: Any) -> str:
    return " ".join(str(value or "").lower().split())


def supplier_aliases_from_env(raw_value: str | None) -> dict[str, list[str]]:
    if not raw_value:
        return DEFAULT_SUPPLIER_ALIASES
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        logging.warning("SUPPLIER_ALIASES is not valid JSON. Using default supplier aliases.")
        return DEFAULT_SUPPLIER_ALIASES
    if not isinstance(parsed, dict):
        logging.warning("SUPPLIER_ALIASES must be a JSON object. Using default supplier aliases.")
        return DEFAULT_SUPPLIER_ALIASES

    aliases: dict[str, list[str]] = {}
    for supplier, values in parsed.items():
        if isinstance(values, str):
            aliases[str(supplier)] = [values]
        elif isinstance(values, list):
            aliases[str(supplier)] = [str(value) for value in values if str(value).strip()]
    return aliases or DEFAULT_SUPPLIER_ALIASES


def supplier_search_text(data: dict[str, Any]) -> str:
    parts = [
        data.get("supplier_name"),
        data.get("vendor_name"),
        data.get("company_name"),
        data.get("tax_invoice"),
        data.get("invoice_number"),
        data.get("delivery_order_no"),
        data.get("notes"),
    ]
    for document in (data.get("delivery_order_data"), data.get("invoice_data")):
        if isinstance(document, dict):
            parts.extend(
                [
                    document.get("supplier_name"),
                    document.get("vendor_name"),
                    document.get("company_name"),
                    document.get("tax_invoice"),
                    document.get("invoice_number"),
                    document.get("notes"),
                ]
            )
    return normalized_text(" ".join(str(part) for part in parts if part))


def detect_supplier_name(
    data: dict[str, Any],
    default_supplier: str,
    aliases: dict[str, list[str]] | None = None,
) -> str:
    explicit_supplier = str(data.get("supplier_name") or data.get("vendor_name") or "").strip()
    if explicit_supplier:
        return explicit_supplier

    alias_map = aliases or DEFAULT_SUPPLIER_ALIASES
    search_text = supplier_search_text(data)
    for supplier, supplier_aliases in alias_map.items():
        for alias in supplier_aliases:
            normalized_alias = normalized_text(alias)
            if not normalized_alias:
                continue
            if normalized_alias.endswith("-"):
                if re.search(rf"\b{re.escape(normalized_alias)}", search_text):
                    return supplier
            elif normalized_alias in search_text:
                return supplier
    return default_supplier
