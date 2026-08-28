"""
DocumentProfile — dataclasses, loader, validator, normalizer registry, and classifier scoring.

This module is the single source of truth for the DocumentProfile schema.
It is a standalone module with no dependency on invoice_bot.py.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, fields as dataclass_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────


@dataclass(frozen=True)
class ClassifierMarker:
    pattern: str
    type: str  # "literal" or "regex"
    weight: int
    role: str | None = None


@dataclass(frozen=True)
class ClassifierConfig:
    markers: tuple[ClassifierMarker, ...]
    match_threshold: int = 8
    ambiguity_margin: int = 3


@dataclass(frozen=True)
class QRConfig:
    expected: bool = False
    type: str | None = None
    use_for_classification: bool = False
    use_for_validation: bool = False


@dataclass(frozen=True)
class FieldDef:
    name: str
    type: str = "text"  # text, date, number, money, int, phone, email
    label_hints: tuple[str, ...] = ()
    required: bool = False
    pattern: str | None = None
    normalizers: tuple[str, ...] = ()
    extraction: str = "ai"  # ai, ocr_region, both
    crop_hint: tuple[float, float, float, float] | None = None
    input_format: str | None = None  # e.g. "DD.MM.YYYY" for date fields


@dataclass(frozen=True)
class TableColumn:
    field: str
    label_hints: tuple[str, ...] = ()
    type: str = "text"


@dataclass(frozen=True)
class LineItemTable:
    columns: tuple[TableColumn, ...]
    row_count_source: str = "ai_with_ocr_reconciliation"


@dataclass(frozen=True)
class ValidationRule:
    rule: str
    target: str | None = None
    operands: tuple[str, ...] = ()
    expr: str | None = None
    tolerance: float = 0.02


@dataclass(frozen=True)
class WorkflowConfig:
    po_prefix: str = "PO"
    procurement_folder_name: str = "UNKNOWN"
    register_supplier_name: str = "UNKNOWN"


@dataclass(frozen=True)
class DocumentProfile:
    """Complete profile for a document type."""

    # Identity
    id: str
    name: str
    supplier: str
    document_type: str  # invoice, delivery_order, receipt, purchase_order, etc.
    schema_version: int = SCHEMA_VERSION
    profile_version: int = 1
    created_at: str = ""
    updated_at: str = ""
    status: str = "active"  # active, deprecated, disabled

    # Classification
    classifier: ClassifierConfig | None = None

    # QR
    qr: QRConfig = field(default_factory=QRConfig)

    # Fields
    fields: tuple[FieldDef, ...] = ()

    # Line-item table
    line_item_table: LineItemTable | None = None

    # Validation
    validation_rules: tuple[ValidationRule, ...] = ()

    # Workflow
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)

    # AI prompt template
    ai_extraction_prompt: str = ""


# ──────────────────────────────────────────────
# Normalizer registry
# ──────────────────────────────────────────────

NormalizerFn = Callable[[Any], Any]

NORMALIZER_REGISTRY: dict[str, NormalizerFn] = {}


def register_normalizer(name: str) -> Callable[[NormalizerFn], NormalizerFn]:
    """Decorator to register a normalizer function."""
    def decorator(func: NormalizerFn) -> NormalizerFn:
        NORMALIZER_REGISTRY[name] = func
        return func
    return decorator


@register_normalizer("strip_whitespace")
def _strip_whitespace(value: Any) -> Any:
    if value is None:
        return None
    s = " ".join(str(value).strip().split())
    return s if s else None


@register_normalizer("ocr_letter_o_to_zero")
def _ocr_letter_o_to_zero(value: Any) -> Any:
    if value is None:
        return None
    return str(value).replace("O", "0").replace("o", "0")


@register_normalizer("ocr_letter_b_to_eight")
def _ocr_letter_b_to_eight(value: Any) -> Any:
    if value is None:
        return None
    return str(value).replace("B", "8").replace("b", "8")


@register_normalizer("normalize_invoice_prefix")
def _normalize_invoice_prefix(value: Any) -> Any:
    if value is None:
        return None
    s = str(value).upper().strip()
    s = re.sub(r"^1G(?=[-/])", "TG", s)
    s = re.sub(r"^T6(?=[-/])", "TG", s)
    return s if s else None


@register_normalizer("to_iso_date")
def _to_iso_date(value: Any) -> Any:
    """Convert DD.MM.YYYY -> YYYY-MM-DD. Pass through if already YYYY-MM-DD."""
    if value is None:
        return None
    s = str(value).strip()
    # Already ISO YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    m = re.match(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", s)
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


@register_normalizer("to_iso_date_dmy")
def _to_iso_date_dmy(value: Any) -> Any:
    """Convert DD/MM/YYYY -> YYYY-MM-DD"""
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    return None


@register_normalizer("parse_money")
def _parse_money(value: Any) -> Any:
    if value is None:
        return None
    s = str(value).strip()
    s = re.sub(r"[^0-9.,-]", "", s)
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


@register_normalizer("clean_contact")
def _clean_contact(value: Any) -> Any:
    if value is None:
        return None
    s = str(value)
    s = re.sub(r"\b(?:Fax|H/P|Tel|Phone|HP|HP:|ATTN|Attn)\s*[:.]?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+", " ", s).strip()
    return s if s else None


@register_normalizer("normalize_item_no")
def _normalize_item_no(value: Any) -> Any:
    if value is None:
        return None
    m = re.search(r"\d+", str(value))
    return m.group(0) if m else None


@register_normalizer("normalize_quantity_unit")
def _normalize_quantity_unit(value: Any) -> Any:
    if value is None:
        return None
    unit = str(value).strip().lower()
    aliases = {
        "pcs": "pcs", "pes": "pcs", "pts": "pcs", "pc": "pcs",
        "piece": "pcs", "pieces": "pcs", "ton": "ton", "tor": "ton",
        "toll": "roll",
    }
    return aliases.get(unit, unit[:20])


def apply_normalizers(value: Any, normalizer_names: tuple[str, ...]) -> Any:
    """Apply a chain of normalizers to a value."""
    result = value
    for name in normalizer_names:
        fn = NORMALIZER_REGISTRY.get(name)
        if fn is None:
            logger.warning("Unknown normalizer: %s", name)
            continue
        try:
            result = fn(result)
        except Exception as exc:
            logger.warning("Normalizer %s failed on %r: %s", name, value, exc)
    return result


# ──────────────────────────────────────────────
# Classifier scoring
# ──────────────────────────────────────────────


def score_profile_classifier(profile: DocumentProfile, text: str) -> int:
    """Score a single profile against OCR/AI text using its classifier markers.

    Returns the sum of weights of all matching markers.
    """
    if not profile.classifier:
        return 0

    score = 0
    for marker in profile.classifier.markers:
        if marker.type == "literal":
            if marker.pattern.lower() in text.lower():
                score += marker.weight
        elif marker.type == "regex":
            try:
                if re.search(marker.pattern, text, re.IGNORECASE):
                    score += marker.weight
            except re.error:
                logger.warning("Invalid regex in profile %s: %s", profile.id, marker.pattern)
    return score


def score_all_profiles(
    profiles: list[DocumentProfile],
    text: str,
) -> dict[str, int]:
    """Score all profiles against text. Returns dict of {profile_id: score}."""
    return {p.id: score_profile_classifier(p, text) for p in profiles}


def classify_best_profile(
    profiles: list[DocumentProfile],
    text: str,
) -> tuple[str | None, str, int, int]:
    """Determine the best-matching profile.

    Returns:
        (profile_id, status, score, runner_up_score)
        status is one of: "matched", "below_threshold", "ambiguous"
    """
    scores = score_all_profiles(profiles, text)

    # Filter to profiles with score >= threshold
    qualified = [
        (p.id, scores[p.id], p.classifier.match_threshold if p.classifier else 0)
        for p in profiles
        if p.classifier and scores[p.id] >= p.classifier.match_threshold
    ]

    if not qualified:
        # No profile met threshold
        best_id = max(scores, key=scores.get) if scores else None
        best_score = scores.get(best_id, 0) if best_id else 0
        return (best_id, "below_threshold", best_score, 0)

    # Sort by score descending
    qualified.sort(key=lambda x: x[1], reverse=True)

    top_id, top_score, _ = qualified[0]
    if len(qualified) == 1:
        return (top_id, "matched", top_score, 0)

    second_score = qualified[1][1]
    top_profile = next(p for p in profiles if p.id == top_id)
    margin = top_score - second_score

    if margin >= top_profile.classifier.ambiguity_margin:
        return (top_id, "matched", top_score, second_score)
    else:
        return (top_id, "ambiguous", top_score, second_score)


# ──────────────────────────────────────────────
# Validator
# ──────────────────────────────────────────────


class ProfileValidationError(ValueError):
    """Raised when a profile dict fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


