"""
Profile management commands for the Telegram invoice extractor bot.

Handles /list_profiles, /profile_info, /disable_profile, /enable_profile,
/remove_profile, /test_profile, /export_profiles, /import_profiles.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from document_profiles import (
    load_profiles,
    load_profile,
    profile_to_dict,
    profile_from_dict,
    save_profile,
    disable_profile as dp_disable,
    remove_profile as dp_remove,
    rebuild_index,
    validate_profile,
    classify_best_profile,
    score_profile_classifier,
)

logger = logging.getLogger(__name__)

# ── Test state key for /test_profile ──────────────────────────────────
TEST_PROFILE_KEY = "test_profile"


def get_test_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    state = context.chat_data.get(TEST_PROFILE_KEY)
    return state if isinstance(state, dict) else None


def clear_test_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data.pop(TEST_PROFILE_KEY, None)


# ── Confidence tracking ───────────────────────────────────────────────

CONFIDENCE_TRACKING_DIR = Path(__file__).resolve().parent / "data" / "profile_confidence"
CONFIDENCE_ROLLING_WINDOW = 10
DRIFT_ALERT_THRESHOLD = 0.6  # 60%


def _confidence_tracking_path(profile_id: str) -> Path:
    CONFIDENCE_TRACKING_DIR.mkdir(parents=True, exist_ok=True)
    return CONFIDENCE_TRACKING_DIR / f"{profile_id}.jsonl"


def record_extraction_outcome(profile_id: str, passed_validation: bool) -> None:
    """Record an extraction outcome for a profile."""
    import json
    import time
    path = _confidence_tracking_path(profile_id)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"timestamp": time.time(), "passed": passed_validation}) + "\n")


def get_profile_confidence(profile_id: str) -> dict[str, Any]:
    """Get the rolling confidence stats for a profile."""
    path = _confidence_tracking_path(profile_id)
    if not path.exists():
        return {"total": 0, "passed": 0, "rate": 1.0, "drift_alert": False, "recent": []}

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Only the last N records
    recent = records[-CONFIDENCE_ROLLING_WINDOW:]
    total = len(recent)
    passed = sum(1 for r in recent if r.get("passed"))
    rate = passed / total if total > 0 else 1.0

    return {
        "total": len(records),
        "recent_count": total,
        "passed": passed,
        "rate": round(rate, 2),
        "drift_alert": total >= CONFIDENCE_ROLLING_WINDOW and rate < DRIFT_ALERT_THRESHOLD,
        "recent": recent,
    }


def check_drift_alerts() -> list[str]:
    """Check all profiles for drift alerts. Returns list of alert messages."""
    alerts = []
    profiles = load_profiles()
    for p in profiles:
        stats = get_profile_confidence(p.id)
        if stats.get("drift_alert"):
            alerts.append(
                f"Profile '{p.id}' ({p.supplier} - {p.document_type}) "
                f"has a {stats['rate']:.0%} validation pass rate over the last {CONFIDENCE_ROLLING_WINDOW} documents. "
                f"The supplier may have changed their layout. Consider re-registering."
            )
    return alerts


# ── Command handlers ──────────────────────────────────────────────────


async def list_profiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /list_profiles — list all registered profiles."""
    if not update.message:
        return
    profiles = load_profiles()
    if not profiles:
        await update.message.reply_text("No document profiles are registered.")
        return

    lines = ["Registered document profiles:"]
    for p in profiles:
        stats = get_profile_confidence(p.id)
        drift = " ⚠" if stats.get("drift_alert") else ""
        lines.append(
            f"  {p.id} (v{p.profile_version}){drift}"
        )
        lines.append(f"    Supplier: {p.supplier}")
        lines.append(f"    Type: {p.document_type}")
        lines.append(f"    Fields: {len(p.fields)}")
        if p.classifier:
            lines.append(f"    Classifier markers: {len(p.classifier.markers)}")
        lines.append(f"    Confidence: {stats['rate']:.0%} ({stats['recent_count']}/{CONFIDENCE_ROLLING_WINDOW} recent)")

    await update.message.reply_text("\n".join(lines))


