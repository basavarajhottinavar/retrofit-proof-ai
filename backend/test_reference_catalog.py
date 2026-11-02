import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from reference_catalog import CPE_REFERENCE_FILE, DNG_REFERENCE_FILE, lookup_legacy_references


class ReferenceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self._write_cpe_workbook()
        self._write_dng_workbook()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_cpe_workbook(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Tabelle1"
        sheet["B2"] = "Solenoid valves CPE10"
        sheet["B3"] = "Pilot air supply"
        sheet["C3"] = "Plug socket"
        sheet["D3"] = "Voltage"
        sheet["E3"] = "Connection"
        sheet["F3"] = "Part No."
        sheet["B4"] = "3/2-way valve, normally closed"
        sheet["B5"] = "Internal"
        sheet["C5"] = "Square"
        sheet["D5"] = "24 V DC"
        sheet["E5"] = "M5"
        sheet["F5"] = "196845"
        sheet["G5"] = "CPE10-M1BH-3GL-M5"
        sheet["J5"] = "564212"
        sheet["K5"] = "VUVG-L10-M52-RT-M5-1H2L"
        sheet["L5"] = "Historical alternative"
        workbook.save(self.data_dir / CPE_REFERENCE_FILE)
        workbook.close()

    def _write_dng_workbook(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Tabelle1"
        sheet["A3"] = "Old PN"
        sheet["B3"] = "Description"
        sheet["C3"] = "status"
        sheet["F3"] = "New PN"
        sheet["G3"] = "Description"
        sheet["N3"] = "Comment"
        sheet["A4"] = "33024"
        sheet["B4"] = "Standard cylinder"
        sheet["C4"] = "A"
        sheet["F4"] = "2036032"
        sheet["G4"] = "Replacement cylinder"
        sheet["N4"] = "Historical cross-reference"
        workbook.save(self.data_dir / DNG_REFERENCE_FILE)
        workbook.close()

    def test_exact_lookup_preserves_source_and_marks_result_unverified(self):
        status, lookups = lookup_legacy_references(["196845"], self.data_dir)

        self.assertEqual(status, "loaded")
        self.assertEqual(len(lookups), 1)
        self.assertTrue(lookups[0]["found"])
        record = lookups[0]["records"][0]
        self.assertEqual(record["source_file"], CPE_REFERENCE_FILE)
        self.assertEqual(record["source_row"], 5)
        self.assertEqual(record["family_or_function"], "Solenoid valves CPE10 / 3/2-way valve, normally closed")
        self.assertEqual(record["technical_context"]["pilot_air_supply"], "Internal")
        self.assertEqual(record["technical_context"]["voltage"], "24 V DC")
        self.assertEqual(record["candidates"][0]["part_number"], "564212")
        self.assertIn("not a compatibility approval", record["review_notice"])

    def test_cylinder_lookup_returns_source_comment_and_candidate(self):
        status, lookups = lookup_legacy_references(["33024"], self.data_dir)

        self.assertEqual(status, "loaded")
        record = lookups[0]["records"][0]
        self.assertEqual(record["source_file"], DNG_REFERENCE_FILE)
        self.assertEqual(record["source_row"], 4)
        self.assertEqual(record["source_status"], "A")
        self.assertEqual(record["source_comment"], "Historical cross-reference")
        self.assertEqual(record["candidates"][0]["part_number"], "2036032")

    def test_lookup_is_exact_and_unknown_part_is_not_guessed(self):
        status, lookups = lookup_legacy_references(["19684"], self.data_dir)

        self.assertEqual(status, "loaded")
        self.assertFalse(lookups[0]["found"])
        self.assertEqual(lookups[0]["records"], [])

    def test_missing_workbooks_are_reported(self):
        empty_dir = self.data_dir / "empty"
        empty_dir.mkdir()

        status, lookups = lookup_legacy_references(["33024"], empty_dir)

        self.assertEqual(status, "not_available")
        self.assertFalse(lookups[0]["found"])


if __name__ == "__main__":
    unittest.main()