VALID_DOCUMENT_TYPES = {
    "invoice", "delivery_order", "receipt", "purchase_order",
    "material_requisition", "quotation", "custom",
}
VALID_STATUSES = {"active", "deprecated", "disabled"}
VALID_MARKER_TYPES = {"literal", "regex"}
VALID_FIELD_TYPES = {"text", "date", "number", "money", "int", "phone", "email"}
VALID_EXTRACTION_MODES = {"ai", "ocr_region", "both"}
VALID_ROW_COUNT_SOURCES = {"ai", "ai_with_ocr_reconciliation"}
VALID_RULE_NAMES = {"line_totals_sum_to", "field_sum", "row_arithmetic"}
VALID_QR_TYPES = {"myinvois"}


def validate_profile(data: dict[str, Any], strict: bool = True) -> list[str]:
    """Validate a profile dict against the schema.

    Args:
        data: The parsed JSON dict.
        strict: If True, warn on missing optional fields. If False, only reject structural errors.

    Returns:
        List of error messages. Empty list = valid.
    """
    errors: list[str] = []
    _validate_identity(data, errors, strict)
    _validate_classifier(data, errors, strict)
    _validate_qr(data, errors, strict)
    _validate_fields(data, errors, strict)
    _validate_line_item_table(data, errors, strict)
    _validate_validation_rules(data, errors, strict)
    _validate_workflow(data, errors, strict)
    _validate_prompt(data, errors, strict)
    return errors