async def profile_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /profile_info <id> — show detailed profile info."""
    if not update.message:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /profile_info <profile_id>")
        return

    profile_id = args[0].strip().lower()
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
    profile = load_profile(profiles_dir / f"{profile_id}.json")
    if not profile:
        await update.message.reply_text(f"Profile '{profile_id}' not found.")
        return

    stats = get_profile_confidence(profile_id)

    lines = [
        f"Profile: {profile.id}",
        f"Name: {profile.name}",
        f"Supplier: {profile.supplier}",
        f"Document type: {profile.document_type}",
        f"Version: {profile.profile_version}",
        f"Status: {profile.status}",
        f"Created: {profile.created_at}",
        f"Updated: {profile.updated_at}",
        "",
        "Fields:",
    ]
    for f in profile.fields:
        req = "required" if f.required else "optional"
        lines.append(f"  {f.name} ({f.type}, {req})")
        if f.pattern:
            lines.append(f"    Pattern: {f.pattern}")
        if f.normalizers:
            lines.append(f"    Normalizers: {', '.join(f.normalizers)}")

    if profile.line_item_table:
        lines.append("")
        lines.append("Table columns:")
        for c in profile.line_item_table.columns:
            hints = ", ".join(c.label_hints[:3]) if c.label_hints else ""
            lines.append(f"  {c.field} ({c.type}) [{hints}]")

    if profile.classifier:
        lines.append("")
        lines.append(f"Classifier: threshold={profile.classifier.match_threshold}, margin={profile.classifier.ambiguity_margin}")
        for m in profile.classifier.markers:
            role = m.role or ""
            lines.append(f"  [{m.type}] weight={m.weight:+d} {role}: {m.pattern[:60]}")

    if profile.validation_rules:
        lines.append("")
        lines.append("Validation rules:")
        for r in profile.validation_rules:
            lines.append(f"  {r.rule} (tolerance={r.tolerance})")

    lines.append("")
    lines.append(f"Workflow:")
    lines.append(f"  PO prefix: {profile.workflow.po_prefix}")
    lines.append(f"  Procurement folder: {profile.workflow.procurement_folder_name}")
    lines.append(f"  Register supplier: {profile.workflow.register_supplier_name}")

    lines.append("")
    lines.append(f"Confidence tracking:")
    lines.append(f"  Total records: {stats['total']}")
    lines.append(f"  Recent ({CONFIDENCE_ROLLING_WINDOW}): {stats['passed']}/{stats['recent_count']} = {stats['rate']:.0%}")
    if stats.get("drift_alert"):
        lines.append("  ⚠ DRIFT ALERT: Low pass rate")

    if profile.ai_extraction_prompt:
        lines.append("")
        lines.append(f"AI prompt: {len(profile.ai_extraction_prompt)} chars")

    await update.message.reply_text("\n".join(lines))


async def disable_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /disable_profile <id> — soft-disable a profile."""
    if not update.message:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /disable_profile <profile_id>")
        return

    profile_id = args[0].strip().lower()
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
    if dp_disable(profile_id, profiles_dir):
        await update.message.reply_text(f"Profile '{profile_id}' disabled.")
    else:
        await update.message.reply_text(f"Profile '{profile_id}' not found or could not be disabled.")


async def enable_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /enable_profile <id> — re-enable a disabled profile."""
    if not update.message:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /enable_profile <profile_id>")
        return

    profile_id = args[0].strip().lower()
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"

    # Load the profile, set status to active, save
    profile_path = profiles_dir / f"{profile_id}.json"
    if not profile_path.exists():
        await update.message.reply_text(f"Profile '{profile_id}' not found.")
        return

    profile = load_profile(profile_path)
    if profile is None:
        await update.message.reply_text(f"Could not load profile '{profile_id}'.")
        return

    updated = profile_from_dict({**profile_to_dict(profile), "status": "active"})
    save_profile(updated, profiles_dir)
    rebuild_index(profiles_dir)
    await update.message.reply_text(f"Profile '{profile_id}' re-enabled.")


async def remove_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /remove_profile <id> — move profile to removed/ directory."""
    if not update.message:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /remove_profile <profile_id>")
        return

    profile_id = args[0].strip().lower()
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
    if dp_remove(profile_id, profiles_dir):
        await update.message.reply_text(f"Profile '{profile_id}' moved to removed/.")
    else:
        await update.message.reply_text(f"Profile '{profile_id}' not found or could not be removed.")


