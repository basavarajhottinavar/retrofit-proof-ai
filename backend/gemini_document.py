import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.5-flash-lite"


def _load_backend_env() -> None:
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    except OSError:
        return


_load_backend_env()


def _model_name() -> str:
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip()
    if not model.lower().startswith("gemini-"):
        model = f"gemini-{model}"
    return model


def gemini_available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _gemini_request(
    payload: dict[str, Any],
    timeout_seconds: float = 90,
    max_attempts: int = 3,
) -> dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("Gemini API key is not configured")

    api_root = os.getenv("GEMINI_API_ROOT", DEFAULT_API_ROOT).rstrip("/")
    url = f"{api_root}/models/{_model_name()}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            request = Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urlopen(request, timeout=timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504} and attempt + 1 < max_attempts:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise
        except (HTTPError, URLError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt + 1 >= max_attempts:
                break
            time.sleep(2 ** (attempt + 1))

    raise RuntimeError("Gemini request failed") from last_error


def _json_response(payload: dict[str, Any]) -> dict[str, Any]:
    response = _gemini_request(payload)
    candidates = response.get("candidates") or []
    if not candidates:
        return {}
    text = (((candidates[0].get("content") or {}).get("parts") or [{}])[0].get("text"))
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        parsed = json.loads(match.group(0))
    return parsed if isinstance(parsed, dict) else {}


def extract_document_with_gemini(
    content: bytes,
    mime_type: str,
    filename: str,
    extracted_text: str = "",
) -> dict[str, Any]:
    if not gemini_available():
        return {}

    hint = ""
    if extracted_text.strip():
        hint = (
            "\nExact text extracted locally (use it to reconcile legibility, not as engineering approval):\n"
            + extracted_text[:16000]
        )
    prompt = (
        "Read this pneumatic/industrial engineering document. "
        "Copy printed part numbers exactly; do not correct, complete, or infer codes. "
        "Identify numbered drawing callouts, legacy/manufacturer codes, descriptions, "
        "component types, uncertainty, and any callout/code mismatch visible in the drawing."
        " For every BOM table row, put the actual printed manufacturer's part/type code in "
        "part_number. Do not use customer, project, ERP, CRC, or internal supplier numbers there."
        " For example, if text says 'PUSH-IN L-FITTING ... cod. NPQM-L-Q10-E-P10', "
        "part_number must be 'NPQM-L-Q10-E-P10'. Also add the exact code to text_callouts."
        + hint
        + "\nReturn JSON with these keys: "
        "components (each callout_no, part_number, manufacturer, description, component_type, confidence), "
        "text_callouts (object keyed by item number and exact printed code), "
        "unknowns (strings), assumptions (strings), warnings (strings). "
        "Never approve a component and never invent a part number."
    )
    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"inlineData": {"mimeType": mime_type, "data": __import__("base64").b64encode(content).decode("ascii")}},
                {"text": prompt},
            ],
        }],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "components": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "callout_no": {"type": "integer"},
                                "part_number": {"type": "string", "nullable": True},
                                "manufacturer": {"type": "string", "nullable": True},
                                "description": {"type": "string", "nullable": True},
                                "component_type": {"type": "string", "nullable": True},
                                "confidence": {"type": "number"},
                            },
                        },
                    },
                    "text_callouts": {"type": "object"},
                    "unknowns": {"type": "array", "items": {"type": "string"}},
                    "assumptions": {"type": "array", "items": {"type": "string"}},
                    "warnings": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["components", "text_callouts", "unknowns", "assumptions", "warnings"],
            },
        },
    }
    result = _json_response(payload)
    result["filename"] = filename
    result["provider"] = "Google Gemini"
    result["model"] = _model_name()
    result["status"] = "ai_extracted" if result else "ai_unavailable"
    return result


def suggest_festo_replacements(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not gemini_available():
        return []

    candidates = []
    for record in records:
        if record.get("festo_part_number") or record.get("festo_type_code"):
            continue
        candidates.append({
            "legacy_part_number": record.get("legacy_part_number"),
            "description": record.get("description"),
            "competitor": record.get("competitor"),
        })
    candidates = candidates[:20]
    if not candidates:
        return []

    prompt = (
        "From the legacy pneumatic component candidates below, propose only plausible current "
        "Festo part numbers or type codes if sufficient technical data is available. "
        "For each result include legacy_part_number, suggested_part_number, suggested_type_code, "
        "basis, confidence, and verification_url. If the legacy item is generic or a bracket/silencer, "
        "prefer a clear no_equivalent result. Never claim compatibility; compatibility requires engineer review. "
        "Do not return prose outside JSON.\n"
        + json.dumps(candidates, ensure_ascii=True)
    )
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "legacy_part_number": {"type": "string"},
                                "suggested_part_number": {"type": "string", "nullable": True},
                                "suggested_type_code": {"type": "string", "nullable": True},
                                "basis": {"type": "string"},
                                "confidence": {"type": "number"},
                                "verification_url": {"type": "string", "nullable": True},
                            },
                        },
                    }
                },
                "required": ["suggestions"],
            },
        },
    }
    result = _json_response(payload)
    suggestions = result.get("suggestions", [])
    for suggestion in suggestions:
        suggestion["status"] = "ai_suggestion_unverified"
        suggestion["requires_engineer_review"] = True
        suggestion["latest_data_verified"] = False
    return suggestions[:20]