def _ensure(data: dict, key: str, typ: type, errors: list[str], path: str = "") -> None:
    if key not in data:
        errors.append(f"{path + '.' if path else ''}{key}: missing required field")
        return
    if not isinstance(data[key], typ):
        errors.append(f"{path + '.' if path else ''}{key}: expected {typ.__name__}, got {type(data[key]).__name__}")


def _validate_identity(data: dict, errors: list[str], strict: bool) -> None:
    _ensure(data, "id", str, errors)
    _ensure(data, "name", str, errors)
    _ensure(data, "supplier", str, errors)
    _ensure(data, "document_type", str, errors)
    _ensure(data, "schema_version", int, errors)
    _ensure(data, "profile_version", int, errors)
    _ensure(data, "status", str, errors)

    if "document_type" in data and data["document_type"] not in VALID_DOCUMENT_TYPES:
        errors.append(f"document_type: invalid value '{data['document_type']}'")
    if "status" in data and data["status"] not in VALID_STATUSES:
        errors.append(f"status: invalid value '{data['status']}'")
    if "schema_version" in data and data["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version: expected {SCHEMA_VERSION}, got {data['schema_version']}")


def _validate_classifier(data: dict, errors: list[str], strict: bool) -> None:
    classifier = data.get("classifier")
    if classifier is None:
        if strict:
            errors.append("classifier: missing (recommended)")
        return

    if not isinstance(classifier, dict):
        errors.append("classifier: expected object")
        return

    _ensure(classifier, "match_threshold", int, errors, "classifier")
    _ensure(classifier, "ambiguity_margin", int, errors, "classifier")

    markers = classifier.get("markers", [])
    if not isinstance(markers, list):
        errors.append("classifier.markers: expected array")
        return

    for i, marker in enumerate(markers):
        if not isinstance(marker, dict):
            errors.append(f"classifier.markers[{i}]: expected object")
            continue
        _ensure(marker, "pattern", str, errors, f"classifier.markers[{i}]")
        _ensure(marker, "type", str, errors, f"classifier.markers[{i}]")
        _ensure(marker, "weight", int, errors, f"classifier.markers[{i}]")
        if marker.get("type") not in VALID_MARKER_TYPES:
            errors.append(f"classifier.markers[{i}].type: invalid value '{marker.get('type')}'")