async def test_profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /test_profile <id> — start a test flow for a profile."""
    if not update.message:
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Usage: /test_profile <profile_id>")
        return

    profile_id = args[0].strip().lower()
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
    profile = load_profile(profiles_dir / f"{profile_id}.json")
    if not profile:
        await update.message.reply_text(f"Profile '{profile_id}' not found.")
        return

    # Mark the chat as awaiting a test image
    context.chat_data[TEST_PROFILE_KEY] = {"profile_id": profile_id, "step": "awaiting_image"}
    await update.message.reply_text(
        f"Testing profile '{profile_id}' ({profile.name}).\n"
        "Send a sample image of this document type to test extraction."
    )


async def handle_test_file(update: Update, context: ContextTypes.DEFAULT_TYPE, file_path: Path) -> bool:
    """Handle a file received during test mode. Returns True if handled."""
    state = get_test_state(context)
    if not state:
        return False

    profile_id = state.get("profile_id")
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
    profile = load_profile(profiles_dir / f"{profile_id}.json")
    if not profile:
        if update.message:
            await update.message.reply_text(f"Profile '{profile_id}' no longer exists.")
        clear_test_state(context)
        return True

    if not update.message:
        return True

    # Run local OCR extraction
    try:
        from invoice_bot import extract_invoice_with_local_ocr, UnknownDocumentFormat
        result = extract_invoice_with_local_ocr(file_path)
        data = result.data
    except UnknownDocumentFormat as exc:
        data = {"error": str(exc)}
    except Exception as exc:
        data = {"error": f"Extraction failed: {exc}"}

    # Build report
    lines = [
        f"Test result for profile '{profile_id}':",
        f"Supplier: {profile.supplier}",
        f"Document type: {profile.document_type}",
        "",
    ]

    if "error" in data:
        lines.append(f"Error: {data['error']}")
    else:
        lines.append(f"Tax invoice: {data.get('tax_invoice', 'N/A')}")
        lines.append(f"Date: {data.get('invoice_date', 'N/A')}")
        lines.append(f"Contact: {data.get('contact_person', 'N/A')}")
        lines.append(f"Total: {data.get('document_total', 'N/A')}")
        items = data.get("line_items", [])
        lines.append(f"Line items: {len(items)}")
        for item in items[:5]:
            lines.append(f"  {item.get('item_no')}. {item.get('description')[:50]} | {item.get('quantity')} {item.get('quantity_unit')}")
        if len(items) > 5:
            lines.append(f"  ... and {len(items) - 5} more")

        # Run validation
        from invoice_bot import run_validation_rules, apply_profile_normalizers
        from profile_generator import _self_test_profile
        import asyncio

        # Validation warnings
        normalized = apply_profile_normalizers(data, profile)
        val_warnings = run_validation_rules(normalized, profile)
        if val_warnings:
            lines.append("")
            lines.append("Validation warnings:")
            for w in val_warnings:
                lines.append(f"  - {w}")
        else:
            lines.append("")
            lines.append("Validation: all checks passed")

        # Classifier check
        from invoice_bot import classify_document
        ocr_text = result.raw_text if hasattr(result, 'raw_text') else ""
        if ocr_text:
            pid, status, score, ru = classify_document(ocr_text)
            lines.append("")
            lines.append(f"Classifier: {status} (profile={pid}, score={score})")

    lines.append("")
    lines.append("Use /test_profile again to test another profile.")

    await update.message.reply_text("\n".join(lines))
    clear_test_state(context)
    return True


async def export_profiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /export_profiles — export all profiles as a ZIP."""
    if not update.message:
        return
    profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
    if not profiles_dir.exists():
        await update.message.reply_text("No profiles directory found.")
        return

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(profiles_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            zf.write(path, path.name)
        # Also include removed profiles
        removed_dir = profiles_dir / "removed"
        if removed_dir.exists():
            for path in sorted(removed_dir.glob("*.json")):
                zf.write(path, f"removed/{path.name}")

    zip_buffer.seek(0)
    await update.message.reply_document(
        document=zip_buffer,
        filename="document_profiles_export.zip",
        caption=f"Exported profiles from {profiles_dir}",
    )


async def import_profiles_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /import_profiles — import profiles from a ZIP file."""
    if not update.message or not update.message.document:
        await update.message.reply_text("Send a ZIP file exported from /export_profiles.")
        return

    mime_type = update.message.document.mime_type or ""
    file_name = update.message.document.file_name or ""
    if not file_name.endswith(".zip") and "zip" not in mime_type:
        await update.message.reply_text("Please send a ZIP file.")
        return

    # Download the ZIP
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        telegram_file = await context.bot.get_file(update.message.document.file_id)
        await telegram_file.download_to_drive(custom_path=Path(tmp.name))

        import zipfile
        profiles_dir = Path(__file__).resolve().parent / "data" / "document_profiles"
        imported = 0
        skipped = 0
        errors = []

        with zipfile.ZipFile(tmp.name, "r") as zf:
            for name in zf.namelist():
                if not name.endswith(".json") or name == "index.json" or name.startswith("removed/"):
                    continue
                try:
                    data = json.loads(zf.read(name))
                except json.JSONDecodeError:
                    errors.append(f"{name}: invalid JSON")
                    continue

                # Validate
                validation_errors = validate_profile(data, strict=False)
                if validation_errors:
                    errors.append(f"{name}: validation failed: {'; '.join(validation_errors)}")
                    continue

                # Check for collision
                profile_id = data.get("id", "").lower()
                target_path = profiles_dir / f"{profile_id}.json"
                if target_path.exists():
                    skipped += 1
                    continue

                # Save
                target_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                imported += 1

        rebuild_index(profiles_dir)

        response = f"Imported {imported} profiles."
        if skipped:
            response += f" {skipped} skipped (already exist)."
        if errors:
            response += f"\nErrors: {len(errors)}"
            for e in errors[:5]:
                response += f"\n  - {e}"
        await update.message.reply_text(response)
    finally:
        os.unlink(tmp.name)