# DocumentProfile Schema

> Schema version 1 — defines the JSON structure for per-document-type extraction profiles.

## Overview

A `DocumentProfile` tells the bot how to classify, extract, validate, and route a specific document type (e.g. "TUJU GALAXY Tax Invoice", "ABC Supplier Delivery Order"). Profiles are plain JSON files stored in `data/document_profiles/` and loaded at startup.

---

## 1. Identity & Versioning

```json
{
  "id": "tuju_galaxy_invoice",
  "name": "TUJU GALAXY - Tax Invoice",
  "supplier": "TUJU GALAXY",
  "document_type": "invoice",
  "schema_version": 1,
  "profile_version": 3,
  "created_at": "2026-07-08T00:00:00Z",
  "updated_at": "2026-07-08T00:00:00Z",
  "status": "active"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | yes | Unique kebab-case identifier. Used as filename stem (`<id>.json`). |
| `name` | string | yes | Human-readable label. |
| `supplier` | string | yes | Supplier/company name for routing and procurement folders. |
| `document_type` | string | yes | `"invoice"`, `"delivery_order"`, `"receipt"`, `"purchase_order"`, `"material_requisition"`, or `"custom"`. |
| `schema_version` | int | yes | Must match `document_profiles.SCHEMA_VERSION`. |
| `profile_version` | int | yes | Incremented on each edit. Old versions kept as `<id>.v<N>.json`. |
| `created_at` | ISO-8601 | yes | Creation timestamp. |
| `updated_at` | ISO-8601 | yes | Last modification timestamp. |
| `status` | string | yes | `"active"`, `"deprecated"`, or `"disabled"`. Loader only loads `active`. |

**Versioning rule**: When a profile is edited, the old file is renamed to `<id>.v<old_version>.json` and the new file gets `profile_version = old_version + 1`. Only `status: "active"` profiles are loaded.

---

## 2. Weighted Classifier

```json
"classifier": {
  "markers": [
    {"pattern": "TUJU GALAXY", "type": "literal", "weight": 5, "role": "supplier"},
    {"pattern": "SST No[.:]?\\s*W10-\\d+", "type": "regex", "weight": 5, "role": "supplier"},
    {"pattern": "TG-[A-Z0-9]{5,}", "type": "regex", "weight": 3, "role": "docnumber"},
    {"pattern": "tax invoice", "type": "literal", "weight": 1, "role": "doctype"},
    {"pattern": "delivery order", "type": "literal", "weight": -3, "role": "doctype_exclusion"}
  ],
  "match_threshold": 8,
  "ambiguity_margin": 3
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `markers` | array | yes | List of marker objects. |
| `markers[].pattern` | string | yes | Literal string or regex pattern to search OCR/AI text. |
| `markers[].type` | string | yes | `"literal"` (case-insensitive substring match) or `"regex"` (re.search). |
| `markers[].weight` | int | yes | Contribution to score. Negative weights allow exclusion (e.g. "delivery order" excludes invoice profile). |
| `markers[].role` | string | optional | Semantic role: `"supplier"`, `"docnumber"`, `"doctype"`, `"doctype_exclusion"`, `"custom"`. For logging/analysis. |
| `match_threshold` | int | yes | Minimum total score for this profile to be considered a match. |
| `ambiguity_margin` | int | yes | Winner must beat runner-up by ≥ this margin. Otherwise → AMBIGUOUS → AI fallback. |

**Scoring algorithm**:
```
score = sum(marker.weight for marker in markers if marker matches text)
```
- If `score < match_threshold` → no match.
- If multiple profiles score ≥ threshold, the top scorer wins **only if** `score_top - score_second ≥ ambiguity_margin`.
- Otherwise → `"AMBIGUOUS"` → invoke AI classifier fallback.

**Negative weight example**: TUJU invoices and TUJU delivery orders share many markers (`TG-` prefix, `TUJU GALAXY`). The DO profile has `"invoice"` with weight `-3` to lower its score when the text says "tax invoice". The invoice profile similarly has `"delivery order"` with weight `-3`.

---

## 3. MyInvois QR Block

```json
"qr": {
  "expected": false,
  "type": null,
  "use_for_classification": false,
  "use_for_validation": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `expected` | bool | yes | Whether this document type should carry a QR code. |
| `type` | string | nullable | `"myinvois"` for LHDN e-Invoice QR, or `null`/absent. |
| `use_for_classification` | bool | yes | If true, a successful QR decode identifying the supplier overrides text-based classifier. |
| `use_for_validation` | bool | yes | If true, QR-decoded values (supplier TIN, invoice number, total) are compared against extracted fields. |

When `qr.type == "myinvois"`, the QR payload is expected to follow the LHDN MyInvois format. The decoded supplier registration number (TIN) is used as the highest-weight classifier signal.

---

## 4. Fields

```json
"fields": [
  {
    "name": "invoice_number",
    "label_hints": ["Tax Invoice", "Invoice No", "Invoice Number"],
    "type": "text",
    "required": true,
    "pattern": "TG-[A-Z0-9]+",
    "normalizers": ["ocr_letter_o_to_zero", "strip_whitespace"],
    "extraction": "ai",
    "crop_hint": null
  },
  {
    "name": "invoice_date",
    "label_hints": ["Date", "Invoice Date", "DO Date"],
    "type": "date",
    "required": true,
    "input_format": "DD.MM.YYYY",
    "normalizers": ["to_iso_date"],
    "extraction": "ai",
    "crop_hint": null
  },
  {
    "name": "supplier_name",
    "label_hints": ["Supplier", "Vendor", "Company"],
    "type": "text",
    "required": false,
    "pattern": null,
    "normalizers": ["strip_whitespace"],
    "extraction": "ai",
    "crop_hint": null
  },
  {
    "name": "contact_person",
    "label_hints": ["Contact Person", "Attn", "Person to Contact"],
    "type": "text",
    "required": false,
    "pattern": null,
    "normalizers": ["strip_whitespace", "clean_contact"],
    "extraction": "ai",
    "crop_hint": [0.07, 0.28, 0.72, 0.35]
  },
  {
    "name": "document_total",
    "label_hints": ["Total", "Grand Total", "Total Payable", "Amount Due"],
    "type": "money",
    "required": false,
    "pattern": null,
    "normalizers": ["parse_money"],
    "extraction": "ai",
    "crop_hint": null
  }
]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Machine field name (snake_case). Used as key in extraction output. |
| `label_hints` | string[] | optional | Possible label text adjacent to the field value. Used for AI prompt and OCR verification. |
| `type` | string | yes | One of: `"text"`, `"date"`, `"number"`, `"money"`, `"int"`, `"phone"`, `"email"`. |
| `required` | bool | yes | If true, extraction with this field null triggers a review warning. |
| `pattern` | string | nullable | Optional regex pattern to validate the extracted value. |
| `normalizers` | string[] | optional | Ordered list of named normalizer functions to apply. See Normalizer Registry below. |
| `extraction` | string | yes | `"ai"` (default — AI vision extracts), `"ocr_region"` (OCR-only), or `"both"` (AI extracts, OCR verifies). |
| `crop_hint` | array | nullable | Optional relative box `[x1, y1, x2, y2]` (0.0–1.0) for OCR verification. NEVER used as sole extraction source. |

### Normalizer Registry

Named functions registered in `document_profiles.py`:

| Name | Description | Input | Output |
|---|---|---|---|
| `strip_whitespace` | Trim and collapse whitespace | string | string |
| `ocr_letter_o_to_zero` | Replace `O`/`o` with `0` in alphanumeric codes | string | string |
| `ocr_letter_b_to_eight` | Replace `B`/`b` with `8` in alphanumeric codes | string | string |
| `normalize_invoice_prefix` | Fix `1G`→`TG`, `T6`→`TG` | string | string |
| `to_iso_date` | Convert `DD.MM.YYYY` to `YYYY-MM-DD` | string | string |
| `to_iso_date_dmy` | Convert `DD/MM/YYYY` to `YYYY-MM-DD` | string | string |
| `parse_money` | Strip `RM `, commas, parse float | string | float |
| `clean_contact` | Remove `Fax:`, `H/P:`, `Tel:` labels from contact field | string | string |
| `normalize_item_no` | Extract leading digits from item number | string | string |
| `normalize_quantity_unit` | Standardise unit aliases (pcs, pc→pcs; ton, tor→ton) | string | string |

---

## 5. Line-Item Table

```json
"line_item_table": {
  "columns": [
    {"field": "item_no", "label_hints": ["No", "Item No", "#"], "type": "int"},
    {"field": "description", "label_hints": ["Product Description", "Description", "Item Description"], "type": "text"},
    {"field": "quantity", "label_hints": ["Quantity", "Qty", "QTY"], "type": "number"},
    {"field": "quantity_unit", "label_hints": ["Unit", "UOM", "UM"], "type": "text"},
    {"field": "unit_price", "label_hints": ["Unit Price", "Price", "Rate"], "type": "money"},
    {"field": "line_total", "label_hints": ["Amount", "Total", "Line Total"], "type": "money"}
  ],
  "row_count_source": "ai_with_ocr_reconciliation"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `columns` | array | yes | Ordered list of column definitions. |
| `columns[].field` | string | yes | Field name matching one in `fields[]` for single-value fields, or an in-table field name. |
| `columns[].label_hints` | string[] | optional | Table header text variations. |
| `columns[].type` | string | yes | Same types as field definitions. |
| `row_count_source` | string | yes | `"ai"` (rely on AI), `"ai_with_ocr_reconciliation"` (existing pattern: compare AI rows vs OCR-visible rows, request reconciliation if mismatch). |

**Reconciliation algorithm** (replicates existing `extraction_needs_reconciliation()` logic, generalised):
1. Run OCR on the full page or table crop region.
2. Detect table header by matching `label_hints` from any column.
3. Count visible row numbers (1, 2, 3...) in the OCR text below the header.
4. Compare against AI-extracted row count.
5. If AI count < OCR count (or missing row numbers), request AI reconciliation pass.

---

## 6. Cross-Field Validation Rules

```json
"validation_rules": [
  {"rule": "line_totals_sum_to", "target": "subtotal", "tolerance": 0.02},
  {"rule": "field_sum", "operands": ["subtotal", "sst_amount"], "target": "grand_total", "tolerance": 0.02},
  {"rule": "row_arithmetic", "expr": "quantity * unit_price == line_total", "tolerance": 0.02}
]
```

| Field | Type | Required | Description |
|---|---|---|---|
| `rule` | string | yes | Rule name. Supported: `"line_totals_sum_to"`, `"field_sum"`, `"row_arithmetic"`. |
| `target` | string | conditional | Target field name (for sum rules). |
| `operands` | string[] | conditional | Source field names (for sum rules). |
| `expr` | string | conditional | Arithmetic expression (for row_arithmetic). |
| `tolerance` | number | yes | Acceptable absolute difference. |

**Behaviour**: Validation failures do NOT reject the document. They produce `⚠️` warnings in the Telegram reply and set `needs_review = true` in the register entry.

### Supported Rules

| Rule | Description |
|---|---|
| `line_totals_sum_to` | Sum of `line_total` across all line items should equal a named field (e.g. `subtotal`). |
| `field_sum` | Sum of operand fields should equal target field (e.g. `subtotal + sst_amount == grand_total`). |
| `row_arithmetic` | For each row, check `quantity * unit_price == line_total` within tolerance. |

---

## 7. Workflow Routing

```json
"workflow": {
  "po_prefix": "BFE PO TUJU",
  "procurement_folder_name": "TUJU GALAXY",
  "register_supplier_name": "TUJU GALAXY"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `po_prefix` | string | yes | Prefix for PO workbook filenames (e.g. `"BFE PO TUJU"` → `"BFE PO TUJU JULY 0001.xlsx"`). |
| `procurement_folder_name` | string | yes | Subfolder name under `PROCUREMENT/` for this supplier. |
| `register_supplier_name` | string | yes | Value written to `supplier_name` column in `invoice_register.csv`. |

---

## 8. AI Extraction Prompt Template

```json
"ai_extraction_prompt": "You extract {supplier} {document_type} data from document images.\nReturn only valid JSON matching this schema:\n{schema_block}\n{field_instructions}\n\nTable columns:\n{table_columns}\n\nRules:\n{rules}"
```

| Field | Type | Required | Description |
|---|---|---|---|
| `ai_extraction_prompt` | string | yes | Template string with placeholders. Loaded at runtime and rendered with profile data. |

**Available placeholders**:
- `{supplier}` — profile's supplier name
- `{document_type}` — profile's document_type
- `{schema_block}` — JSON schema block generated from field definitions
- `{field_instructions}` — per-field extraction instructions (label hints, required/optional, special rules)
- `{table_columns}` — line-item column headers with field names
- `{rules}` — extraction rules from the profile

**Fallback**: When no profile matches, a generic prompt is used that asks the AI to identify document type, supplier, and all visible fields from scratch.

---

## 9. Complete Example

```json
{
  "id": "tuju_galaxy_invoice",
  "name": "TUJU GALAXY - Tax Invoice",
  "supplier": "TUJU GALAXY",
  "document_type": "invoice",
  "schema_version": 1,
  "profile_version": 1,
  "created_at": "2026-07-08T00:00:00Z",
  "updated_at": "2026-07-08T00:00:00Z",
  "status": "active",

  "classifier": {
    "markers": [
      {"pattern": "TUJU GALAXY", "type": "literal", "weight": 5, "role": "supplier"},
      {"pattern": "TUJU GALAKSI", "type": "literal", "weight": 5, "role": "supplier"},
      {"pattern": "SST No[.:]?\\s*W10-\\d+", "type": "regex", "weight": 5, "role": "supplier"},
      {"pattern": "TG-[A-Z0-9]{5,}", "type": "regex", "weight": 3, "role": "docnumber"},
      {"pattern": "tax invoice", "type": "literal", "weight": 1, "role": "doctype"},
      {"pattern": "taxinvoice", "type": "literal", "weight": 1, "role": "doctype"},
      {"pattern": "invoice", "type": "literal", "weight": 1, "role": "doctype"},
      {"pattern": "delivery order", "type": "literal", "weight": -3, "role": "doctype_exclusion"}
    ],
    "match_threshold": 8,
    "ambiguity_margin": 3
  },

  "qr": {
    "expected": false,
    "type": null,
    "use_for_classification": false,
    "use_for_validation": false
  },

  "fields": [
    {
      "name": "invoice_number",
      "label_hints": ["Tax Invoice", "Invoice No", "Invoice Number"],
      "type": "text",
      "required": true,
      "pattern": "TG-[A-Z0-9]+",
      "normalizers": ["ocr_letter_o_to_zero", "ocr_letter_b_to_eight", "normalize_invoice_prefix", "strip_whitespace"],
      "extraction": "ai",
      "crop_hint": null
    },
    {
      "name": "invoice_date",
      "label_hints": ["Date", "Invoice Date"],
      "type": "date",
      "required": true,
      "input_format": "DD.MM.YYYY",
      "normalizers": ["to_iso_date"],
      "extraction": "ai",
      "crop_hint": null
    },
    {
      "name": "supplier_name",
      "label_hints": ["Supplier", "Vendor", "Company"],
      "type": "text",
      "required": false,
      "pattern": null,
      "normalizers": ["strip_whitespace"],
      "extraction": "ai",
      "crop_hint": null
    },
    {
      "name": "contact_person",
      "label_hints": ["Contact Person", "Attn", "Person to Contact"],
      "type": "text",
      "required": false,
      "pattern": null,
      "normalizers": ["strip_whitespace", "clean_contact"],
      "extraction": "ai",
      "crop_hint": [0.07, 0.28, 0.72, 0.35]
    },
    {
      "name": "document_total",
      "label_hints": ["Total", "Grand Total", "Total Payable", "Amount Due"],
      "type": "money",
      "required": false,
      "pattern": null,
      "normalizers": ["parse_money"],
      "extraction": "ai",
      "crop_hint": null
    }
  ],

  "line_item_table": {
    "columns": [
      {"field": "item_no", "label_hints": ["No", "Item No"], "type": "int"},
      {"field": "description", "label_hints": ["Product Description", "Description"], "type": "text"},
      {"field": "quantity", "label_hints": ["Quantity", "Qty"], "type": "number"},
      {"field": "quantity_unit", "label_hints": ["Unit", "UOM"], "type": "text"},
      {"field": "unit_price", "label_hints": ["Unit Price", "Price"], "type": "money"},
      {"field": "line_total", "label_hints": ["Amount", "Total"], "type": "money"}
    ],
    "row_count_source": "ai_with_ocr_reconciliation"
  },

  "validation_rules": [
    {"rule": "line_totals_sum_to", "target": "document_total", "tolerance": 0.02},
    {"rule": "row_arithmetic", "expr": "quantity * unit_price == line_total", "tolerance": 0.02}
  ],

  "workflow": {
    "po_prefix": "BFE PO TUJU",
    "procurement_folder_name": "TUJU GALAXY",
    "register_supplier_name": "TUJU GALAXY"
  },

  "ai_extraction_prompt": "You extract {supplier} {document_type} data from document images.\nReturn only valid JSON matching this schema:\n{schema_block}\n\n{field_instructions}\n\nTable columns:\n{table_columns}\n\nRules:\n- Do not invent document numbers, dates, contact details, item details, prices, or amounts that are not visible.\n- If a critical field is unclear, cropped out, upside-down, or only inferred from context, return null for that field and explain the uncertainty in notes.\n- Never use a phone number, fax number, address number, quantity, amount, or line-item number as the document number or date.\n- If a row is partially unclear, still include it with the visible fields and mention the uncertainty in notes.\n{reconciliation_instructions}"
}
```

---

## 10. File Layout

```
data/document_profiles/
├── index.json
├── tuju_galaxy_invoice.json
├── tuju_galaxy_delivery_order.json
├── tuju_galaxy_invoice.v2.json      ← old version, ignored by loader
└── removed/                          ← disabled profiles go here
```

### `index.json`

```json
{
  "profiles": [
    {
      "id": "tuju_galaxy_invoice",
      "name": "TUJU GALAXY - Tax Invoice",
      "supplier": "TUJU GALAXY",
      "document_type": "invoice",
      "profile_version": 1,
      "status": "active"
    },
    {
      "id": "tuju_galaxy_delivery_order",
      "name": "TUJU GALAXY - Delivery Order",
      "supplier": "TUJU GALAXY",
      "document_type": "delivery_order",
      "profile_version": 1,
      "status": "active"
    }
  ]
}
```

The index is a lightweight registry for fast classifier iteration without loading all profile JSONs. It is regenerated by `rebuild_index()` whenever profiles are added/removed.