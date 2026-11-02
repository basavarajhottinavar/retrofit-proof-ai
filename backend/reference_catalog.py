from pathlib import Path
import re
from typing import Any

from openpyxl import load_workbook

DATA_DIR = Path(__file__).resolve().parent / "data" / "testing"
CPE_REFERENCE_FILE = "CPE_VUVG_Reference_list.xlsx"
DNG_REFERENCE_FILE = "Referenzliste DNG 160-200.xlsx"
REVIEW_NOTICE = (
    "This is an unverified local source reference, not a compatibility approval. "
    "Confirm current status and application fit with an engineer."
)


def _part_number(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip().upper()


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _load_cpe_references(path: Path) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if "Tabelle1" not in workbook.sheetnames:
            return []

        sheet = workbook["Tabelle1"]
        family = None
        function = None
        context: dict[str, Any] = {}
        records = []
        for row_number, row in enumerate(sheet.iter_rows(min_row=2, max_col=17, values_only=True), start=2):
            heading = _text(row[1])
            if heading and heading.lower().startswith("solenoid valves"):
                family = heading
                function = None
                context = {}
            elif heading and re.match(r"^\d/\d-way", heading, flags=re.IGNORECASE):
                function = heading

            legacy_part_number = _part_number(row[5])
            if not legacy_part_number:
                continue

            for key, value in zip(
                ("pilot_air_supply", "plug_socket", "voltage", "connection"),
                row[1:5],
            ):
                if _text(value):
                    context[key] = value

            candidates = []
            for part_column, type_column, note_column in ((9, 10, 11), (14, 15, 16)):
                candidate_part = _part_number(row[part_column])
                if candidate_part:
                    candidates.append(
                        {
                            "part_number": candidate_part,
                            "product_type": _text(row[type_column]),
                            "note": _text(row[note_column]),
                        }
                    )

            records.append(
                {
                    "source_file": path.name,
                    "source_sheet": sheet.title,
                    "source_row": row_number,
                    "legacy_part_number": legacy_part_number,
                    "legacy_description": _text(row[6]),
                    "family_or_function": " / ".join(value for value in (family, function) if value),
                    "technical_context": {key: _text(value) for key, value in context.items()},
                    "source_status": None,
                    "source_comment": None,
                    "candidates": candidates,
                    "review_notice": REVIEW_NOTICE,
                }
            )
        return records
    finally:
        workbook.close()


def _load_dng_references(path: Path) -> list[dict[str, Any]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        records = []
        for row_number, row in enumerate(sheet.iter_rows(min_row=4, max_col=16, values_only=True), start=4):
            legacy_part_number = _part_number(row[0])
            if not legacy_part_number:
                continue

            candidates = []
            replacement_part_number = _part_number(row[5])
            if replacement_part_number:
                candidates.append(
                    {
                        "part_number": replacement_part_number,
                        "product_type": _text(row[6]),
                        "note": _text(row[13]),
                    }
                )

            records.append(
                {
                    "source_file": path.name,
                    "source_sheet": sheet.title,
                    "source_row": row_number,
                    "legacy_part_number": legacy_part_number,
                    "legacy_description": _text(row[1]),
                    "family_or_function": None,
                    "technical_context": {},
                    "source_status": _text(row[2]),
                    "source_comment": _text(row[13]),
                    "candidates": candidates,
                    "review_notice": REVIEW_NOTICE,
                }
            )
        return records
    finally:
        workbook.close()


def lookup_legacy_references(
    part_numbers: list[str], data_dir: Path = DATA_DIR
) -> tuple[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = {}
    loaded_files = 0

    for filename, loader in (
        (CPE_REFERENCE_FILE, _load_cpe_references),
        (DNG_REFERENCE_FILE, _load_dng_references),
    ):
        path = data_dir / filename
        if path.is_file():
            loaded_files += 1
            for record in loader(path):
                index.setdefault(record["legacy_part_number"], []).append(record)

    data_status = "loaded" if loaded_files == 2 else "partially_loaded" if loaded_files else "not_available"
    lookups = []
    for requested in dict.fromkeys(_part_number(item) for item in part_numbers if _part_number(item)):
        records = index.get(requested, [])
        lookups.append(
            {
                "query": requested,
                "found": bool(records),
                "records": records,
                "review_notice": REVIEW_NOTICE,
            }
        )
    return data_status, lookups