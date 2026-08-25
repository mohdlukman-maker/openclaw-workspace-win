"""
Registration flow for the Telegram invoice extractor bot.

Handles the multi-step conversation for registering new document profiles
via the /register_document command.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

import document_profiles
import registration_state
from document_profiles import (
    load_profiles,
    profile_from_dict,
    profile_to_dict,
    save_profile,
    rebuild_index,
    score_profile_classifier,
    classify_best_profile,
)
from profile_generator import generate_profile_from_samples

logger = logging.getLogger(__name__)

# ── Conversation state keys ───────────────────────────────────────────
REGISTRATION_KEY = "registration"


# ── State machine ─────────────────────────────────────────────────────


def get_registration_state(context: ContextTypes.DEFAULT_TYPE) -> dict[str, Any] | None:
    """Get the current registration state, if any."""
    state = context.chat_data.get(REGISTRATION_KEY)
    if isinstance(state, dict):
        return state
    # Try loading from persistent storage
    chat_id = _chat_id(context)
    if chat_id:
        state = registration_state.load_registration_state(chat_id)
        if state:
            context.chat_data[REGISTRATION_KEY] = state
            return state
    return None


def _chat_id(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Get the chat ID from context."""
    try:
        if context._chat_id:
            return str(context._chat_id)
    except Exception:
        pass
    return None


def clear_registration_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Clear the registration state from memory and disk."""
    chat_id = _chat_id(context)
    if chat_id:
        registration_state.clear_registration_state(chat_id)
    context.chat_data.pop(REGISTRATION_KEY, None)


def _persist_state(context: ContextTypes.DEFAULT_TYPE, state: dict[str, Any]) -> None:
    """Persist the registration state to disk."""
    chat_id = _chat_id(context)
    if chat_id:
        registration_state.save_registration_state(chat_id, state)


def is_in_registration_mode(context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if the chat is currently in registration mode."""
    state = get_registration_state(context)
    return state is not None


# ── Command handlers ──────────────────────────────────────────────────


async def register_document_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /register_document — start the registration flow."""
    if not update.message:
        return

    # Clear any existing registration state
    clear_registration_state(context)

    state = {
        "step": "awaiting_samples",
        "samples": [],
        "blank_template": None,
        "supplier_name": None,
        "draft_profile": None,
        "draft_json": None,
        "self_test": None,
        "errors": [],
        "warnings": [],
    }
    context.chat_data[REGISTRATION_KEY] = state
    _persist_state(context, state)

    await update.message.reply_text(
        "Let's register a new document profile.\n\n"
        "Send 1–2 filled samples of the document (photo of the document, "
        "or an XLSX file).\n\n"
        "If you also have an empty template of the same document, "
        "send /blank first, then the empty template.\n\n"
        "To specify the supplier name, send /supplier <name>.\n\n"
        "Send /cancel at any time to abort."
    )


async def register_blank_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /blank — mark next file as blank template."""
    if not update.message:
        return
    state = get_registration_state(context)
    if not state:
        await update.message.reply_text("No registration in progress. Use /register_document first.")
        return

    state["step"] = "awaiting_blank"
    await update.message.reply_text("Send the blank template file (photo, or XLSX file).")