def _validate_qr(data: dict, errors: list[str], strict: bool) -> None:
    qr = data.get("qr")
    if qr is None:
        if strict:
            errors.append("qr: missing (recommended)")
        return

    if not isinstance(qr, dict):
        errors.append("qr: expected object")
        return

    _ensure(qr, "expected", bool, errors, "qr")
    if qr.get("type") is not None and qr["type"] not in VALID_QR_TYPES:
        errors.append(f"qr.type: invalid value '{qr['type']}'")


def _validate_fields(data: dict, errors: list[str], strict: bool) -> None:
    fields = data.get("fields")
    if fields is None:
        errors.append("fields: missing required field")
        return

    if not isinstance(fields, list):
        errors.append("fields: expected array")
        return

    seen_names: set[str] = set()
    for i, field in enumerate(fields):
        if not isinstance(field, dict):
            errors.append(f"fields[{i}]: expected object")
            continue
        _ensure(field, "name", str, errors, f"fields[{i}]")
        _ensure(field, "type", str, errors, f"fields[{i}]")

        name = field.get("name", "")
        if name in seen_names:
            errors.append(f"fields[{i}].name: duplicate '{name}'")
        seen_names.add(name)

        if field.get("type") not in VALID_FIELD_TYPES:
            errors.append(f"fields[{i}].type: invalid value '{field.get('type')}'")
        if field.get("extraction") not in VALID_EXTRACTION_MODES:
            errors.append(f"fields[{i}].extraction: invalid value '{field.get('extraction')}'")

        crop_hint = field.get("crop_hint")
        if crop_hint is not None:
            if not isinstance(crop_hint, list) or len(crop_hint) != 4:
                errors.append(f"fields[{i}].crop_hint: expected array of 4 numbers")
            elif not all(isinstance(v, (int, float)) for v in crop_hint):
                errors.append(f"fields[{i}].crop_hint: all values must be numbers")

        normalizers = field.get("normalizers", [])
        if isinstance(normalizers, list):
            for j, n in enumerate(normalizers):
                if n not in NORMALIZER_REGISTRY:
                    errors.append(f"fields[{i}].normalizers[{j}]: unknown normalizer '{n}'")


def _validate_line_item_table(data: dict, errors: list[str], strict: bool) -> None:
    table = data.get("line_item_table")
    if table is None:
        if strict:
            errors.append("line_item_table: missing (recommended)")
        return

    if not isinstance(table, dict):
        errors.append("line_item_table: expected object")
        return

    columns = table.get("columns", [])
    if not isinstance(columns, list):
        errors.append("line_item_table.columns: expected array")
        return

    for i, col in enumerate(columns):
        if not isinstance(col, dict):
            errors.append(f"line_item_table.columns[{i}]: expected object")
            continue
        _ensure(col, "field", str, errors, f"line_item_table.columns[{i}]")

    if table.get("row_count_source") not in VALID_ROW_COUNT_SOURCES:
        errors.append(f"line_item_table.row_count_source: invalid value '{table.get('row_count_source')}'")


def _validate_validation_rules(data: dict, errors: list[str], strict: bool) -> None:
    rules = data.get("validation_rules")
    if rules is None:
        return

    if not isinstance(rules, list):
        errors.append("validation_rules: expected array")
        return

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"validation_rules[{i}]: expected object")
            continue
        _ensure(rule, "rule", str, errors, f"validation_rules[{i}]")
        if rule.get("rule") not in VALID_RULE_NAMES:
            errors.append(f"validation_rules[{i}].rule: invalid value '{rule.get('rule')}'")


def _validate_workflow(data: dict, errors: list[str], strict: bool) -> None:
    workflow = data.get("workflow")
    if workflow is None:
        errors.append("workflow: missing required field")
        return

    if not isinstance(workflow, dict):
        errors.append("workflow: expected object")
        return

    _ensure(workflow, "po_prefix", str, errors, "workflow")
    _ensure(workflow, "procurement_folder_name", str, errors, "workflow")
    _ensure(workflow, "register_supplier_name", str, errors, "workflow")


def _validate_prompt(data: dict, errors: list[str], strict: bool) -> None:
    prompt = data.get("ai_extraction_prompt")
    if prompt is None:
        if strict:
            errors.append("ai_extraction_prompt: missing (recommended)")
        return
    if not isinstance(prompt, str):
        errors.append("ai_extraction_prompt: expected string")


