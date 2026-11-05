import json
import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from gemini_document import suggest_festo_replacements

DATA_DIR = Path(__file__).resolve().parent / "data" / "testing"
OFFICIAL_FACTS_FILE = "festo_official_facts.json"
REVIEW_NOTICE = (
    "Workbook references are historical, unsigned, and unverified for current "
    "application fit. Engineer approval is required."
)
_REVIEW_TERMS = (
    "confirm",
    "check compatibility",
    "based on equivalent",
    "no festo equivalent",
    "please provide technical details",
)


def _value_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if not text or text.upper() in {"NA", "N/A", "0", "0.0"}:
        return None
    return text


def _contains_exact_code(text: str, code: str) -> bool:
    return bool(
        re.search(
            rf"(?<![A-Z0-9-]){re.escape(code.upper())}(?![A-Z0-9-])",
            text.upper(),
        )
    )


def _project_rows(path: Path) -> tuple[str, list[dict[str, Any]]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        rows = sheet.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else "" for value in next(rows, ())]
        required = {
            "SL.NO",
            "Competitor",
            "Original code",
            "Description",
            "Festo part number",
            "Festo type code",
            "Sign",
            "Remarks",
            "FoundinCRT:Yes/No/NA",
        }
        if not required.issubset(headers):
            return "invalid_workbook", []

        indexes = {header: headers.index(header) for header in required}
        records = []
        for row_number, row in enumerate(rows, start=2):
            if not any(value is not None and str(value).strip() for value in row):
                continue

            def value(column: str) -> Any:
                index = indexes[column]
                return row[index] if index < len(row) else None

            remarks = _value_text(value("Remarks")) or ""
            item_match = re.search(r"\bdrawing item\s+(\d+)\b", remarks, re.IGNORECASE)
            original_code = _value_text(value("Original code"))
            festo_part_number = _value_text(value("Festo part number"))
            festo_type_code = _value_text(value("Festo type code"))
            caveats = [
                term
                for term in _REVIEW_TERMS
                if term in remarks.casefold()
            ]

            if not festo_part_number and not festo_type_code:
                reference_status = "no_candidate_recorded"
            elif caveats:
                reference_status = "provisional_reference"
            else:
                reference_status = "source_listed_unverified"

            records.append(
                {
                    "source_file": path.name,
                    "source_sheet": sheet.title,
                    "source_row": row_number,
                    "drawing_item": int(item_match.group(1)) if item_match else None,
                    "legacy_part_number": original_code,
                    "description": _value_text(value("Description")),
                    "competitor": _value_text(value("Competitor")),
                    "festo_part_number": festo_part_number,
                    "festo_type_code": festo_type_code,
                    "source_sign": _value_text(value("Sign")),
                    "source_signoff_present": bool(_value_text(value("Sign"))),
                    "found_in_crt_source_value": _value_text(value("FoundinCRT:Yes/No/NA")),
                    "source_remarks": remarks or None,
                    "review_caveats": caveats,
                    "reference_status": reference_status,
                    "requires_engineer_review": True,
                }
            )
        return "loaded", records
    finally:
        workbook.close()


def _normalize_project_key(value: str) -> str:
    stem = Path(value).stem.casefold().strip()
    stem = re.sub(r"^(?:project|projekt)[\s_.-]*", "", stem)
    stem = re.sub(
        r"[\s_.-]+(?:parts?|crosswalk|bom|diagram|drawing|schematic)(?:[\s_.-].*)?$",
        "",
        stem,
    )
    return re.sub(r"[^a-z0-9]+", "", stem)