async def register_supplier_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /supplier <name> — set supplier name."""
    if not update.message:
        return
    state = get_registration_state(context)
    if not state:
        await update.message.reply_text("No registration in progress. Use /register_document first.")
        return

    name = " ".join(context.args or []).strip()
    if not name:
        await update.message.reply_text("Send the supplier name. Example: /supplier ABC Sdn Bhd")
        return

    state["supplier_name"] = name
    await update.message.reply_text(f"Supplier name set to: {name}")


# ── File handlers ─────────────────────────────────────────────────────


async def handle_registration_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    file_path: Path,
) -> None:
    """Handle a file received during registration mode."""
    state = get_registration_state(context)
    if not state:
        return

    if not update.message:
        return

    # Handle blank template
    if state.get("step") == "awaiting_blank":
        state["blank_template"] = file_path
        state["step"] = "awaiting_samples"
        _persist_state(context, state)
        await update.message.reply_text(
            f"Blank template saved: {file_path.name}. "
            "Now send 1–2 filled samples of the document."
        )
        return

    # Collect samples
    state["samples"].append(file_path)
    sample_count = len(state["samples"])
    _persist_state(context, state)

    if sample_count >= 2:
        # We have enough samples — generate the profile
        await update.message.reply_text(
            f"Got {sample_count} sample(s). Generating profile..."
        )
        await _generate_and_preview(update, context, state)
    else:
        await update.message.reply_text(
            f"Sample {sample_count} saved: {file_path.name}. "
            "Send one more sample, or send /generate to create the profile with what we have."
        )


async def _generate_and_preview(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state: dict[str, Any],
) -> None:
    """Run the profile generator and show a preview."""
    if not update.message:
        return

    try:
        result = await generate_profile_from_samples(
            samples=state["samples"],
            blank_template=state.get("blank_template"),
            supplier_name=state.get("supplier_name"),
        )
    except Exception as exc:
        logger.exception("Profile generation failed")
        await update.message.reply_text(f"Profile generation failed: {exc}")
        return

    state["errors"] = result.get("errors", [])
    state["warnings"] = result.get("warnings", [])
    state["self_test"] = result.get("self_test")

    if result.get("errors"):
        error_text = "\n".join(f"- {e}" for e in result["errors"])
        await update.message.reply_text(
            f"Profile generation failed:\n{error_text}\n\n"
            "Send /cancel to abort or try again with better samples."
        )
        return

    profile = result.get("profile")
    if not profile or not result.get("draft_json"):
        await update.message.reply_text(
            "Profile generation returned an empty result. Send /cancel to abort."
        )
        return

    state["draft_profile"] = profile
    state["draft_json"] = result["draft_json"]

    # Check for collisions
    collision_warnings = _check_collisions(profile)
    if collision_warnings:
        state["warnings"].extend(collision_warnings)

    # Build preview
    preview = _build_preview(profile, state)
    state["preview"] = preview

    # Show inline keyboard
    keyboard = [
        [
            InlineKeyboardButton("Accept", callback_data="reg_accept"),
            InlineKeyboardButton("Edit", callback_data="reg_edit"),
            InlineKeyboardButton("Cancel", callback_data="reg_cancel"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(preview, reply_markup=reply_markup)


def _build_preview(profile, state: dict[str, Any]) -> str:
    """Build a preview message for the generated profile."""
    lines = [
        "Profile preview:",
        f"Name: {profile.name}",
        f"Supplier: {profile.supplier}",
        f"Document type: {profile.document_type}",
        "",
        "Fields:",
    ]
    for f in profile.fields:
        req = "required" if f.required else "optional"
        lines.append(f"  - {f.name} ({f.type}, {req})")
        if f.pattern:
            lines.append(f"    Pattern: {f.pattern}")
        if f.normalizers:
            lines.append(f"    Normalizers: {', '.join(f.normalizers)}")

    if profile.line_item_table:
        lines.append("")
        lines.append("Table columns:")
        for c in profile.line_item_table.columns:
            hints = ", ".join(c.label_hints[:3]) if c.label_hints else ""
            lines.append(f"  - {c.field} ({c.type}) [{hints}]")

    if profile.classifier:
        lines.append("")
        lines.append("Classifier markers:")
        for m in profile.classifier.markers:
            role = m.role or ""
            lines.append(f"  [{m.type}] weight={m.weight:+d} {role}: {m.pattern[:60]}")

    st = state.get("self_test")
    if st:
        lines.append("")
        lines.append(f"Self-test: {'PASSED' if st.get('passed') else 'FAILED'}")
        lines.append(f"  {st.get('details', '')}")

    if state.get("warnings"):
        lines.append("")
        lines.append("Warnings:")
        for w in state["warnings"]:
            lines.append(f"  - {w}")

    lines.append("")
    lines.append("Accept, edit, or cancel?")

    return "\n".join(lines)


def _check_collisions(profile) -> list[str]:
    """Check if the new profile's classifier would collide with existing profiles."""
    warnings = []
    existing_profiles = load_profiles()
    if not existing_profiles:
        return warnings

    # Check existing profile texts against the new profile's classifier
    # We use the existing profiles' classifiers as a proxy
    markers = profile.classifier.markers if profile.classifier else []
    if not markers:
        return warnings

    for existing in existing_profiles:
        if existing.id == profile.id:
            continue
        # Check if the existing profile's classifier would match the new profile's supplier/doc type
        # This is a simplified check — full collision detection requires OCR text
        existing_supplier = existing.supplier.lower()
        new_supplier = profile.supplier.lower()
        if existing_supplier == new_supplier and existing.document_type == profile.document_type:
            warnings.append(
                f"Collision: {existing.id} already covers {existing.supplier} - {existing.document_type}. "
                f"New profile '{profile.id}' may overlap."
            )

    return warnings


# ── Callback handlers ─────────────────────────────────────────────────


