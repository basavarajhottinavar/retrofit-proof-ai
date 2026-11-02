from typing import Literal
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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
    known_unknowns: list[str] = Field(default_factory=list, max_length=30)
    current_quote_hours: float | None = Field(default=None, ge=0)
    estimated_quote_hours: float | None = Field(default=None, ge=0)
    engineering_hourly_cost_inr: float | None = Field(default=None, ge=0)


class RoiEstimate(BaseModel):
    engineering_hours_saved: float
    estimated_cost_savings_inr: float


class AssessmentResponse(BaseModel):
    assessment_id: str
    status: Literal["information_incomplete", "awaiting_engineer_review"]
    requires_engineer_review: Literal[True] = True
    summary: str
    missing_information: list[str]
    known_unknowns: list[str]
    review_checklist: list[str]
    bom_status: Literal["not_generated"] = "not_generated"
    bom_note: str
    roi_estimate: RoiEstimate | None


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
        review_checklist=[
            "Verify pressure, flow, loads, and duty against current manufacturer data.",
            "Confirm fail-safe behavior and safety circuit with the responsible engineer.",
            "Validate electrical ratings, I/O signals, and network compatibility.",
            "Define acceptance criteria before any commissioning tests.",
        ],
        bom_note=(
            "No approved product catalog is loaded. No part substitutions or sizing "
            "recommendations are generated."
        ),
        roi_estimate=roi_estimate,
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/assessments", response_model=AssessmentResponse)
def create_assessment(request: AssessmentRequest) -> AssessmentResponse:
    return assess_request(request)