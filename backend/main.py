from io import BytesIO
import json
import os
from typing import Literal
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font


class AiReview(BaseModel):
    enabled: bool
    provider: str
    summary: str
    risks: list[str]


def ai_review_intake(request: "AssessmentRequest", missing: list[str], bom_preview: list["BomPreviewItem"]) -> AiReview:
    fallback = AiReview(
        enabled=False,
        provider="deterministic fallback",
        summary="AI review is unavailable; deterministic engineering checks remain active.",
        risks=[item for item in missing[:8]],
    )
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return fallback

    try:
        from openai import OpenAI

        prompt = {
            "project_name": request.project_name,
            "application": request.application,
            "pressure_bar": request.operating_pressure_bar,
            "cycle_rate_per_min": request.target_cycle_rate_per_min,
            "observed_components": request.observed_components,
            "legacy_part_numbers": request.legacy_part_numbers,
            "known_unknowns": request.known_unknowns,
            "missing_information": missing,
            "candidate_bom": [
                item.model_dump(exclude={"disposition"}) for item in bom_preview[:30]
            ],
        }
        response = OpenAI(api_key=api_key).chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a pneumatic retrofit review assistant. Return JSON with "
                        "\"summary\" and \"risks\" keys. Do not approve parts or design. "
                        "Identify engineering unknowns, missing safety data, compatibility "
                        "questions, and commissioning risks. Risks must be short strings."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        return AiReview(
            enabled=True,
            provider="OpenAI",
            summary=str(payload.get("summary", "AI review completed."))[:1000],
            risks=[str(item) for item in payload.get("risks", [])[:12]],
        )
    except Exception:
        return fallback

from reference_catalog import lookup_legacy_references
from document_intake import (
    MAX_DOCUMENT_BYTES,
    MAX_DOCUMENT_COUNT,
    extract_document,
)
from project_reconciliation import lookup_project_component_names

