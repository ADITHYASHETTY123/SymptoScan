from typing import List

EMERGENCY_TERMS = {
    "chest pain",
    "shortness of breath",
    "trouble breathing",
    "fainting",
    "unconscious",
    "seizure",
    "stroke",
    "slurred speech",
    "severe bleeding",
    "suicidal",
}

DEFAULT_DISCLAIMER = (
    "Educational information only, not a medical diagnosis. "
    "If symptoms are severe, worsening, or you are worried, seek professional care promptly."
)


def detect_warning_signs(symptom_text: str) -> List[str]:
    lowered = symptom_text.lower()
    found = [term for term in sorted(EMERGENCY_TERMS) if term in lowered]
    if found:
        found.insert(0, "Potential red-flag symptoms detected")
    return found
