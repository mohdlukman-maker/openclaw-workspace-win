"""
Unit tests for document_profiles.py — validator, classifier scoring, normalizers, loader.

These are pure-function tests with no dependency on invoice_bot.py.
"""

import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from document_profiles import (
    SCHEMA_VERSION,
    DocumentProfile,
    ClassifierConfig,
    ClassifierMarker,
    FieldDef,
    TableColumn,
    LineItemTable,
    ValidationRule,
    WorkflowConfig,
    QRConfig,
    NORMALIZER_REGISTRY,
    apply_normalizers,
    score_profile_classifier,
    score_all_profiles,
    classify_best_profile,
    validate_profile,
    profile_from_dict,
    profile_to_dict,
    load_profile,
    load_profiles,
    save_profile,
    rebuild_index,
    disable_profile,
    remove_profile,
)


# ═══════════════════════════════════════════════════════════════════════
#  Validator Tests
# ═══════════════════════════════════════════════════════════════════════

class ValidateProfileTests(unittest.TestCase):
    def setUp(self):
        self.valid_profile = {
            "id": "test_supplier_invoice",
            "name": "Test Supplier - Invoice",
            "supplier": "Test Supplier",
            "document_type": "invoice",
            "schema_version": SCHEMA_VERSION,
            "profile_version": 1,
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
            "status": "active",
            "classifier": {
                "markers": [
                    {"pattern": "TEST SUPPLIER", "type": "literal", "weight": 5, "role": "supplier"},
                    {"pattern": "TS-\\d+", "type": "regex", "weight": 3, "role": "docnumber"},
                ],
                "match_threshold": 8,
                "ambiguity_margin": 3,
            },
            "qr": {"expected": False, "type": None, "use_for_classification": False, "use_for_validation": False},
            "fields": [
                {"name": "invoice_number", "type": "text", "required": True, "pattern": "TS-\\d+", "normalizers": ["strip_whitespace"], "extraction": "ai"},
                {"name": "invoice_date", "type": "date", "required": True, "input_format": "DD.MM.YYYY", "normalizers": ["to_iso_date"], "extraction": "ai"},
            ],
            "line_item_table": {
                "columns": [
                    {"field": "item_no", "label_hints": ["No"], "type": "int"},
                    {"field": "description", "label_hints": ["Description"], "type": "text"},
                ],
                "row_count_source": "ai_with_ocr_reconciliation",
            },
            "validation_rules": [
                {"rule": "row_arithmetic", "expr": "quantity * unit_price == line_total", "tolerance": 0.02},
            ],
            "workflow": {
                "po_prefix": "PO TEST",
                "procurement_folder_name": "TEST SUPPLIER",
                "register_supplier_name": "TEST SUPPLIER",
            },
            "ai_extraction_prompt": "Extract {supplier} {document_type} data.",
        }

    def test_valid_profile_passes(self):
        errors = validate_profile(self.valid_profile, strict=True)
        self.assertEqual(errors, [])

    def test_missing_required_fields(self):
        errors = validate_profile({}, strict=False)
        self.assertIn("id: missing required field", errors)
        self.assertIn("fields: missing required field", errors)
        self.assertIn("workflow: missing required field", errors)

    def test_invalid_document_type(self):
        data = dict(self.valid_profile)
        data["document_type"] = "banana"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("document_type" in e for e in errors))

    def test_invalid_status(self):
        data = dict(self.valid_profile)
        data["status"] = "archived"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("status" in e for e in errors))

    def test_wrong_schema_version(self):
        data = dict(self.valid_profile)
        data["schema_version"] = 999
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("schema_version" in e for e in errors))

    def test_invalid_marker_type(self):
        data = dict(self.valid_profile)
        data["classifier"]["markers"][0]["type"] = "fuzzy"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("classifier.markers[0].type" in e for e in errors))

    def test_invalid_field_type(self):
        data = dict(self.valid_profile)
        data["fields"][0]["type"] = "binary"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("fields[0].type" in e for e in errors))

    def test_invalid_extraction_mode(self):
        data = dict(self.valid_profile)
        data["fields"][0]["extraction"] = "manual"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("fields[0].extraction" in e for e in errors))

    def test_duplicate_field_names(self):
        data = dict(self.valid_profile)
        data["fields"].append({"name": "invoice_number", "type": "text"})
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("duplicate" in e.lower() for e in errors))

    def test_unknown_normalizer(self):
        data = dict(self.valid_profile)
        data["fields"][0]["normalizers"] = ["does_not_exist"]
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("unknown normalizer" in e.lower() for e in errors))

    def test_invalid_crop_hint(self):
        data = dict(self.valid_profile)
        data["fields"][0]["crop_hint"] = [0.1, 0.2]
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("crop_hint" in e for e in errors))

    def test_invalid_rule_name(self):
        data = dict(self.valid_profile)
        data["validation_rules"][0]["rule"] = "quantum_compute"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("validation_rules[0].rule" in e for e in errors))

    def test_invalid_row_count_source(self):
        data = dict(self.valid_profile)
        data["line_item_table"]["row_count_source"] = "magic"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("row_count_source" in e for e in errors))

    def test_invalid_qr_type(self):
        data = dict(self.valid_profile)
        data["qr"]["type"] = "qris"
        errors = validate_profile(data, strict=False)
        self.assertTrue(any("qr.type" in e for e in errors))


