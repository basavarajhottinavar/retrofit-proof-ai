import csv
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

import ezdxf
from pypdf import PdfReader
from openpyxl import load_workbook

MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
MAX_DOCUMENT_COUNT = 8
MAX_EXTRACTED_CHARACTERS = 16000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 2000

SUPPORTED_TEXT_TYPES = {".pdf", ".xlsx", ".csv", ".dxf"}
SUPPORTED_IMAGE_TYPES = {".png", ".jpg", ".jpeg"}


def _safe_filename(filename: str) -> str:
    return Path(filename.replace("\\", "/")).name[:260] or "unnamed"


def _bounded_result(
    filename: str,
    extension: str,
    text: str,
    note: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    truncated = len(text) > MAX_EXTRACTED_CHARACTERS
    if truncated:
        text = text[:MAX_EXTRACTED_CHARACTERS]
        note = f"{note} Extracted text was truncated for review."

    return {
        "filename": _safe_filename(filename),
        "file_type": extension.lstrip(".") or "unknown",
        "status": "text_extracted" if text.strip() else "manual_review_required",
        "extracted_text": text,
        "source_note": note,
        "metadata": {**(metadata or {}), "text_truncated": truncated},
    }


def _validate_ooxml_archive(content: bytes) -> None:
    with ZipFile(BytesIO(content)) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        uncompressed_bytes = sum(entry.file_size for entry in entries)
        if len(entries) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("Workbook contains too many internal files.")
        if uncompressed_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
            raise ValueError("Workbook expands beyond the safe processing limit.")
        if any(entry.file_size > 0 and entry.compress_size == 0 for entry in entries):
            raise ValueError("Workbook contains an invalid compressed entry.")
        if any(
            entry.compress_size > 0 and entry.file_size / entry.compress_size > 200
            for entry in entries
        ):
            raise ValueError("Workbook compression ratio exceeds the safe limit.")


def _extract_pdf(filename: str, extension: str, content: bytes) -> dict[str, Any]:
    reader = PdfReader(BytesIO(content), strict=False)
    if reader.is_encrypted:
        return _bounded_result(
            filename,
            extension,
            "",
            "Encrypted PDF could not be read. Review it manually in an approved viewer.",
            {"page_count": len(reader.pages)},
        )

    page_text = []
    for page_number, page in enumerate(reader.pages[:100], start=1):
        text = page.extract_text() or ""
        if text.strip():
            page_text.append(f"[Page {page_number}]\n{text.strip()}")

    note = (
        "Text-layer extraction only. Verify each value against the original drawing; "
        "scanned pages and symbols are not interpreted."
    )
    return _bounded_result(
        filename,
        extension,
        "\n\n".join(page_text),
        note,
        {"page_count": len(reader.pages), "pages_scanned": min(len(reader.pages), 100)},
    )


def _extract_xlsx(filename: str, extension: str, content: bytes) -> dict[str, Any]:
    _validate_ooxml_archive(content)
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    try:
        lines = []
        sheet_names = []
        truncated_rows = False
        for sheet in workbook.worksheets[:20]:
            sheet_names.append(sheet.title)
            if sheet.max_row > 5000 or sheet.max_column > 100:
                truncated_rows = True
            for row_number, row in enumerate(
                sheet.iter_rows(
                    min_row=1,
                    max_row=min(sheet.max_row or 1, 5000),
                    max_col=min(sheet.max_column or 1, 100),
                ),
                start=1,
            ):
                values = [
                    f"{cell.coordinate}={str(cell.value).strip()}"
                    for cell in row
                    if cell.value is not None and str(cell.value).strip()
                ]
                if values:
                    lines.append(f"[{sheet.title} row {row_number}] " + " | ".join(values))
                if sum(map(len, lines)) > MAX_EXTRACTED_CHARACTERS:
                    truncated_rows = True
                    break
            if sum(map(len, lines)) > MAX_EXTRACTED_CHARACTERS:
                break

        note = "Workbook cell text extracted for manual correction; formulas are not recalculated."
        if truncated_rows:
            note += " Workbook rows or extracted text were truncated to processing limits."
        return _bounded_result(
            filename,
            extension,
            "\n".join(lines),
            note,
            {"sheet_names": sheet_names},
        )
    finally:
        workbook.close()


def _extract_csv(filename: str, extension: str, content: bytes) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = content.decode("cp1252")

    lines = []
    for row_number, row in enumerate(csv.reader(StringIO(decoded)), start=1):
        values = [value.strip() for value in row if value.strip()]
        if values:
            lines.append(f"[Row {row_number}] " + " | ".join(values))
        if sum(map(len, lines)) > MAX_EXTRACTED_CHARACTERS:
            break

    return _bounded_result(
        filename,
        extension,
        "\n".join(lines),
        "CSV text extracted for manual correction; columns are not automatically classified.",
    )


def _extract_dxf(filename: str, extension: str, content: bytes) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        decoded = content.decode("cp1252")

    drawing = ezdxf.read(StringIO(decoded))
    lines = []
    entity_counts: dict[str, int] = {}
    for entity in drawing.modelspace():
        entity_type = entity.dxftype()
        entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
        text = None
        if entity_type in {"TEXT", "ATTRIB", "ATTDEF"}:
            text = entity.dxf.get("text")
        elif entity_type == "MTEXT":
            text = entity.text
        if text:
            layer = entity.dxf.get("layer", "0")
            lines.append(f"[{layer}] {str(text).replace(chr(92) + 'P', ' ').strip()}")

    return _bounded_result(
        filename,
        extension,
        "\n".join(lines),
        "DXF text entities and counts extracted only. Geometry, pneumatic connectivity, symbols, and safety function are not interpreted.",
        {"entity_counts": entity_counts},
    )


def extract_document(filename: str, content: bytes) -> dict[str, Any]:
    safe_name = _safe_filename(filename)
    extension = Path(safe_name).suffix.lower()
    if not content:
        return _bounded_result(safe_name, extension, "", "File is empty.")

    if len(content) > MAX_DOCUMENT_BYTES:
        return _bounded_result(
            safe_name,
            extension,
            "",
            f"File exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)} MB per-file limit.",
        )

    if extension in SUPPORTED_IMAGE_TYPES:
        return _bounded_result(
            safe_name,
            extension,
            "",
            "Image accepted, but OCR is not enabled. Transcribe and verify it manually.",
        )
    if extension not in SUPPORTED_TEXT_TYPES:
        return {
            "filename": safe_name,
            "file_type": extension.lstrip(".") or "unknown",
            "status": "unsupported",
            "extracted_text": "",
            "source_note": "This file type is not parsed. DWG files are not supported.",
            "metadata": {},
        }

    try:
        if extension == ".pdf":
            return _extract_pdf(safe_name, extension, content)
        if extension == ".xlsx":
            return _extract_xlsx(safe_name, extension, content)
        if extension == ".csv":
            return _extract_csv(safe_name, extension, content)
        return _extract_dxf(safe_name, extension, content)
    except (BadZipFile, ValueError, OSError, UnicodeError, ezdxf.DXFError):
        return {
            "filename": safe_name,
            "file_type": extension.lstrip("."),
            "status": "extraction_error",
            "extracted_text": "",
            "source_note": "Local text extraction failed. Review the original file manually.",
            "metadata": {},
        }
    except Exception:
        return {
            "filename": safe_name,
            "file_type": extension.lstrip("."),
            "status": "extraction_error",
            "extracted_text": "",
            "source_note": "Local text extraction failed. Review the original file manually.",
            "metadata": {},
        }