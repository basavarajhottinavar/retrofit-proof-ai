import json
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from project_reconciliation import (
    OFFICIAL_FACTS_FILE,
    lookup_project_component_names,
    reconcile_project,
)

WORKBOOK_NAME = "Project_316_parts_1.xlsx"

HEADERS = [
    "Date",
    "OTRSID",
    "TRSref/FaxidRef",
    "Cluster",
    "Country",
    "SL.NO",
    "Customer material number",
    "Competitor",
    "Original code",
    "Description",
    "Festo part number",
    "Festo type code",
    "Sign",
    "Remarks",
    "US-Competitorlink",
    "FoundinCRT:Yes/No/NA",
    "Projecteditor",
    "Product Type",
]


class ProjectReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self._write_workbook()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_workbook(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Sheet1"
        sheet.append(HEADERS)
        self._append(sheet, 1, "VALVE-A", "111", "VUVS-A", "drawing item 1; check compatibility")
        self._append(sheet, 2, "NA", 0, 0, "drawing item 2; No Festo equivalent")
        self._append(sheet, 3, "VALVE-B", None, "TYPE-B", "drawing item 3")
        self._append(sheet, 4, "UNNUMBERED-X", 0, 0, "un-numbered item")
        self._append(sheet, 5, "MISSING-X", "222", "TYPE-X", "drawing item 5")
        workbook.save(self.data_dir / WORKBOOK_NAME)
        workbook.close()

    def _append(self, sheet, item, original_code, festo_number, festo_type, remarks, description=None):
        values = [None] * len(HEADERS)
        values[HEADERS.index("SL.NO")] = item
        values[HEADERS.index("Competitor")] = "SMC"
        values[HEADERS.index("Original code")] = original_code
        values[HEADERS.index("Description")] = description or f"Item {item} description"
        values[HEADERS.index("Festo part number")] = festo_number
        values[HEADERS.index("Festo type code")] = festo_type
        values[HEADERS.index("Remarks")] = remarks
        sheet.append(values)

    def test_exact_item_matches_and_review_states_are_preserved(self):
        result = reconcile_project(
            "316.pdf",
            "1: VALVE-A\n2: DN7.2 coupling\n3: VALVE-B\nUNNUMBERED-X\n",
            self.data_dir,
        )

        self.assertEqual(result["status"], "text_reconciled")
        self.assertEqual(result["total_source_lines"], 5)
        self.assertFalse(result["source_signoff_present"])
        self.assertEqual(result["records"][0]["diagram_match_status"], "exact_code_and_item_match")
        self.assertEqual(result["records"][0]["reference_status"], "provisional_reference")
        self.assertEqual(result["records"][1]["diagram_match_status"], "drawing_item_present_code_unavailable")
        self.assertEqual(result["records"][1]["reference_status"], "no_candidate_recorded")
        self.assertEqual(result["records"][2]["reference_status"], "source_listed_unverified")
        self.assertEqual(result["records"][3]["diagram_match_status"], "exact_code_found_without_item_number")
        self.assertEqual(result["records"][4]["diagram_match_status"], "not_found_in_text_layer")
        self.assertTrue(all(record["requires_engineer_review"] for record in result["records"]))

    def test_part_code_prefix_is_not_counted_as_exact_match(self):
        result = reconcile_project("316.pdf", "1: VALVE-A2", self.data_dir)

        self.assertEqual(result["records"][0]["diagram_match_status"], "drawing_item_code_mismatch")

    def test_official_facts_join_only_on_exact_festo_part_number(self):
        facts = {
            "retrieved_on": "2026-11-03",
            "source_region": "Festo US online store",
            "products": [
                {
                    "part_number": "111",
                    "type_code": "VUVS-A",
                    "product_page": "https://example.invalid/product",
                }
            ],
        }
        (self.data_dir / OFFICIAL_FACTS_FILE).write_text(json.dumps(facts), encoding="utf-8")

        result = reconcile_project("316.pdf", "1: VALVE-A", self.data_dir)

        self.assertEqual(result["official_product_facts_status"], "loaded")
        self.assertEqual(result["records"][0]["official_festo_product"]["part_number"], "111")
        self.assertIsNone(result["records"][2]["official_festo_product"])

    def test_only_project_316_filename_uses_project_crosswalk(self):
        self.assertIsNone(reconcile_project("other.pdf", "1: VALVE-A", self.data_dir))

    def test_missing_workbook_is_reported(self):
        empty_dir = Path(self.temp_dir.name) / "empty"
        empty_dir.mkdir()

        result = reconcile_project("316.pdf", "1: VALVE-A", empty_dir)

        self.assertEqual(result["status"], "not_available")
        self.assertEqual(result["source_files"], [])

    def test_project_id_from_pdf_text_matches_a_generic_filename(self):
        workbook_path = self.data_dir / "Project_case-42_parts_1.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(HEADERS)
        self._append(sheet, 7, "VALVE-42", "777", "TYPE-42", "Project case-42; drawing item 7")
        workbook.save(workbook_path)
        workbook.close()

        result = reconcile_project(
            "brownfield-scan.pdf",
            "Project: case-42\n1: VALVE-A\n7: VALVE-42",
            self.data_dir,
        )

        self.assertEqual(result["project_id"], "case42")
        self.assertEqual(result["source_files"], [workbook_path.name])
        self.assertEqual(result["records"][0]["diagram_match_status"], "exact_code_and_item_match")

    def test_legacy_name_lookup_supports_exact_names_and_description_phrases(self):
        workbook_path = self.data_dir / WORKBOOK_NAME
        workbook = load_workbook(workbook_path)
        self._append(
            workbook.active,
            6,
            "KQ2T16-00A",
            "153133",
            "QST-16",
            "Project 316; drawing item 6",
            description="Push-in T-connector, 16 mm",
        )
        workbook.save(workbook_path)
        workbook.close()

        lookups = lookup_project_component_names(
            ["Push-in T-connector, 16 mm", "Push-in T-connector", "KQ2T16-00A", "unlisted component"],
            self.data_dir,
        )

        self.assertEqual(lookups[0]["matches"][0]["match_type"], "exact_component_name")
        self.assertEqual(lookups[1]["matches"][0]["match_type"], "description_phrase")
        self.assertEqual(lookups[2]["matches"][0]["match_type"], "exact_part_number")
        self.assertEqual(lookups[2]["matches"][0]["festo_part_number"], "153133")
        self.assertEqual(lookups[3]["status"], "no_match")
        self.assertEqual(lookups[3]["matches"], [])


if __name__ == "__main__":
    unittest.main()