# ═══════════════════════════════════════════════════════════════════════
#  Classifier Scoring Tests
# ═══════════════════════════════════════════════════════════════════════

class ClassifierScoringTests(unittest.TestCase):
    def setUp(self):
        self.invoice_profile = DocumentProfile(
            id="tuju_galaxy_invoice",
            name="TUJU GALAXY - Tax Invoice",
            supplier="TUJU GALAXY",
            document_type="invoice",
            classifier=ClassifierConfig(
                markers=(
                    ClassifierMarker(pattern="TUJU GALAXY", type="literal", weight=5, role="supplier"),
                    ClassifierMarker(pattern="TG-[A-Z0-9]{5,}", type="regex", weight=3, role="docnumber"),
                    ClassifierMarker(pattern="tax invoice", type="literal", weight=1, role="doctype"),
                    ClassifierMarker(pattern="delivery order", type="literal", weight=-3, role="doctype_exclusion"),
                ),
                match_threshold=8,
                ambiguity_margin=3,
            ),
        )
        self.do_profile = DocumentProfile(
            id="tuju_galaxy_delivery_order",
            name="TUJU GALAXY - Delivery Order",
            supplier="TUJU GALAXY",
            document_type="delivery_order",
            classifier=ClassifierConfig(
                markers=(
                    ClassifierMarker(pattern="TUJU GALAXY", type="literal", weight=5, role="supplier"),
                    ClassifierMarker(pattern="TG-[A-Z0-9]{5,}", type="regex", weight=3, role="docnumber"),
                    ClassifierMarker(pattern="delivery order", type="literal", weight=1, role="doctype"),
                    ClassifierMarker(pattern="tax invoice", type="literal", weight=-3, role="doctype_exclusion"),
                ),
                match_threshold=8,
                ambiguity_margin=3,
            ),
        )
        self.profiles = [self.invoice_profile, self.do_profile]

    def test_invoice_scores_above_threshold(self):
        text = "TUJU GALAXY SDN BHD Tax Invoice TG-K08849"
        score = score_profile_classifier(self.invoice_profile, text)
        # 5 (TUJU GALAXY) + 3 (TG-K08849) + 1 (tax invoice) = 9
        self.assertEqual(score, 9)

    def test_do_scores_above_threshold(self):
        text = "TUJU GALAXY SDN BHD Delivery Order No TG-K08849"
        score = score_profile_classifier(self.do_profile, text)
        # 5 (TUJU GALAXY) + 3 (TG-K08849) + 1 (delivery order) = 9
        self.assertEqual(score, 9)

    def test_invoice_negative_exclusion_works(self):
        text = "TUJU GALAXY Delivery Order No TG-K08849"
        score = score_profile_classifier(self.invoice_profile, text)
        # 5 (TUJU GALAXY) + 3 (TG-K08849) + 0 (no "tax invoice") + 1 (has "invoice" subword? no, literal is "tax invoice")
        # Actually "delivery order" is in the text, so -3
        # 5 + 3 - 3 = 5
        self.assertEqual(score, 5)
        self.assertLess(score, self.invoice_profile.classifier.match_threshold)

    def test_do_negative_exclusion_works(self):
        text = "TUJU GALAXY Tax Invoice TG-K08849"
        score = score_profile_classifier(self.do_profile, text)
        # 5 (TUJU GALAXY) + 3 (TG-K08849) + 0 (no "delivery order") - 3 (has "tax invoice") = 5
        self.assertEqual(score, 5)
        self.assertLess(score, self.do_profile.classifier.match_threshold)

    def test_classify_best_invoice_wins(self):
        text = "TUJU GALAXY SDN BHD Tax Invoice TG-K08849\nContact: Farah 011-54302725"
        result_id, status, score, runner_up = classify_best_profile(self.profiles, text)
        self.assertEqual(result_id, "tuju_galaxy_invoice")
        self.assertEqual(status, "matched")
        self.assertEqual(score, 9)  # 5+3+1
        # DO scores 5+3-3=5, below threshold 8, so runner_up is 0
        self.assertEqual(runner_up, 0)

    def test_classify_best_do_wins(self):
        text = "TUJU GALAXY SDN BHD Delivery Order TG-K08849\nContact: Zukiram"
        result_id, status, score, runner_up = classify_best_profile(self.profiles, text)
        self.assertEqual(result_id, "tuju_galaxy_delivery_order")
        self.assertEqual(status, "matched")
        self.assertEqual(score, 9)

    def test_below_threshold(self):
        text = "Some random receipt from Kedai Runcit"
        result_id, status, score, runner_up = classify_best_profile(self.profiles, text)
        self.assertEqual(status, "below_threshold")
        self.assertEqual(score, 0)

    def test_ambiguous_when_too_close(self):
        """When both profiles have similar scores, should be ambiguous."""
        # Text with TUJU and TG- but no clear doctype exclusion
        text = "TUJU GALAXY TG-K08849 Contact: Farah"
        result_id, status, score, runner_up = classify_best_profile(self.profiles, text)
        self.assertEqual(status, "ambiguous")

    def test_score_all_profiles(self):
        text = "TUJU GALAXY Tax Invoice TG-K08849"
        scores = score_all_profiles(self.profiles, text)
        self.assertEqual(scores["tuju_galaxy_invoice"], 9)
        self.assertEqual(scores["tuju_galaxy_delivery_order"], 5)

    def test_regex_marker_works(self):
        profile = DocumentProfile(
            id="sst_matcher",
            name="SST Matcher",
            supplier="Test",
            document_type="invoice",
            classifier=ClassifierConfig(
                markers=(
                    ClassifierMarker(pattern=r"SST No[.:]?\s*W10-\d+", type="regex", weight=5),
                ),
                match_threshold=5,
            ),
        )
        self.assertEqual(score_profile_classifier(profile, "SST No: W10-12345"), 5)
        self.assertEqual(score_profile_classifier(profile, "SST No. W10-99999"), 5)
        self.assertEqual(score_profile_classifier(profile, "No SST here"), 0)