app = FastAPI(title="RetrofitProof AI", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class AssessmentRequest(BaseModel):
    project_name: str = Field(min_length=1, max_length=120)
    application: str = Field(min_length=1, max_length=200)
    operating_pressure_bar: float | None = Field(default=None, gt=0)
    target_cycle_rate_per_min: float | None = Field(default=None, gt=0)
    diagram_available: bool = False
    io_list_available: bool = False
    observed_components: list[str] = Field(default_factory=list, max_length=40)
    legacy_part_numbers: list[str] = Field(default_factory=list, max_length=40)
    legacy_component_names: list[str] = Field(default_factory=list, max_length=40)
    source_documents: list["SourceDocumentEvidence"] = Field(default_factory=list, max_length=8)
    known_unknowns: list[str] = Field(default_factory=list, max_length=30)
    current_quote_hours: float | None = Field(default=None, ge=0)
    estimated_quote_hours: float | None = Field(default=None, ge=0)
    engineering_hourly_cost_inr: float | None = Field(default=None, ge=0)


class RoiEstimate(BaseModel):
    engineering_hours_saved: float
    estimated_cost_savings_inr: float


class BomPreviewItem(BaseModel):
    legacy_part_number: str | None = None
    description: str | None = None
    festo_part_number: str | None = None
    festo_type_code: str | None = None
    quantity: int = 1
    review_status: str
    disposition: Literal["engineer_review_required"] = "engineer_review_required"


class ValidationTest(BaseModel):
    phase: Literal["FAT", "SAT"]
    test_id: str
    title: str
    acceptance_criteria: str
    safety_note: str


class ReferenceCandidate(BaseModel):
    part_number: str
    product_type: str | None = None
    note: str | None = None


class LocalReferenceRecord(BaseModel):
    source_file: str
    source_sheet: str
    source_row: int
    legacy_part_number: str
    legacy_description: str | None = None
    family_or_function: str | None = None
    technical_context: dict[str, str | None]
    source_status: str | None = None
    source_comment: str | None = None
    candidates: list[ReferenceCandidate]
    review_notice: str


class ReferenceLookup(BaseModel):
    query: str
    found: bool
    records: list[LocalReferenceRecord]
    review_notice: str


class ComponentNameMatch(BaseModel):
    project_id: str | None = None
    source_file: str
    source_sheet: str
    source_row: int
    drawing_item: int | None = None
    legacy_part_number: str | None = None
    description: str | None = None
    competitor: str | None = None
    festo_part_number: str | None = None
    festo_type_code: str | None = None
    source_remarks: str | None = None
    reference_status: str
    match_type: Literal["exact_part_number", "exact_component_name", "description_phrase"]
    official_festo_product: dict[str, Any] | None = None
    review_notice: str


class ComponentNameLookup(BaseModel):
    query: str
    status: Literal["matched", "no_match", "not_available"]
    matches_truncated: bool
    matches: list[ComponentNameMatch]
    review_notice: str


class SourceDocumentEvidence(BaseModel):
    filename: str = Field(max_length=260)
    file_type: str = Field(max_length=12)
    status: Literal["text_extracted", "manual_review_required", "unsupported", "extraction_error"]
    extracted_text: str = Field(default="", max_length=16000)
    source_note: str = Field(max_length=500)
    project_reconciliation: dict[str, Any] | None = None


class SourceDocumentSummary(BaseModel):
    filename: str
    file_type: str
    status: Literal["text_extracted", "manual_review_required", "unsupported", "extraction_error"]
    source_note: str
    project_reconciliation: dict[str, Any] | None = None


class AssessmentResponse(BaseModel):
    assessment_id: str
    status: Literal["information_incomplete", "awaiting_engineer_review"]
    requires_engineer_review: Literal[True] = True
    summary: str
    missing_information: list[str]
    known_unknowns: list[str]
    reference_data_status: Literal["loaded", "partially_loaded", "not_available"]
    reference_lookups: list[ReferenceLookup]
    component_name_lookups: list[ComponentNameLookup]
    source_documents: list[SourceDocumentSummary]
    review_checklist: list[str]
    bom_status: Literal["not_generated"] = "not_generated"
    bom_note: str
    roi_estimate: RoiEstimate | None
    bom_preview: list[BomPreviewItem]
    validation_tests: list[ValidationTest]
    ai_review: AiReview


def _bom_preview(component_name_lookups: list[dict[str, Any]], reconciliation_records: list[dict[str, Any]]) -> list[BomPreviewItem]:
    items: dict[tuple[str, str, str], BomPreviewItem] = {}

    def add(legacy: Any, description: Any, festo_part: Any, festo_type: Any, status: Any) -> None:
        legacy_text = str(legacy or "").strip()
        description_text = str(description or "").strip()
        festo_text = str(festo_part or "").strip()
        festo_type_text = str(festo_type or "").strip()
        key = (legacy_text, festo_text, festo_type_text)
        if key in items:
            items[key].quantity += 1
            return
        items[key] = BomPreviewItem(
            legacy_part_number=legacy_text or None,
            description=description_text or None,
            festo_part_number=festo_text or None,
            festo_type_code=festo_type_text or None,
            review_status=str(status or "requires_engineer_review").replace("_", " "),
        )

    for lookup in component_name_lookups:
        for match in lookup["matches"]:
            add(match.get("legacy_part_number"), match.get("description"), match.get("festo_part_number"), match.get("festo_type_code"), match.get("reference_status"))
    for record in reconciliation_records:
        add(record.get("legacy_part_number"), record.get("description"), record.get("festo_part_number"), record.get("festo_type_code"), record.get("reference_status"))
    return list(items.values())


def assess_request(request: AssessmentRequest) -> AssessmentResponse:
    missing_information = []
    if not request.project_name.strip():
        missing_information.append("Project name")
    if not request.application.strip():
        missing_information.append("Machine application")
    if request.operating_pressure_bar is None:
        missing_information.append("Operating pressure")
    if request.target_cycle_rate_per_min is None:
        missing_information.append("Target cycle rate")
    if not request.diagram_available:
        missing_information.append("As-built pneumatic diagram")
    if not request.io_list_available:
        missing_information.append("As-built I/O list")
    if not any(component.strip() for component in request.observed_components):
        missing_information.append("Existing component inventory")

    reference_data_status, reference_lookups = lookup_legacy_references(
        request.legacy_part_numbers
    )
    component_name_lookups = lookup_project_component_names(
        [*request.legacy_part_numbers, *request.legacy_component_names]
    )

    roi_estimate = None
    roi_inputs = (
        request.current_quote_hours,
        request.estimated_quote_hours,
        request.engineering_hourly_cost_inr,
    )
    if all(value is not None for value in roi_inputs):
        hours_saved = request.current_quote_hours - request.estimated_quote_hours
        roi_estimate = RoiEstimate(
            engineering_hours_saved=round(hours_saved, 2),
            estimated_cost_savings_inr=round(
                hours_saved * request.engineering_hourly_cost_inr, 2
            ),
        )

    complete = not missing_information
    reconciliation_records = [
        record
        for document in request.source_documents
        if document.project_reconciliation
        for record in document.project_reconciliation.get("records", [])
    ]
    bom_preview = _bom_preview(
        [lookup.model_dump() if hasattr(lookup, "model_dump") else lookup for lookup in component_name_lookups],
        reconciliation_records,
    )
    validation_tests = [
        ValidationTest(
            phase="FAT",
            test_id="FAT-001",
            title="Valve switching and indication",
            acceptance_criteria="Each commanded valve reaches the approved state and returns the expected I/O indication.",
            safety_note="Use isolated compressed air and the approved lockout procedure.",
        ),
        ValidationTest(
            phase="FAT",
            test_id="FAT-002",
            title="Cylinder end-position verification",
            acceptance_criteria="Actuator reaches both approved end positions without impact, abnormal noise, or unintended drift.",
            safety_note="Keep personnel outside the guarded hazardous zone.",
        ),
        ValidationTest(
            phase="SAT",
            test_id="SAT-001",
            title="Automatic cycle and fail-safe response",
            acceptance_criteria="The machine completes repeated approved cycles and safe state behavior matches the validated sequence.",
            safety_note="Obtain machine-owner authorization and perform only under approved commissioning controls.",
        ),
        ValidationTest(
            phase="SAT",
            test_id="SAT-002",
            title="Pressure, leak, and flow verification",
            acceptance_criteria="Recorded operating pressure and observed leakage remain within the approved site limits.",
            safety_note="Pressure testing requires engineering approval and an appropriate exclusion zone.",
        ),
    ]
    return AssessmentResponse(
        assessment_id=str(uuid4()),
        status="awaiting_engineer_review" if complete else "information_incomplete",
        summary=(
            "Intake captured. Engineering review is required before retrofit decisions."
            if complete
            else "More information is needed before the retrofit scope can be reviewed."
        ),
        missing_information=missing_information,
        known_unknowns=[item.strip() for item in request.known_unknowns if item.strip()],
        reference_data_status=reference_data_status,
        reference_lookups=reference_lookups,
        component_name_lookups=component_name_lookups,
        source_documents=[
            SourceDocumentSummary(
                filename=document.filename,
                file_type=document.file_type,
                status=document.status,
                source_note=document.source_note,
                project_reconciliation=document.project_reconciliation,
            )
            for document in request.source_documents
        ],
        review_checklist=[
            "Verify pressure, flow, loads, and duty against current manufacturer data.",
            "Confirm fail-safe behavior and safety circuit with the responsible engineer.",
            "Validate electrical ratings, I/O signals, and network compatibility.",
            "Define acceptance criteria before any commissioning tests.",
        ],
        bom_note=(
            "Local cross-reference files may show historical alternatives, but they "
            "are not an approved product catalog. No compatibility or sizing "
            "recommendation is generated."
        ),
        roi_estimate=roi_estimate,
        bom_preview=bom_preview,
        validation_tests=validation_tests,
        ai_review=ai_review_intake(request, missing_information, bom_preview),
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/documents/extract")
async def extract_documents(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one document.")
    if len(files) > MAX_DOCUMENT_COUNT:
        raise HTTPException(
            status_code=413,
            detail=f"Upload no more than {MAX_DOCUMENT_COUNT} files at once.",
        )

    total_bytes = 0
    results = []
    for upload in files:
        try:
            content = await upload.read(MAX_DOCUMENT_BYTES + 1)
            total_bytes += len(content)
            if len(content) > MAX_DOCUMENT_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"{upload.filename or 'A file'} exceeds the per-file size limit.",
                )
            if total_bytes > MAX_DOCUMENT_BYTES * 3:
                raise HTTPException(status_code=413, detail="Combined upload is too large.")
            extraction = await run_in_threadpool(
                extract_document, upload.filename or "unnamed", content
            )
            results.append(extraction)
        finally:
            await upload.close()

    return {"documents": results, "stored": False}


@app.post("/assessments", response_model=AssessmentResponse)
def create_assessment(request: AssessmentRequest) -> AssessmentResponse:
    return assess_request(request)


@app.post("/assessments/export-xlsx")
def export_assessment_xlsx(payload: dict[str, Any]) -> StreamingResponse:
    assessment = payload.get("assessment")
    if not isinstance(assessment, dict):
        raise HTTPException(status_code=400, detail="Assessment data is required.")

    workbook = Workbook()
    worksheet = workbook.active
    export_type = str(payload.get("export_type", "crosswalk"))
    filename = "legacy-festo-crosswalk.xlsx"

    if export_type == "bom":
        worksheet.title = "Candidate BOM"
        worksheet.append([
            "Legacy part number", "Description", "Festo part number",
            "Festo type code", "Quantity", "Review status", "Disposition",
        ])
        for item in assessment.get("bom_preview", []):
            worksheet.append([
                item.get("legacy_part_number"), item.get("description"),
                item.get("festo_part_number"), item.get("festo_type_code"),
                item.get("quantity", 1), item.get("review_status"),
                item.get("disposition", "engineer_review_required"),
            ])
        filename = "candidate-bom.xlsx"
    elif export_type == "validation_tests":
        worksheet.title = "FAT SAT Plan"
        worksheet.append([
            "Phase", "Test ID", "Title", "Acceptance criteria", "Safety note",
        ])
        for test in assessment.get("validation_tests", []):
            worksheet.append([
                test.get("phase"), test.get("test_id"), test.get("title"),
                test.get("acceptance_criteria"), test.get("safety_note"),
            ])
        filename = "fat-sat-validation-plan.xlsx"
    else:
        worksheet.title = "Legacy and Festo"
        worksheet.append([
            "Legacy part number",
            "Legacy description",
            "Manufacturer",
            "Festo part number",
            "Festo type code",
            "Review status",
        ])

    seen_rows: set[tuple[str, str, str, str, str]] = set()

    def add_row(
        legacy_part_number: Any,
        description: Any,
        manufacturer: Any,
        festo_part_number: Any,
        festo_type_code: Any,
        review_status: Any,
    ) -> None:
        values = (
            str(legacy_part_number or "").strip(),
            str(description or "").strip(),
            str(manufacturer or "").strip(),
            str(festo_part_number or "").strip(),
            str(festo_type_code or "").strip(),
        )
        if not values[0] and not values[1]:
            return
        key = values
        if key in seen_rows:
            return
        seen_rows.add(key)
        worksheet.append([*values, str(review_status or "").replace("_", " ")])

    if export_type == "crosswalk":
        for lookup in assessment.get("component_name_lookups", []):
            for match in lookup.get("matches", []):
                add_row(
                    match.get("legacy_part_number"),
                    match.get("description"),
                    match.get("competitor"),
                    match.get("festo_part_number"),
                    match.get("festo_type_code"),
                    match.get("reference_status"),
                )

        for source in assessment.get("source_documents", []):
            reconciliation = source.get("project_reconciliation")
            if not isinstance(reconciliation, dict):
                continue
            for record in reconciliation.get("records", []):
                add_row(
                    record.get("legacy_part_number"),
                    record.get("description"),
                    record.get("competitor"),
                    record.get("festo_part_number"),
                    record.get("festo_type_code"),
                    record.get("reference_status"),
                )

    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
    for column in worksheet.columns:
        width = min(max(len(str(cell.value or "")) for cell in column) + 2, 50)
        worksheet.column_dimensions[column[0].column_letter].width = width

    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )