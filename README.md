# RetrofitProof AI

RetrofitProof AI is a brownfield pneumatic retrofit migration assistant. Its purpose is to convert legacy pneumatic diagrams and I/O information into a reviewable Festo retrofit design, generate test-backed BOM candidates, and support a defensible customer ROI case.

The intended workflow is: photograph or upload existing machine documentation, convert it into technician-verified circuit and component data, identify appropriate retrofit alternatives, and produce a review package containing a candidate BOM, migration information, FAT/SAT tests, assumptions, and measured payback data.

## Problem

Older Indian machine lines commonly contain undocumented cylinders, valve manifolds, pressure equipment, mixed control networks, and obsolete pneumatic components. Original drawings may be missing or outdated, installed components may differ from the bill of materials, and PLC I/O lists may be incomplete. Legacy documentation is also often spread across photographs, spreadsheets, nameplates, PDFs, and technician knowledge.

Sales engineers therefore spend significant time tracing circuit dependencies, compatibility, pressure and flow assumptions, replacement options, validation work, and commissioning risk. An ordinary catalog recommender cannot understand the dependencies across the complete pneumatic circuit.

Typical risks include:

- Treating outdated drawings as a record of the installed machine
- Selecting replacements without checking the actual machine configuration
- Missing operating pressure, duty-cycle, valve, sensor, or electrical information
- Mixing historical component references with current product compatibility
- Creating an indicative quote before engineering evidence is complete
- Presenting automated recommendations as approved engineering decisions

## Solution

RetrofitProof AI provides a structured brownfield migration workflow:

1. Ingests photographed ISO 1219 diagrams, as-built I/O lists, nameplates, and known pressure, flow, and cycle requirements using document parsing plus technician correction.
2. Builds technician-verified circuit context and identifies unknown pressure ranges, flow limits, fail-safe assumptions, missing sensors, and undocumented installed components.
3. Matches candidate Festo actuators, valves, service units, and CPX-AP modules using deterministic engineering constraints and permitted Festo sizing tools or APIs.
4. Presents retrofit alternatives:
   - Like-for-like pneumatic replacement
   - Instrumented pneumatic upgrade
   - Pneumatics-to-electric conversion where appropriate
5. Generates a candidate BOM, wiring and I/O migration information, FAT/SAT test cases, assumptions, and an ROI worksheet.
6. Calculates an indicative quotation-efficiency case from measured engineering effort inputs.
7. Requires senior engineer sign-off before any migration recommendation is approved.

The application is intended to reduce engineering quotation effort, incorrect substitutions, retrofit scope uncertainty, and commissioning punch-list items while increasing retrofit quote acceptance and Festo hardware attachment.

This application is an engineering **review aid**, not an approval tool, sizing engine, executable commissioning procedure, or automatically approved bill of materials. All retrofit decisions require verification by the responsible engineer. Current technical ratings and product functions must be checked against current technical data and the machine site engineer.

## How the application works

- The Angular frontend collects project information and source documents.
- The FastAPI backend validates the assessment request and identifies missing intake information.
- Local document extraction reads supported PDF, XLSX, CSV, and DXF content.
- Component references are reconciled against the project's configured reference data.
- Optional AI review can summarize risks when `OPENAI_API_KEY` is configured. AI output is advisory and is not used for product approval.
- The assessment always requires engineer review.

No uploaded source document is retained by the application or sent to an external AI service. Local document extraction is performed by the backend.

## Target customer use cases

- **Automotive tier-2 press fixture:** replace discontinued pneumatic valves while preserving machine safety and sequence behavior.
- **Food packer I/O upgrade:** migrate pneumatics and controls to an Ethernet-based controller with a reviewable I/O mapping.
- **Machine builder format-change modernization:** assess pneumatic-to-electric conversion for high-frequency format changes.

## Business value

RetrofitProof AI is intended to deliver:

- Shorter engineering quotations
- Fewer incorrect component substitutions
- Faster approval of the retrofit scope
- Better documented FAT/SAT validation
- More predictable commissioning
- A measured customer ROI case
- Conversion opportunities from incumbent competitor components to Festo hardware and engineering services

Potential revenue models include paid diagnostics and migration reports for integrators, together with increased hardware, engineering-service, and support attachment.

## Product measures

The proposed product success measures are:

- Engineering hours required per quotation
- Validated component-match precision
- Retrofit quote acceptance
- Festo hardware attachment value
- Commissioning punch-list items
- Time from intake to review-ready migration package

## Minimum viable demonstration

The proposed hackathon demonstration uses five anonymized historical retrofit projects to compare candidate outputs and time-to-quote with expert-generated BOMs and test plans. Every output must require senior engineer sign-off; the demonstration must not present an automated result as approved design.

## Risks and guardrails

- Image recognition can misread pneumatic symbols, arrow direction, port markings, safety circuits, or handwritten annotations.
- Current equipment ratings and functions must be verified against current technical data, not assumed from historical documents.
- Historical competitor references must not be interpreted as proof of product compatibility.
- Missing pressure ranges, flow limits, fail-safe assumptions, sensors, and safety circuits must remain visible as unknowns.
- Photographs and scanned documents require technician correction and source verification.
- Like-for-like replacement, instrumented upgrades, and electrification are alternatives for engineer evaluation, not automatically selectable recommendations.
- FAT/SAT templates are validation aids and must be adapted to approved machine-specific procedures.
- No generated report is a design approval. Explicit safety-circuit review, machine-owner authorization, and approved commissioning controls remain mandatory.

## Intake form fields

### 01. Project information