# ═══════════════════════════════════════════════════════════════════════
#  Normalizer Tests
# ═══════════════════════════════════════════════════════════════════════

class NormalizerTests(unittest.TestCase):
    def test_strip_whitespace(self):
        self.assertEqual(apply_normalizers("  Hello   World  ", ("strip_whitespace",)), "Hello World")
        self.assertIsNone(apply_normalizers(None, ("strip_whitespace",)))

    def test_ocr_letter_o_to_zero(self):
        self.assertEqual(apply_normalizers("TG-KO8941", ("ocr_letter_o_to_zero",)), "TG-K08941")
        self.assertEqual(apply_normalizers("TG-Ko8941", ("ocr_letter_o_to_zero",)), "TG-K08941")

    def test_ocr_letter_b_to_eight(self):
        self.assertEqual(apply_normalizers("TG-KOB941", ("ocr_letter_o_to_zero", "ocr_letter_b_to_eight")), "TG-K08941")

    def test_normalize_invoice_prefix(self):
        self.assertEqual(apply_normalizers("1G-K08849", ("normalize_invoice_prefix",)), "TG-K08849")
        self.assertEqual(apply_normalizers("T6-K08849", ("normalize_invoice_prefix",)), "TG-K08849")
        self.assertEqual(apply_normalizers("TG-K08849", ("normalize_invoice_prefix",)), "TG-K08849")

    def test_to_iso_date(self):
        self.assertEqual(apply_normalizers("01.07.2026", ("to_iso_date",)), "2026-07-01")
        self.assertEqual(apply_normalizers("1.7.2026", ("to_iso_date",)), "2026-07-01")
        self.assertEqual(apply_normalizers("2026-07-01", ("to_iso_date",)), "2026-07-01")
        self.assertIsNone(apply_normalizers("not a date", ("to_iso_date",)))

    def test_to_iso_date_dmy(self):
        self.assertEqual(apply_normalizers("01/07/2026", ("to_iso_date_dmy",)), "2026-07-01")

    def test_parse_money(self):
        self.assertEqual(apply_normalizers("RM 168.70", ("parse_money",)), 168.7)
        self.assertEqual(apply_normalizers("RM1,234.50", ("parse_money",)), 1234.5)
        self.assertIsNone(apply_normalizers("N/A", ("parse_money",)))

    def test_clean_contact(self):
        result = apply_normalizers("Fax: Farah 011-54302725", ("clean_contact",))
        self.assertEqual(result, "Farah 011-54302725")
        result = apply_normalizers("H/P: 012-3456789", ("clean_contact",))
        self.assertEqual(result, "012-3456789")

    def test_normalize_item_no(self):
        self.assertEqual(apply_normalizers("1.", ("normalize_item_no",)), "1")
        self.assertEqual(apply_normalizers("Item 5", ("normalize_item_no",)), "5")
        self.assertIsNone(apply_normalizers(None, ("normalize_item_no",)))

    def test_normalize_quantity_unit(self):
        self.assertEqual(apply_normalizers("pcs", ("normalize_quantity_unit",)), "pcs")
        self.assertEqual(apply_normalizers("pc", ("normalize_quantity_unit",)), "pcs")
        self.assertEqual(apply_normalizers("ton", ("normalize_quantity_unit",)), "ton")
        self.assertEqual(apply_normalizers("tor", ("normalize_quantity_unit",)), "ton")
        self.assertEqual(apply_normalizers("roll", ("normalize_quantity_unit",)), "roll")
        self.assertEqual(apply_normalizers("toll", ("normalize_quantity_unit",)), "roll")

    def test_chain_multiple_normalizers(self):
        result = apply_normalizers(
            "TG-KO8941",
            ("normalize_invoice_prefix", "ocr_letter_o_to_zero", "strip_whitespace"),
        )
        self.assertEqual(result, "TG-K08941")


