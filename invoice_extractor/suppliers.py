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
    "WALIHIN PETROLEUM": [
        "walihin petroleum",
        "walihin",
        "petroleum",
    ],
}

KNOWN_SUPPLIER_PROFILES = {
    "WALIHIN PETROLEUM": {
        "category": "TECH",
        "display_name": "WALIHIN PETROLEUM SDN BHD",
        "address_line1": "Lot 7, GSL 3104, Hakka Avenue Estate",
        "address_line2": "5th Miles Penrissen Road, 93250 Kuching, Sarawak.",
        "tel_fax": "TEL/FAX : 082-575987 / Office H/P : 016-8865086",
        "email": "Email : walihinpetroleum@yahoo.com",
        "bank_account": "No Acc : 561118064592 (Maybank)",
        "default_contact": "Lukman 018-9414868",
        "aliases": ["walihin petroleum", "walihin", "petroleum"],
    },
    "TUJU GALAXY": {
        "category": "TUJU",
        "display_name": "TUJU GALAKSI SDN BHD",
        "address_line1": "SL.20,1st Floor, Block 16, KCLD, Galacity,",
        "address_line2": "93350 Kuching Sarawak",
        "tel_fax": "TEL : 082-265809 / 082-265810",
        "email": "",
        "bank_account": "No. Account : 2233006809(UOB)",
        "default_contact": "Zarin 019-9396812",
        "aliases": ["tuju galaxy", "tuju galaksi", "tuju", "tg-"],
    },
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
        data.get("quotation_number"),
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
                    document.get("delivery_order_no"),
                    document.get("quotation_number"),
                    document.get("notes"),
                ]
            )
    return normalized_text(" ".join(str(part) for part in parts if part))


def detect_supplier_name(
    data: dict[str, Any],
    default_supplier: str = "TUJU GALAXY",
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


def detect_supplier_profile(
    data: dict[str, Any],
    default_supplier: str = "TUJU GALAXY",
    aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    supplier_name = detect_supplier_name(data, default_supplier, aliases)

    # 1. Match against known profiles by key
    if supplier_name in KNOWN_SUPPLIER_PROFILES:
        res = dict(KNOWN_SUPPLIER_PROFILES[supplier_name])
        if data.get("supplier_phone"):
            res["tel_fax"] = f"TEL/FAX : {data['supplier_phone']}"
        if data.get("supplier_email"):
            res["email"] = f"Email : {data['supplier_email']}"
        return res

    for key, prof in KNOWN_SUPPLIER_PROFILES.items():
        if prof.get("display_name", "").lower() == supplier_name.lower():
            res = dict(prof)
            return res
        for alias in prof.get("aliases", []):
            if normalized_text(alias) in normalized_text(supplier_name):
                res = dict(prof)
                return res

    # 2. Dynamic generic supplier extraction
    clean_name = re.sub(r"\s*\(\d+-[A-Z]\)", "", supplier_name).strip()
    category = re.sub(r"[^A-Z0-9]+", "", clean_name.split()[0].upper()) if clean_name else "PO"

    raw_address = str(data.get("supplier_address") or "").strip()
    addr_parts = [p.strip() for p in raw_address.split(",") if p.strip()]
    addr1 = ", ".join(addr_parts[:2]) if len(addr_parts) >= 2 else raw_address
    addr2 = ", ".join(addr_parts[2:]) if len(addr_parts) > 2 else ""

    phone = str(data.get("supplier_phone") or "").strip()
    email = str(data.get("supplier_email") or "").strip()
    bank = str(data.get("supplier_bank_account") or "").strip()

    return {
        "category": category or "PO",
        "display_name": clean_name or default_supplier,
        "address_line1": addr1,
        "address_line2": addr2,
        "tel_fax": f"TEL : {phone}" if phone and not phone.lower().startswith("tel") else phone,
        "email": f"Email : {email}" if email and not email.lower().startswith("email") else email,
        "bank_account": f"No Acc : {bank}" if bank and not bank.lower().startswith("no") else bank,
        "default_contact": str(data.get("contact_person") or ""),
    }