async def registration_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard callbacks for registration."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    state = get_registration_state(context)
    if not state:
        await query.edit_message_text("Registration session expired. Use /register_document again.")
        return

    action = query.data

    if action == "reg_accept":
        await _accept_profile(update, context, state)
    elif action == "reg_cancel":
        await _cancel_registration(update, context)
    elif action.startswith("reg_edit_"):
        await _edit_field(update, context, state, action)
    elif action == "reg_edit":
        # Show field list to edit
        await _show_edit_options(update, context, state)


async def _accept_profile(update, context, state):
    """Accept and save the generated profile."""
    profile = state.get("draft_profile")
    if not profile:
        if update.callback_query:
            await update.callback_query.edit_message_text("No profile to save.")
        return

    try:
        save_profile(profile)
        reload_profiles()
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"Profile registered: {profile.name}\n\n"
                f"Upload a {profile.supplier} {profile.document_type} to test it."
            )
        clear_registration_state(context)
    except Exception as exc:
        logger.exception("Failed to save profile")
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"Failed to save profile: {exc}\n\nSend /cancel to abort."
            )


async def _cancel_registration(update, context):
    """Cancel the registration flow."""
    clear_registration_state(context)
    if update.callback_query:
        await update.callback_query.edit_message_text("Registration cancelled.")
    elif update.message:
        await update.message.reply_text("Registration cancelled.")


async def _show_edit_options(update, context, state):
    """Show the list of fields that can be edited."""
    profile = state.get("draft_profile")
    if not profile:
        return

    lines = ["Select a field to edit:"]
    keyboard = []
    for i, f in enumerate(profile.fields):
        lines.append(f"{i + 1}. {f.name} ({f.type})")
        keyboard.append([
            InlineKeyboardButton(f"{i + 1}. {f.name}", callback_data=f"reg_edit_{i}")
        ])

    keyboard.append([InlineKeyboardButton("Cancel", callback_data="reg_cancel")])

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(keyboard),
        )


async def _edit_field(update, context, state, action):
    """Handle editing a specific field."""
    match = re.match(r"reg_edit_(\d+)", action)
    if not match:
        return
    field_idx = int(match.group(1))

    profile = state.get("draft_profile")
    if not profile or field_idx >= len(profile.fields):
        return

    field = profile.fields[field_idx]
    lines = [
        f"Editing field: {field.name}",
        f"Current type: {field.type}",
        f"Current required: {field.required}",
        f"Current pattern: {field.pattern or '(none)'}",
        f"Current normalizers: {', '.join(field.normalizers) if field.normalizers else '(none)'}",
        "",
        "Send /edit_field_name <new_name> to rename",
        "Send /edit_field_pattern <regex> to change the pattern",
        "Send /edit_field_required to toggle required",
        "Send /edit_field_delete to remove this field",
        "Send /preview to see the updated profile",
        "Send /cancel to stop editing",
    ]

    if update.callback_query:
        state["editing_field_idx"] = field_idx
        await update.callback_query.edit_message_text("\n".join(lines))