# ═══════════════════════════════════════════════════════════════════════
#  Round-trip tests (dict ↔ dataclass)
# ═══════════════════════════════════════════════════════════════════════

class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.profile_dict = {
            "id": "test_supplier_invoice",
            "name": "Test Supplier - Invoice",
            "supplier": "Test Supplier",
            "document_type": "invoice",
            "schema_version": SCHEMA_VERSION,
            "profile_version": 1,
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
            "status": "active",
            "classifier": {
                "markers": [
                    {"pattern": "TEST SUPPLIER", "type": "literal", "weight": 5, "role": "supplier"},
                ],
                "match_threshold": 8,
                "ambiguity_margin": 3,
            },
            "qr": {"expected": False, "type": None, "use_for_classification": False, "use_for_validation": False},
            "fields": [
                {"name": "invoice_number", "type": "text", "required": True, "normalizers": ["strip_whitespace"], "extraction": "ai"},
            ],
            "line_item_table": {
                "columns": [
                    {"field": "item_no", "label_hints": ["No"], "type": "int"},
                ],
                "row_count_source": "ai_with_ocr_reconciliation",
            },
            "validation_rules": [],
            "workflow": {
                "po_prefix": "PO TEST",
                "procurement_folder_name": "TEST SUPPLIER",
                "register_supplier_name": "TEST SUPPLIER",
            },
            "ai_extraction_prompt": "Extract {supplier} data.",
        }

    def test_dict_to_dataclass_to_dict(self):
        errors = validate_profile(self.profile_dict, strict=True)
        self.assertEqual(errors, [])

        profile = profile_from_dict(self.profile_dict)
        self.assertEqual(profile.id, "test_supplier_invoice")
        self.assertEqual(profile.supplier, "Test Supplier")
        self.assertEqual(profile.fields[0].name, "invoice_number")
        self.assertEqual(profile.classifier.markers[0].weight, 5)
        self.assertEqual(profile.workflow.po_prefix, "PO TEST")

        # Round-trip back to dict
        result_dict = profile_to_dict(profile)
        # Fields are the same
        self.assertEqual(result_dict["id"], "test_supplier_invoice")
        self.assertEqual(result_dict["classifier"]["markers"][0]["pattern"], "TEST SUPPLIER")

    def test_profile_without_optional_blocks(self):
        minimal = {
            "id": "minimal",
            "name": "Minimal",
            "supplier": "Test",
            "document_type": "invoice",
            "schema_version": SCHEMA_VERSION,
            "profile_version": 1,
            "created_at": "2026-07-08T00:00:00Z",
            "updated_at": "2026-07-08T00:00:00Z",
            "status": "active",
            "fields": [
                {"name": "field1", "type": "text", "extraction": "ai"},
            ],
            "workflow": {
                "po_prefix": "PO",
                "procurement_folder_name": "TEST",
                "register_supplier_name": "TEST",
            },
        }
        errors = validate_profile(minimal, strict=False)
        self.assertEqual(errors, [])
        profile = profile_from_dict(minimal)
        self.assertEqual(profile.id, "minimal")
        self.assertIsNone(profile.classifier)
        self.assertIsNone(profile.line_item_table)


