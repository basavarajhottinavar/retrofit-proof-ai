import unittest
from io import BytesIO, StringIO

import ezdxf
from openpyxl import Workbook
from pypdf import PdfWriter

from document_intake import extract_document


class DocumentIntakeTests(unittest.TestCase):
    def test_csv_extracts_text_without_classifying_columns(self):
        result = extract_document(
            "io.csv",
            b"Tag,Signal,Address\nLS1,Clamp extended,I0.0\n",
        )

        self.assertEqual(result["status"], "text_extracted")
        self.assertIn("LS1", result["extracted_text"])
        self.assertIn("columns are not automatically classified", result["source_note"])

    def test_xlsx_extracts_cell_values(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "IO List"
        sheet.append(["Tag", "Signal", "Address"])
        sheet.append(["LS1", "Clamp extended", "I0.0"])
        buffer = BytesIO()
        workbook.save(buffer)
        workbook.close()

        result = extract_document("io.xlsx", buffer.getvalue())

        self.assertEqual(result["status"], "text_extracted")
        self.assertIn("LS1", result["extracted_text"])
        self.assertEqual(result["metadata"]["sheet_names"], ["IO List"])

    def test_dxf_extracts_text_entities_and_disclaims_geometry(self):
        drawing = ezdxf.new()
        drawing.modelspace().add_text("V1", dxfattribs={"layer": "VALVES"})
        buffer = StringIO()
        drawing.write(buffer)

        result = extract_document("C:\\private\\diagram.dxf", buffer.getvalue().encode())

        self.assertEqual(result["filename"], "diagram.dxf")
        self.assertEqual(result["status"], "text_extracted")
        self.assertIn("[VALVES] V1", result["extracted_text"])
        self.assertIn("connectivity", result["source_note"])

    def test_pdf_without_text_requires_manual_review(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buffer = BytesIO()
        writer.write(buffer)

        result = extract_document("scanned.pdf", buffer.getvalue())

        self.assertEqual(result["status"], "manual_review_required")
        self.assertEqual(result["metadata"]["page_count"], 1)

    def test_image_is_accepted_but_not_ocr_processed(self):
        result = extract_document("diagram.png", b"not parsed by this test")

        self.assertEqual(result["status"], "manual_review_required")
        self.assertIn("OCR is not enabled", result["source_note"])

    def test_dwg_is_not_supported(self):
        result = extract_document("drawing.dwg", b"binary drawing")

        self.assertEqual(result["status"], "unsupported")
        self.assertIn("DWG", result["source_note"])

    def test_invalid_xlsx_is_reported_without_exposing_exception(self):
        result = extract_document("broken.xlsx", b"not a workbook")

        self.assertEqual(result["status"], "extraction_error")
        self.assertEqual(result["extracted_text"], "")
        self.assertNotIn("Traceback", result["source_note"])


if __name__ == "__main__":
    unittest.main()