# ──────────────────────────────────────────────
# Dict ↔ Dataclass conversion
# ──────────────────────────────────────────────


def _marker_from_dict(d: dict) -> ClassifierMarker:
    return ClassifierMarker(
        pattern=d["pattern"],
        type=d["type"],
        weight=d["weight"],
        role=d.get("role"),
    )


def _marker_to_dict(m: ClassifierMarker) -> dict:
    d: dict = {"pattern": m.pattern, "type": m.type, "weight": m.weight}
    if m.role:
        d["role"] = m.role
    return d


def _field_from_dict(d: dict) -> FieldDef:
    crop_hint = d.get("crop_hint")
    if crop_hint is not None:
        crop_hint = tuple(crop_hint)
    return FieldDef(
        name=d["name"],
        type=d.get("type", "text"),
        label_hints=tuple(d.get("label_hints", [])),
        required=d.get("required", False),
        pattern=d.get("pattern"),
        normalizers=tuple(d.get("normalizers", [])),
        extraction=d.get("extraction", "ai"),
        crop_hint=crop_hint,
        input_format=d.get("input_format"),
    )


def _field_to_dict(f: FieldDef) -> dict:
    d: dict = {"name": f.name, "type": f.type, "extraction": f.extraction}
    if f.label_hints:
        d["label_hints"] = list(f.label_hints)
    if f.required:
        d["required"] = True
    if f.pattern:
        d["pattern"] = f.pattern
    if f.normalizers:
        d["normalizers"] = list(f.normalizers)
    if f.crop_hint:
        d["crop_hint"] = list(f.crop_hint)
    if f.input_format:
        d["input_format"] = f.input_format
    return d


def profile_from_dict(data: dict[str, Any]) -> DocumentProfile:
    """Convert a validated dict to a DocumentProfile dataclass."""
    classifier = None
    if data.get("classifier"):
        c = data["classifier"]
        classifier = ClassifierConfig(
            markers=tuple(_marker_from_dict(m) for m in c.get("markers", [])),
            match_threshold=c.get("match_threshold", 8),
            ambiguity_margin=c.get("ambiguity_margin", 3),
        )

    qr = QRConfig(
        expected=data.get("qr", {}).get("expected", False),
        type=data.get("qr", {}).get("type"),
        use_for_classification=data.get("qr", {}).get("use_for_classification", False),
        use_for_validation=data.get("qr", {}).get("use_for_validation", False),
    )

    fields = tuple(_field_from_dict(f) for f in data.get("fields", []))

    table = None
    if data.get("line_item_table"):
        t = data["line_item_table"]
        table = LineItemTable(
            columns=tuple(
                TableColumn(
                    field=c["field"],
                    label_hints=tuple(c.get("label_hints", [])),
                    type=c.get("type", "text"),
                )
                for c in t.get("columns", [])
            ),
            row_count_source=t.get("row_count_source", "ai_with_ocr_reconciliation"),
        )

    validation_rules = tuple(
        ValidationRule(
            rule=r["rule"],
            target=r.get("target"),
            operands=tuple(r.get("operands", [])),
            expr=r.get("expr"),
            tolerance=r.get("tolerance", 0.02),
        )
        for r in data.get("validation_rules", [])
    )

    workflow = WorkflowConfig(
        po_prefix=data.get("workflow", {}).get("po_prefix", "PO"),
        procurement_folder_name=data.get("workflow", {}).get("procurement_folder_name", "UNKNOWN"),
        register_supplier_name=data.get("workflow", {}).get("register_supplier_name", "UNKNOWN"),
    )

    return DocumentProfile(
        id=data["id"],
        name=data["name"],
        supplier=data["supplier"],
        document_type=data["document_type"],
        schema_version=data.get("schema_version", SCHEMA_VERSION),
        profile_version=data.get("profile_version", 1),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        status=data.get("status", "active"),
        classifier=classifier,
        qr=qr,
        fields=fields,
        line_item_table=table,
        validation_rules=validation_rules,
        workflow=workflow,
        ai_extraction_prompt=data.get("ai_extraction_prompt", ""),
    )