def _project_keys_from_text(text: str) -> set[str]:
    keys = set()
    for line in text.splitlines():
        match = re.match(r"\s*(?:project|projekt)\s*[:#-]\s*(.+?)\s*$", line, re.IGNORECASE)
        if match:
            identifier = re.split(
                r"\s+(?:vypracoval|prepared\s+by|drawn\s+by|author|date)\s*[:#-]?\s*",
                match.group(1),
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
            key = _normalize_project_key(identifier)
            if key:
                keys.add(key)
    return keys


def _project_keys_for_workbook(path: Path, records: list[dict[str, Any]]) -> set[str]:
    keys = {_normalize_project_key(path.name)}
    for record in records:
        match = re.search(
            r"\bproject\s+([a-z0-9]+(?:[-_][a-z0-9]+)*)",
            record.get("source_remarks") or "",
            re.IGNORECASE,
        )
        if match:
            keys.add(_normalize_project_key(match.group(1)))
    return {key for key in keys if key}


def _matching_project_workbooks(
    filename: str, extracted_text: str, data_dir: Path
) -> tuple[str | None, list[tuple[Path, list[dict[str, Any]]]], str | None]:
    candidates = []
    for path in data_dir.glob("*.xlsx"):
        status, records = _project_rows(path)
        if status == "loaded":
            candidates.append((path, records, _project_keys_for_workbook(path, records)))

    if not candidates:
        return None, [], "not_available"

    filename_key = _normalize_project_key(filename)
    text_keys = _project_keys_from_text(extracted_text)
    filename_matches = [
        item for item in candidates if filename_key and filename_key in item[2]
    ]
    text_matches = [
        item for item in candidates if text_keys.intersection(item[2])
    ]

    if filename_matches and text_matches:
        filename_projects = set().union(*(item[2] for item in filename_matches))
        text_projects = set().union(*(item[2] for item in text_matches))
        common_projects = filename_projects.intersection(text_projects)
        if not common_projects:
            return None, [], "identifier_mismatch"
        matches = [
            item for item in candidates if item[2].intersection(common_projects)
        ]
    elif text_matches:
        matches = text_matches
    else:
        matches = filename_matches

    matched_projects = set().union(*(item[2] for item in matches)) if matches else set()
    if not matches:
        return None, [], None
    if len(matched_projects) > 1:
        return None, [], "ambiguous_project_identifier"

    project_id = next(iter(matched_projects))
    selected = [(path, records) for path, records, _ in matches]
    return project_id, selected, None


def _official_product_facts(data_dir: Path) -> dict[str, dict[str, Any]]:
    path = data_dir / OFFICIAL_FACTS_FILE
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        products = payload.get("products", [])
        return {
            str(product["part_number"]).strip(): {
                **product,
                "dataset_source": OFFICIAL_FACTS_FILE,
                "retrieved_on": payload.get("retrieved_on"),
                "source_region": payload.get("source_region"),
            }
            for product in products
            if product.get("part_number")
        }
    except (OSError, ValueError, TypeError, KeyError):
        return {}


def _product_reference(
    official_facts: dict[str, dict[str, Any]],
    part_number: str | None,
    type_code: str | None = None,
) -> dict[str, Any] | None:
    if not part_number:
        return None
    normalized_part = str(part_number).strip()
    if normalized_part in official_facts:
        return official_facts[normalized_part]
    return {
        "part_number": normalized_part,
        "type_code": type_code or "",
        "product_name": f"Festo product {normalized_part}",
        "product_family": "Festo reference",
        "technical_data": {},
        "product_page": f"https://www.festo.com/us/en/a/{normalized_part}/",
        "datasheet": f"https://www.festo.com/us/en/a/download-document/datasheet/{normalized_part}",
        "regional_availability": "not_verified",
        "compatibility_status": "not_assessed",
        "dataset_source": OFFICIAL_FACTS_FILE,
        "retrieved_on": None,
        "source_region": "Festo reference; detailed public facts are not recorded in the current dataset",
    }


def _normalize_component_query(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def lookup_project_component_names(
    queries: list[str], data_dir: Path = DATA_DIR
) -> list[dict[str, Any]]:
    workbooks = []
    for path in data_dir.glob("*.xlsx"):
        status, records = _project_rows(path)
        if status != "loaded":
            continue
        project_ids = _project_keys_for_workbook(path, records)
        project_id = sorted(project_ids)[0] if project_ids else None
        workbooks.append((path, project_id, records))

    official_facts = _official_product_facts(data_dir)
    results = []
    for query in dict.fromkeys(item.strip() for item in queries if item.strip()):
        normalized_query = _normalize_component_query(query)
        compact_query = normalized_query.replace(" ", "")
        matches = []

        if normalized_query:
            for path, project_id, records in workbooks:
                for source_record in records:
                    code = source_record["legacy_part_number"] or ""
                    description = source_record["description"] or ""
                    normalized_code = _normalize_component_query(code).replace(" ", "")
                    normalized_description = _normalize_component_query(description)

                    if compact_query == normalized_code and normalized_code:
                        match_type = "exact_part_number"
                    elif normalized_query == normalized_description and normalized_description:
                        match_type = "exact_component_name"
                    elif f" {normalized_query} " in f" {normalized_description} ":
                        match_type = "description_phrase"
                    else:
                        continue

                    matches.append(
                        {
                            "project_id": project_id,
                            **source_record,
                            "match_type": match_type,
                            "official_festo_product": _product_reference(
                                official_facts,
                                source_record["festo_part_number"],
                                source_record["festo_type_code"],
                            ),
                            "review_notice": REVIEW_NOTICE,
                        }
                    )

        matches.sort(
            key=lambda item: (
                {"exact_part_number": 0, "exact_component_name": 1, "description_phrase": 2}[item["match_type"]],
                item["project_id"] or "",
                item["source_file"],
                item["source_row"],
            )
        )
        results.append(
            {
                "query": query,
                "status": "matched" if matches else "no_match" if workbooks else "not_available",
                "matches_truncated": len(matches) > 50,
                "matches": matches[:50],
                "review_notice": (
                    "Matches use exact normalized part numbers or exact phrases within source descriptions. "
                    "They are not compatibility approvals."
                ),
            }
        )
    return results


def _drawing_item_lines(text: str) -> dict[int, str]:
    items = {}
    for line in text.splitlines():
        match = re.match(r"\s*(\d{1,3})\s*:\s*(.*?)\s*$", line)
        if match:
            items[int(match.group(1))] = match.group(2).strip()
    return items


def _component_code(component: dict[str, Any]) -> str | None:
    description = str(component.get("description") or "")
    # Prefer the manufacturer code printed in BOM descriptions (for example
    # "cod. NPQM-L-Q10-E-P10") over customer/internal ERP codes.
    match = re.search(
        r"\bcod(?:ice)?\.?\s*[:=]?\s*([A-Z0-9][A-Z0-9./+-]*(?:-[A-Z0-9./+-]+)+)",
        description,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    supplied = _value_text(component.get("part_number"))
    return supplied


def _generic_ai_reconciliation(
    filename: str,
    data_dir: Path,
    ai_analysis: dict[str, Any],
) -> dict[str, Any]:
    workbook_matches = []
    for path in data_dir.glob("*.xlsx"):
        status, records = _project_rows(path)
        if status == "loaded":
            workbook_matches.extend((path, record) for record in records)

    official_facts = _official_product_facts(data_dir)
    records = []
    for component in ai_analysis.get("components", []):
        legacy_code = _component_code(component)
        description = _value_text(component.get("description"))
        component_type = _value_text(component.get("component_type"))
        normalized_code = _normalize_component_query(legacy_code or "")
        normalized_description = _normalize_component_query(description or "")
        workbook_record = None
        match_type = "ai_extracted"

        for _, source_record in workbook_matches:
            source_code = _normalize_component_query(source_record["legacy_part_number"] or "")
            source_description = _normalize_component_query(source_record["description"] or "")
            if normalized_code and source_code and normalized_code == source_code:
                workbook_record = source_record
                match_type = "exact_workbook_part_number"
                break
            if normalized_description and source_description and normalized_description == source_description:
                workbook_record = source_record
                match_type = "exact_workbook_description"
                break

        record = {
            "drawing_item": component.get("callout_no"),
            "legacy_part_number": legacy_code,
            "description": description,
            "component_type": component_type,
            "manufacturer": _value_text(component.get("manufacturer")),
            "competitor": (
                workbook_record["competitor"] if workbook_record else _value_text(component.get("manufacturer"))
            ),
            "festo_part_number": workbook_record["festo_part_number"] if workbook_record else None,
            "festo_type_code": workbook_record["festo_type_code"] if workbook_record else None,
            "source_file": workbook_record["source_file"] if workbook_record else None,
            "source_sheet": workbook_record["source_sheet"] if workbook_record else None,
            "source_row": workbook_record["source_row"] if workbook_record else None,
            "source_remarks": workbook_record["source_remarks"] if workbook_record else None,
            "reference_status": workbook_record["reference_status"] if workbook_record else match_type,
            "match_type": match_type,
            "diagram_item_text": legacy_code,
            "diagram_match_status": match_type,
            "requires_engineer_review": True,
            "confidence": component.get("confidence"),
            "review_notice": REVIEW_NOTICE,
            "official_festo_product": _product_reference(
                official_facts,
                workbook_record["festo_part_number"] if workbook_record else None,
                workbook_record["festo_type_code"] if workbook_record else None,
            ),
        }
        records.append(record)

    ai_suggestions = suggest_festo_replacements(records)
    suggestions_by_code = {
        suggestion.get("legacy_part_number"): suggestion
        for suggestion in ai_suggestions
        if suggestion.get("legacy_part_number")
    }
    for record in records:
        suggestion = suggestions_by_code.get(record.get("legacy_part_number"))
        if suggestion:
            record["latest_festo_suggestion"] = suggestion

    return {
        "project_id": _normalize_project_key(filename) or None,
        "status": "ai_text_reconciled" if records else "ai_unavailable",
        "source_files": sorted({record["source_file"] for record in records if record["source_file"]}),
        "source_sheet": None,
        "source_signoff_present": False,
        "total_source_lines": len(records),
        "diagram_match_counts": {"ai_extracted": len(records)},
        "gemini_festo_suggestions": ai_suggestions,
        "records": records,
        "review_notice": REVIEW_NOTICE,
    }


def reconcile_project(
    filename: str,
    extracted_text: str,
    data_dir: Path = DATA_DIR,
    ai_analysis: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    project_id, workbooks, resolution_error = _matching_project_workbooks(
        filename, extracted_text, data_dir
    )
    if resolution_error:
        return {
            "project_id": None,
            "status": resolution_error,
            "source_files": [],
            "records": [],
            "review_notice": REVIEW_NOTICE,
        }
    if not workbooks or project_id is None:
        return _generic_ai_reconciliation(filename, data_dir, ai_analysis) if ai_analysis else None

    records = [record for _, workbook_records in workbooks for record in workbook_records]
    official_facts = _official_product_facts(data_dir)
    item_lines = _drawing_item_lines(extracted_text)
    upper_text = extracted_text.upper()
    ai_callouts: dict[int, str] = {}
    if ai_analysis:
        for raw_item, code in (ai_analysis.get("text_callouts") or {}).items():
            try:
                ai_callouts[int(raw_item)] = str(code).strip()
            except (TypeError, ValueError):
                continue
        for component in ai_analysis.get("components", []):
            item_number = component.get("callout_no")
            code = component.get("part_number")
            if item_number is not None and code:
                try:
                    ai_callouts.setdefault(int(item_number), str(code))
                except (TypeError, ValueError):
                    continue

    for record in records:
        item_number = record["drawing_item"]
        code = record["legacy_part_number"]
        item_text = item_lines.get(item_number) if item_number is not None else None
        ai_item_text = ai_callouts.get(item_number) if item_number is not None else None
        if ai_item_text and not item_text:
            item_text = ai_item_text
            record["diagram_item_text_source"] = "gemini_reconciled"

        if item_text and not code:
            diagram_status = "drawing_item_present_code_unavailable"
        elif item_text and code and _contains_exact_code(item_text, code):
            diagram_status = "exact_code_and_item_match"
        elif item_text and code:
            diagram_status = "drawing_item_code_mismatch"
        elif code and _contains_exact_code(upper_text, code):
            diagram_status = "exact_code_found_without_item_number"
        elif extracted_text.strip():
            diagram_status = "not_found_in_text_layer"
        else:
            diagram_status = "not_evaluated_no_text_layer"

        record["diagram_item_text"] = item_text
        record["diagram_match_status"] = diagram_status
        record["review_notice"] = REVIEW_NOTICE
        record["official_festo_product"] = _product_reference(
            official_facts,
            record["festo_part_number"],
            record["festo_type_code"],
        )

    ai_suggestions = suggest_festo_replacements(records) if ai_analysis else []
    suggestion_by_code = {
        suggestion.get("legacy_part_number"): suggestion
        for suggestion in ai_suggestions
        if suggestion.get("legacy_part_number")
    }
    for record in records:
        suggestion = suggestion_by_code.get(record.get("legacy_part_number"))
        if suggestion:
            record["latest_festo_suggestion"] = suggestion

    counts: dict[str, int] = {}
    for record in records:
        status = record["diagram_match_status"]
        counts[status] = counts.get(status, 0) + 1

    return {
        "project_id": project_id,
        "status": "text_reconciled" if extracted_text.strip() else "manual_review_required",
        "source_files": [path.name for path, _ in workbooks],
        "source_sheet": records[0]["source_sheet"] if records else None,
        "source_signoff_present": any(record["source_signoff_present"] for record in records),
        "total_source_lines": len(records),
        "official_product_facts_status": "loaded" if official_facts else "not_available",
        "official_product_facts_count": len(official_facts),
        "diagram_match_counts": counts,
        "gemini_festo_suggestions": ai_suggestions,
        "records": records,
        "review_notice": REVIEW_NOTICE,
    }