async def handle_edit_commands(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle edit commands during registration. Returns True if handled."""
    state = get_registration_state(context)
    if not state:
        return False

    if not update.message:
        return False

    text = update.message.text or ""
    editing_idx = state.get("editing_field_idx")
    profile = state.get("draft_profile")
    if editing_idx is None or profile is None or editing_idx >= len(profile.fields):
        return False

    if text.startswith("/edit_field_name "):
        new_name = text[17:].strip()
        if new_name:
            # Create a new profile with the renamed field
            new_fields = list(profile.fields)
            old = new_fields[editing_idx]
            new_fields[editing_idx] = document_profiles.FieldDef(
                name=new_name,
                type=old.type,
                label_hints=old.label_hints,
                required=old.required,
                pattern=old.pattern,
                normalizers=old.normalizers,
                extraction=old.extraction,
                crop_hint=old.crop_hint,
                input_format=old.input_format,
            )
            state["draft_profile"] = document_profiles.DocumentProfile(
                id=profile.id,
                name=profile.name,
                supplier=profile.supplier,
                document_type=profile.document_type,
                schema_version=profile.schema_version,
                profile_version=profile.profile_version,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
                status=profile.status,
                classifier=profile.classifier,
                qr=profile.qr,
                fields=tuple(new_fields),
                line_item_table=profile.line_item_table,
                validation_rules=profile.validation_rules,
                workflow=profile.workflow,
                ai_extraction_prompt=profile.ai_extraction_prompt,
            )
            await update.message.reply_text(f"Field renamed to '{new_name}'. Send /preview to see the updated profile.")
            return True

    elif text.startswith("/edit_field_pattern "):
        new_pattern = text[20:].strip()
        if new_pattern:
            new_fields = list(profile.fields)
            old = new_fields[editing_idx]
            new_fields[editing_idx] = document_profiles.FieldDef(
                name=old.name,
                type=old.type,
                label_hints=old.label_hints,
                required=old.required,
                pattern=new_pattern,
                normalizers=old.normalizers,
                extraction=old.extraction,
                crop_hint=old.crop_hint,
                input_format=old.input_format,
            )
            state["draft_profile"] = document_profiles.DocumentProfile(
                id=profile.id,
                name=profile.name,
                supplier=profile.supplier,
                document_type=profile.document_type,
                schema_version=profile.schema_version,
                profile_version=profile.profile_version,
                created_at=profile.created_at,
                updated_at=profile.updated_at,
                status=profile.status,
                classifier=profile.classifier,
                qr=profile.qr,
                fields=tuple(new_fields),
                line_item_table=profile.line_item_table,
                validation_rules=profile.validation_rules,
                workflow=profile.workflow,
                ai_extraction_prompt=profile.ai_extraction_prompt,
            )
            await update.message.reply_text(f"Pattern updated. Send /preview to see the updated profile.")
            return True

    elif text == "/edit_field_required":
        new_fields = list(profile.fields)
        old = new_fields[editing_idx]
        new_fields[editing_idx] = document_profiles.FieldDef(
            name=old.name,
            type=old.type,
            label_hints=old.label_hints,
            required=not old.required,
            pattern=old.pattern,
            normalizers=old.normalizers,
            extraction=old.extraction,
            crop_hint=old.crop_hint,
            input_format=old.input_format,
        )
        state["draft_profile"] = document_profiles.DocumentProfile(
            id=profile.id,
            name=profile.name,
            supplier=profile.supplier,
            document_type=profile.document_type,
            schema_version=profile.schema_version,
            profile_version=profile.profile_version,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            status=profile.status,
            classifier=profile.classifier,
            qr=profile.qr,
            fields=tuple(new_fields),
            line_item_table=profile.line_item_table,
            validation_rules=profile.validation_rules,
            workflow=profile.workflow,
            ai_extraction_prompt=profile.ai_extraction_prompt,
        )
        status = "required" if new_fields[editing_idx].required else "optional"
        await update.message.reply_text(f"Field toggled to {status}. Send /preview to see the updated profile.")
        return True

    elif text == "/edit_field_delete":
        new_fields = list(profile.fields)
        deleted_name = new_fields.pop(editing_idx).name
        state["draft_profile"] = document_profiles.DocumentProfile(
            id=profile.id,
            name=profile.name,
            supplier=profile.supplier,
            document_type=profile.document_type,
            schema_version=profile.schema_version,
            profile_version=profile.profile_version,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
            status=profile.status,
            classifier=profile.classifier,
            qr=profile.qr,
            fields=tuple(new_fields),
            line_item_table=profile.line_item_table,
            validation_rules=profile.validation_rules,
            workflow=profile.workflow,
            ai_extraction_prompt=profile.ai_extraction_prompt,
        )
        state["editing_field_idx"] = None
        await update.message.reply_text(f"Field '{deleted_name}' deleted. Send /preview to see the updated profile.")
        return True

    elif text == "/preview":
        preview = _build_preview(state["draft_profile"], state)
        keyboard = [
            [
                InlineKeyboardButton("Accept", callback_data="reg_accept"),
                InlineKeyboardButton("Edit", callback_data="reg_edit"),
                InlineKeyboardButton("Cancel", callback_data="reg_cancel"),
            ],
        ]
        if update.message:
            await update.message.reply_text(preview, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    return False


async def handle_registration_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle text messages during registration. Returns True if handled."""
    state = get_registration_state(context)
    if not state:
        return False

    if not update.message:
        return False

    text = update.message.text or ""

    # Handle /generate
    if text == "/generate":
        if state["samples"]:
            await _generate_and_preview(update, context, state)
            return True
        else:
            await update.message.reply_text("No samples collected yet. Send document files first.")
            return True

    # Handle /cancel
    if text == "/cancel":
        await _cancel_registration(update, context)
        return True

    # Handle edit commands
    if await handle_edit_commands(update, context):
        return True

    return False


# ── Lazy import for document_profiles ─────────────────────────────────
import document_profiles