def profile_to_dict(profile: DocumentProfile) -> dict[str, Any]:
    """Convert a DocumentProfile dataclass to a dict (for JSON serialization)."""
    d: dict[str, Any] = {
        "id": profile.id,
        "name": profile.name,
        "supplier": profile.supplier,
        "document_type": profile.document_type,
        "schema_version": profile.schema_version,
        "profile_version": profile.profile_version,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
        "status": profile.status,
    }

    if profile.classifier:
        d["classifier"] = {
            "markers": [_marker_to_dict(m) for m in profile.classifier.markers],
            "match_threshold": profile.classifier.match_threshold,
            "ambiguity_margin": profile.classifier.ambiguity_margin,
        }

    d["qr"] = {
        "expected": profile.qr.expected,
        "type": profile.qr.type,
        "use_for_classification": profile.qr.use_for_classification,
        "use_for_validation": profile.qr.use_for_validation,
    }

    d["fields"] = [_field_to_dict(f) for f in profile.fields]

    if profile.line_item_table:
        d["line_item_table"] = {
            "columns": [
                {
                    "field": c.field,
                    "label_hints": list(c.label_hints),
                    "type": c.type,
                }
                for c in profile.line_item_table.columns
            ],
            "row_count_source": profile.line_item_table.row_count_source,
        }

    if profile.validation_rules:
        d["validation_rules"] = [
            {
                "rule": r.rule,
                "target": r.target,
                "operands": list(r.operands),
                "expr": r.expr,
                "tolerance": r.tolerance,
            }
            for r in profile.validation_rules
        ]

    d["workflow"] = {
        "po_prefix": profile.workflow.po_prefix,
        "procurement_folder_name": profile.workflow.procurement_folder_name,
        "register_supplier_name": profile.workflow.register_supplier_name,
    }

    if profile.ai_extraction_prompt:
        d["ai_extraction_prompt"] = profile.ai_extraction_prompt

    return d


# ──────────────────────────────────────────────
# Loader / Saver
# ──────────────────────────────────────────────

DEFAULT_PROFILES_DIR = Path(__file__).resolve().parent / "data" / "document_profiles"