| Field | Required | Current use | Engineering calculation status |
|---|---|---|---|
| **Project name** | Yes | Identifies the assessment and appears in reports and exported review packets. | Not a technical calculation input. |
| **Machine / application** | Yes | Describes the machine or process and provides context for review and optional AI analysis. | Not a technical calculation input. |
| **Operating pressure, bar** | Checked as required intake evidence | Records the nominal or measured operating pressure and identifies it as missing when not supplied. It is included in the review packet and optional AI-review context. | Not currently used in automated pressure, valve, cylinder, or flow sizing. |
| **Target cycle rate, cycles/min** | Checked as required intake evidence | Records the required duty and identifies it as missing when not supplied. It is included in the review packet and optional AI-review context. | Not currently used in cycle-time, flow, wear, or duty calculations. |

Review interpretation: project name and application are identification and scope inputs. Operating pressure and cycle rate are engineering-critical inputs in principle, but the current application captures and validates them without performing automated sizing calculations.

### 02. As-built evidence

“As-built” means the machine condition as currently installed onsite, including subsequent field modifications that may not be represented in the original design documents.

As-built evidence can include:

- Current pneumatic diagrams
- Current valve, sensor, cylinder, fitting, tubing, and tag identifiers
- Current PLC I/O lists and signal mappings
- Existing component part numbers
- Operational pressure, flow, load, and duty information
- Modifications, undocumented changes, obsolete components, and replacement parts
- Differences between physical installation and available drawings
- Assumptions and items that require technician confirmation

| Field | Current use | Important limitation |
|---|---|---|
| **Pneumatic diagram — Available and reviewed** | Acts as an intake completeness check and is recorded in the review packet. | Checking the box confirms the user's review declaration; it does not parse, validate, or approve the drawing. |
| **I/O list — Available and reviewed** | Acts as an intake completeness check and verifies that electrical/PLC evidence has been considered. | Checking the box does not validate addresses, electrical ratings, signal type, or PLC configuration. |
| **Source documents** | Extracts supported text locally for review and may provide data for project reconciliation. | Extracted content requires verification; scanned drawings and some formats may need manual transcription. |
| **Existing components and tags** | Creates component inventory evidence and feeds exact reference lookup and BOM-preview reconciliation. | Text is not a validated engineering inventory, and matches do not prove replacement compatibility. |
| **Legacy part numbers** | Performs exact legacy-part-number lookup against the configured reference data and project reconciliation information. | Matches are historical cross-reference information, not an approved part list. |
| **Legacy component names** | Performs exact-name or description-phrase lookup against configured project reference data. | This is a limited text lookup and does not perform fuzzy guessing or technical compatibility analysis. |
| **Known unknowns / assumptions** | Records uncertainties and includes them in the review packet and optional AI-review context. | Assumptions are not accepted as confirmed facts. They must be marked for technician or engineer confirmation. |

The application currently treats the pneumatic diagram and I/O list as **documentation completeness gates**. It does not independently inspect their contents merely because they are checked or attached.

## Optional quote-effort baseline

The optional quote-effort section supports an indicative return-on-investment comparison:

```text
Hours saved = Current quote effort - Estimated quote effort
Cost savings = Hours saved x Engineering hourly cost
```

This calculation requires:

- Current quote effort, in hours
- Estimated effort using the reviewed workflow, in hours
- Engineering hourly cost in INR

This is only an indicative comparison of quote effort. It does not measure real retrofit savings, operational productivity, machine availability, energy use, or business return, and it does not guarantee that the estimate will be achieved.

## What the current version does not calculate

The current release does **not** automatically calculate or approve:

- Valve or cylinder sizing
- Pneumatic flow requirements
- Pressure-drop or consumption calculations
- Cycle-time feasibility
- Force or load calculations
- Actuator duty and service life
- Electrical compatibility
- Safety system compatibility
- Fail-safe behavior
- BOM legality or technical approval
- Commissioning pass/fail status
- Guaranteed ROI or energy savings

Pressure, cycle rate, source documents, component tags, and as-built evidence are therefore important for eventual engineering analysis, but the present implementation does not turn them into a sizing result.

## Generated assessment output

An assessment can be:

- `information_incomplete` when required intake information is missing
- `awaiting_engineer_review` when the minimum intake checklist is complete

The response also provides:

- Missing information
- Known unknowns
- Reference lookup status
- Component reference candidates
- Source-document summaries
- Candidate BOM-preview items
- FAT/SAT review-test templates
- Engineer review checklist
- Optional ROI estimate
- Optional AI summary and risk notes

Candidate BOM items are explicitly limited to `engineer_review_required`. No compatibility or sizing recommendation is generated.

## Running the application

### Backend

From the repository root:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
npm start
```

The frontend expects the backend at `http://127.0.0.1:8000`. The default Angular development URL is `http://localhost:4200`.

### Optional AI review

Set an API key only when optional hosted AI review is intended:

```powershell
$env:OPENAI_API_KEY="your-key"
```

When no key is configured, the backend uses its deterministic fallback review.

## Tests

Run the backend unit tests from the repository root:

```powershell
cd backend
.venv\Scripts\Activate.ps1
py -m unittest discover -p "test_*.py"
```

Run the frontend tests from the repository root:

```powershell
cd frontend
npm test
```

## Safety and review notice

RetrofitProof AI must not be used as the sole basis for a design decision, machine modification, pressure test, commissioning activity, or safety assessment. Use approved drawings, manufacturer documentation, competent engineering review, machine-owner authorization, suitable risk assessment, and site commissioning controls.