# ═══════════════════════════════════════════════════════════════════════
#  Loader / Saver Tests
# ═══════════════════════════════════════════════════════════════════════

class LoaderSaverTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.profiles_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_profile(self):
        profile = DocumentProfile(
            id="test_profile",
            name="Test Profile",
            supplier="Test Supplier",
            document_type="invoice",
            status="active",
            fields=(FieldDef(name="field1", type="text"),),
            workflow=WorkflowConfig(
                po_prefix="PO",
                procurement_folder_name="TEST",
                register_supplier_name="TEST",
            ),
        )
        path = save_profile(profile, self.profiles_dir)
        self.assertTrue(path.exists())

        loaded = load_profile(path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, "test_profile")
        self.assertEqual(loaded.supplier, "Test Supplier")
        self.assertEqual(loaded.fields[0].name, "field1")

    def test_load_profiles_skips_inactive(self):
        # Save active profile
        active = DocumentProfile(
            id="active_one",
            name="Active",
            supplier="A",
            document_type="invoice",
            status="active",
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="A", register_supplier_name="A"),
        )
        save_profile(active, self.profiles_dir)

        # Save disabled profile
        disabled = DocumentProfile(
            id="disabled_one",
            name="Disabled",
            supplier="B",
            document_type="invoice",
            status="disabled",
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="B", register_supplier_name="B"),
        )
        save_profile(disabled, self.profiles_dir)

        loaded = load_profiles(self.profiles_dir)
        ids = [p.id for p in loaded]
        self.assertIn("active_one", ids)
        self.assertNotIn("disabled_one", ids)

    def test_load_profiles_skips_versioned_files(self):
        # Save a profile
        profile = DocumentProfile(
            id="versioned",
            name="Versioned",
            supplier="V",
            document_type="invoice",
            status="active",
            profile_version=2,
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="V", register_supplier_name="V"),
        )
        save_profile(profile, self.profiles_dir)

        # Manually create an old version file
        old = self.profiles_dir / "versioned.v1.json"
        old.write_text('{"id": "versioned", "name": "Old", "supplier": "V", "document_type": "invoice", "schema_version": 1, "profile_version": 1, "status": "active", "fields": [], "workflow": {"po_prefix": "PO", "procurement_folder_name": "V", "register_supplier_name": "V"}}', encoding="utf-8")

        loaded = load_profiles(self.profiles_dir)
        ids = [p.id for p in loaded]
        # Only the active .json (v2) should be loaded
        self.assertIn("versioned", ids)
        self.assertEqual(len(ids), 1)

    def test_save_archives_old_version(self):
        v1 = DocumentProfile(
            id="archivable",
            name="v1",
            supplier="A",
            document_type="invoice",
            status="active",
            profile_version=1,
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="A", register_supplier_name="A"),
        )
        save_profile(v1, self.profiles_dir)

        v2 = DocumentProfile(
            id="archivable",
            name="v2",
            supplier="A",
            document_type="invoice",
            status="active",
            profile_version=2,
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="A", register_supplier_name="A"),
        )
        save_profile(v2, self.profiles_dir)

        # Old version should be archived
        self.assertTrue((self.profiles_dir / "archivable.v1.json").exists())
        self.assertTrue((self.profiles_dir / "archivable.json").exists())

        # Load should return v2
        loaded = load_profile(self.profiles_dir / "archivable.json")
        self.assertEqual(loaded.profile_version, 2)

    def test_rebuild_index(self):
        profile = DocumentProfile(
            id="indexed",
            name="Indexed",
            supplier="I",
            document_type="invoice",
            status="active",
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="I", register_supplier_name="I"),
        )
        save_profile(profile, self.profiles_dir)

        index_path = self.profiles_dir / "index.json"
        self.assertTrue(index_path.exists())
        with open(index_path, "r") as f:
            index = json.load(f)
        entry_ids = [e["id"] for e in index["profiles"]]
        self.assertIn("indexed", entry_ids)

    def test_disable_profile(self):
        profile = DocumentProfile(
            id="to_disable",
            name="To Disable",
            supplier="D",
            document_type="invoice",
            status="active",
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="D", register_supplier_name="D"),
        )
        save_profile(profile, self.profiles_dir)

        self.assertTrue(disable_profile("to_disable", self.profiles_dir))
        loaded = load_profile(self.profiles_dir / "to_disable.json")
        self.assertEqual(loaded.status, "disabled")

    def test_remove_profile(self):
        profile = DocumentProfile(
            id="to_remove",
            name="To Remove",
            supplier="R",
            document_type="invoice",
            status="active",
            fields=(FieldDef(name="f1", type="text"),),
            workflow=WorkflowConfig(po_prefix="PO", procurement_folder_name="R", register_supplier_name="R"),
        )
        save_profile(profile, self.profiles_dir)

        self.assertTrue(remove_profile("to_remove", self.profiles_dir))
        self.assertFalse((self.profiles_dir / "to_remove.json").exists())
        self.assertTrue((self.profiles_dir / "removed" / "to_remove.json").exists())


# ═══════════════════════════════════════════════════════════════════════
#  Edge case tests
# ═══════════════════════════════════════════════════════════════════════

class EdgeCaseTests(unittest.TestCase):
    def test_no_profiles_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as d:
            profiles = load_profiles(Path(d))
            self.assertEqual(profiles, [])

    def test_missing_directory_returns_empty(self):
        profiles = load_profiles(Path("/nonexistent/path"))
        self.assertEqual(profiles, [])

    def test_corrupt_json_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "corrupt.json"
            path.write_text("{bad json", encoding="utf-8")
            result = load_profile(path)
            self.assertIsNone(result)

    def test_classifier_no_markers_scores_zero(self):
        profile = DocumentProfile(
            id="no_markers",
            name="No Markers",
            supplier="N",
            document_type="invoice",
            # No classifier
        )
        self.assertEqual(score_profile_classifier(profile, "any text"), 0)

    def test_apply_normalizers_unknown_skips(self):
        result = apply_normalizers("hello", ("unknown_normalizer",))
        self.assertEqual(result, "hello")


if __name__ == "__main__":
    unittest.main()