def load_profile(path: Path) -> DocumentProfile | None:
    """Load a single profile from a JSON file, validate, return dataclass."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to load profile %s: %s", path, exc)
        return None

    errors = validate_profile(data, strict=False)
    if errors:
        logger.error("Profile %s validation errors: %s", path, errors)
        return None

    try:
        return profile_from_dict(data)
    except (KeyError, TypeError) as exc:
        logger.error("Failed to parse profile %s: %s", path, exc)
        return None


def get_default_builtin_profiles() -> list[DocumentProfile]:
    return [
        DocumentProfile(
            id="tuju_galaxy_invoice",
            name="TUJU GALAXY - Tax Invoice",
            supplier="TUJU GALAXY",
            document_type="invoice",
            classifier=ClassifierConfig(
                markers=(
                    ClassifierMarker(pattern="TUJU GALAXY", type="literal", weight=5, role="supplier"),
                    ClassifierMarker(pattern="TUJU GALAKSI", type="literal", weight=5, role="supplier"),
                    ClassifierMarker(pattern="Blackfox", type="literal", weight=3, role="supplier"),
                    ClassifierMarker(pattern=r"TG-[A-Z0-9]{4,}", type="regex", weight=3, role="docnumber"),
                    ClassifierMarker(pattern=r"tax\s*invoice", type="regex", weight=5, role="doctype"),
                    ClassifierMarker(pattern=r"delivery\s*order", type="regex", weight=-5, role="doctype_exclusion"),
                ),
                match_threshold=6,
                ambiguity_margin=3,
            ),
        ),
        DocumentProfile(
            id="tuju_galaxy_delivery_order",
            name="TUJU GALAXY - Delivery Order",
            supplier="TUJU GALAXY",
            document_type="delivery_order",
            classifier=ClassifierConfig(
                markers=(
                    ClassifierMarker(pattern="TUJU GALAXY", type="literal", weight=5, role="supplier"),
                    ClassifierMarker(pattern="TUJU GALAKSI", type="literal", weight=5, role="supplier"),
                    ClassifierMarker(pattern="Blackfox", type="literal", weight=3, role="supplier"),
                    ClassifierMarker(pattern=r"TG-[A-Z0-9]{4,}", type="regex", weight=3, role="docnumber"),
                    ClassifierMarker(pattern=r"delivery\s*order", type="regex", weight=5, role="doctype"),
                    ClassifierMarker(pattern=r"tax\s*invoice", type="regex", weight=-5, role="doctype_exclusion"),
                ),
                match_threshold=6,
                ambiguity_margin=3,
            ),
        ),
    ]


def load_profiles(profiles_dir: Path | None = None) -> list[DocumentProfile]:
    """Load all active profiles from the profiles directory.

    Loads <id>.json files (not old versions like <id>.v<N>.json).
    Returns only profiles with status == "active".
    """
    if profiles_dir is None:
        profiles_dir = DEFAULT_PROFILES_DIR

    if not profiles_dir.exists():
        logger.warning("Profiles directory not found: %s", profiles_dir)
        return []

    profiles: list[DocumentProfile] = []
    for path in sorted(profiles_dir.iterdir()):
        if not path.is_file() or path.suffix != ".json":
            continue
        if path.name == "index.json":
            continue
        # Skip old versions: <id>.v<N>.json
        if re.search(r"\.v\d+\.json$", path.name):
            continue

        profile = load_profile(path)
        if profile is not None and profile.status == "active":
            profiles.append(profile)

    logger.info("Loaded %d active profiles from %s", len(profiles), profiles_dir)
    return profiles


def save_profile(profile: DocumentProfile, profiles_dir: Path | None = None) -> Path:
    """Save a profile to disk. Archives old version if exists."""
    if profiles_dir is None:
        profiles_dir = DEFAULT_PROFILES_DIR

    profiles_dir.mkdir(parents=True, exist_ok=True)

    # Archive old version
    new_path = profiles_dir / f"{profile.id}.json"
    if new_path.exists():
        old_profile = load_profile(new_path)
        if old_profile and old_profile.profile_version != profile.profile_version:
            archive_name = f"{profile.id}.v{old_profile.profile_version}.json"
            archive_path = profiles_dir / archive_name
            new_path.rename(archive_path)
            logger.info("Archived old profile to %s", archive_path)

    # Write new
    data = profile_to_dict(profile)
    with open(new_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info("Saved profile %s v%d to %s", profile.id, profile.profile_version, new_path)
    rebuild_index(profiles_dir)
    return new_path


def rebuild_index(profiles_dir: Path | None = None) -> None:
    """Rebuild index.json from all active profiles on disk."""
    if profiles_dir is None:
        profiles_dir = DEFAULT_PROFILES_DIR

    profiles = load_profiles(profiles_dir)
    entries = [
        {
            "id": p.id,
            "name": p.name,
            "supplier": p.supplier,
            "document_type": p.document_type,
            "profile_version": p.profile_version,
            "status": p.status,
        }
        for p in profiles
    ]

    index_path = profiles_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"profiles": entries}, f, indent=2, ensure_ascii=False)

    logger.info("Rebuilt index.json with %d profiles", len(entries))


def disable_profile(profile_id: str, profiles_dir: Path | None = None) -> bool:
    """Soft-disable a profile by setting status to disabled."""
    if profiles_dir is None:
        profiles_dir = DEFAULT_PROFILES_DIR

    path = profiles_dir / f"{profile_id}.json"
    if not path.exists():
        logger.error("Profile %s not found", profile_id)
        return False

    profile = load_profile(path)
    if profile is None:
        return False

    updated = profile_from_dict({**profile_to_dict(profile), "status": "disabled"})
    save_profile(updated, profiles_dir)
    return True


def remove_profile(profile_id: str, profiles_dir: Path | None = None) -> bool:
    """Move a profile to the removed/ subdirectory."""
    if profiles_dir is None:
        profiles_dir = DEFAULT_PROFILES_DIR

    src = profiles_dir / f"{profile_id}.json"
    if not src.exists():
        logger.error("Profile %s not found", profile_id)
        return False

    removed_dir = profiles_dir / "removed"
    removed_dir.mkdir(exist_ok=True)
    dst = removed_dir / f"{profile_id}.json"
    src.rename(dst)
    logger.info("Moved profile %s to %s", profile_id, dst)
    rebuild_index(profiles_dir)
    return True