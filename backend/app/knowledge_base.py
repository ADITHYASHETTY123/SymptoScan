import csv
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Set


DATA_DIR = Path(__file__).resolve().parent / "data"
MODIFIER_WORDS = {
    "acute",
    "bladder",
    "continuous",
    "dischromic",
    "extra",
    "high",
    "internal",
    "mild",
    "mucoid",
}
SYMPTOM_ALIASES = {
    "belly pain": ["stomach pain"],
    "dry cough": ["cough"],
    "itchy": ["itching"],
    "itchiness": ["itching"],
    "rash": ["skin rash"],
    "runny nose": ["runny nose"],
    "skin rash": ["skin rash"],
    "tired": ["fatigue"],
    "tiredness": ["fatigue"],
    "vomit": ["vomiting"],
    "weakness": ["fatigue"],
}


def _normalize_text(value: str) -> str:
    value = (value or "").strip().lower().replace("_", " ")
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return " ".join(value.split())


def _compact_text(value: str) -> str:
    return _normalize_text(value).replace(" ", "")


def _read_csv_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file, skipinitialspace=True)
        return [{(key or "").strip(): (value or "").strip() for key, value in row.items()} for row in reader]


@dataclass(frozen=True)
class DiseaseCandidate:
    disease: str
    score: float
    confidence: float
    confidence_level: str
    matched_symptoms: List[str]
    matched_weight: int
    total_known_symptoms: int
    description: str
    precautions: List[str]
    supporting_evidence: List[str]


class SymptomKnowledgeBase:
    def __init__(self) -> None:
        self._disease_to_symptoms = self._load_disease_symptoms()
        self._severity = self._load_symptom_severity()
        self._descriptions = self._load_descriptions()
        self._precautions = self._load_precautions()
        self._known_symptoms = sorted({symptom for symptoms in self._disease_to_symptoms.values() for symptom in symptoms})
        self._symptom_index = {symptom: self._build_search_terms(symptom) for symptom in self._known_symptoms}

    def _core_symptom(self, symptom: str) -> str:
        words = symptom.split()
        while len(words) > 1 and words[0] in MODIFIER_WORDS:
            words = words[1:]
        return " ".join(words)

    def _build_search_terms(self, symptom: str) -> Set[str]:
        terms = {symptom, symptom.replace(" ", "")}
        core = self._core_symptom(symptom)
        if core:
            terms.add(core)
            terms.add(core.replace(" ", ""))
        for alias, mapped in SYMPTOM_ALIASES.items():
            if symptom in mapped:
                terms.add(_normalize_text(alias))
                terms.add(_compact_text(alias))
        return {term for term in terms if term}

    def _load_disease_symptoms(self) -> Dict[str, Set[str]]:
        disease_map: Dict[str, Set[str]] = {}
        for row in _read_csv_rows(DATA_DIR / "dataset.csv"):
            disease = row.get("Disease", "").strip()
            if not disease:
                continue
            symptoms = disease_map.setdefault(disease, set())
            for key, value in row.items():
                if key.startswith("Symptom_") and value:
                    normalized = _normalize_text(value)
                    if normalized:
                        symptoms.add(normalized)
        return disease_map

    def _load_symptom_severity(self) -> Dict[str, int]:
        severity: Dict[str, int] = {}
        for row in _read_csv_rows(DATA_DIR / "Symptom-severity.csv"):
            symptom = _normalize_text(row.get("Symptom", ""))
            if not symptom:
                continue
            try:
                severity[symptom] = int(str(row.get("weight", "1")).strip())
            except ValueError:
                severity[symptom] = 1
        return severity

    def _load_descriptions(self) -> Dict[str, str]:
        descriptions: Dict[str, str] = {}
        for row in _read_csv_rows(DATA_DIR / "symptom_Description.csv"):
            disease = row.get("Disease", "").strip()
            description = row.get("Description", "").strip()
            if disease and description:
                descriptions[disease] = description
        return descriptions

    def _load_precautions(self) -> Dict[str, List[str]]:
        precautions: Dict[str, List[str]] = {}
        for row in _read_csv_rows(DATA_DIR / "symptom_precaution.csv"):
            disease = row.get("Disease", "").strip()
            if not disease:
                continue
            items = [value.strip() for key, value in row.items() if key.startswith("Precaution_") and value and value.strip()]
            precautions[disease] = items
        return precautions

    def extract_user_symptoms(self, symptom_text: str) -> List[str]:
        normalized_input = _normalize_text(symptom_text)
        compact_input = _compact_text(symptom_text)
        word_set = set(normalized_input.split())
        matches: List[str] = []
        exact_matches: Set[str] = set()

        for symptom in self._known_symptoms:
            symptom_words = symptom.split()
            search_terms = self._symptom_index[symptom]
            if symptom in normalized_input:
                matches.append(symptom)
                exact_matches.add(symptom)
                continue
            if any(term and term in compact_input for term in search_terms if " " not in term):
                matches.append(symptom)
                if symptom.replace(" ", "") in compact_input:
                    exact_matches.add(symptom)
                continue
            if len(symptom_words) > 1 and all(word in word_set for word in symptom_words):
                matches.append(symptom)
                continue
            core = self._core_symptom(symptom)
            core_words = core.split()
            if core != symptom and core_words and all(word in word_set for word in core_words):
                matches.append(symptom)

        if matches:
            grouped: Dict[str, str] = {}
            for symptom in sorted(set(matches)):
                core = self._core_symptom(symptom)
                existing = grouped.get(core)
                if not existing:
                    grouped[core] = symptom
                    continue
                if symptom in exact_matches and existing not in exact_matches:
                    grouped[core] = symptom
                    continue
                if existing in exact_matches and symptom not in exact_matches:
                    continue
                existing_score = (self._severity.get(existing, 1), len(existing.split()))
                candidate_score = (self._severity.get(symptom, 1), len(symptom.split()))
                if candidate_score > existing_score:
                    grouped[core] = symptom
            return sorted(grouped.values())

        chunks = [
            chunk.strip()
            for chunk in re.split(r",|\band\b|\bwith\b|\bfor\b|\bplus\b", normalized_input)
            if chunk.strip()
        ]
        fuzzy_matches: List[str] = []
        for chunk in chunks:
            for symptom in self._known_symptoms:
                ratio = SequenceMatcher(None, chunk, symptom).ratio()
                if ratio >= 0.86:
                    fuzzy_matches.append(symptom)
        return sorted(set(fuzzy_matches))

    def retrieve(self, symptom_text: str, limit: int = 5) -> List[DiseaseCandidate]:
        extracted_symptoms = self.extract_user_symptoms(symptom_text)
        if not extracted_symptoms:
            return []

        candidates: List[DiseaseCandidate] = []
        extracted_set = set(extracted_symptoms)
        for disease, disease_symptoms in self._disease_to_symptoms.items():
            matched = sorted(extracted_set.intersection(disease_symptoms))
            if not matched:
                continue

            matched_weight = sum(self._severity.get(symptom, 1) for symptom in matched)
            matched_count = len(matched)
            focus = len(matched) / max(len(extracted_set), 1)
            symptom_coverage = matched_count / max(len(disease_symptoms), 1)
            description_bonus = 0.4 if self._descriptions.get(disease) else 0.0
            score = round((matched_weight * 1.7) + (matched_count * 2.6) + (focus * 2.5) + description_bonus, 4)
            confidence = round(
                min(
                    1.0,
                    (focus * 0.25)
                    + (min(matched_count, 4) / 4 * 0.4)
                    + (min(matched_weight, 18) / 18 * 0.25)
                    + (symptom_coverage * 0.1),
                ),
                4,
            )
            confidence_level = self._confidence_level(confidence, matched_count, focus)

            supporting_evidence = [
                f"Matched symptoms: {', '.join(matched[:6])}",
                f"Matched {matched_count} out of {len(extracted_set)} extracted user symptoms",
                f"Severity-weighted match score: {matched_weight}",
                f"Confidence: {confidence_level} ({confidence:.2f})",
            ]

            candidates.append(
                DiseaseCandidate(
                    disease=disease,
                    score=score,
                    confidence=confidence,
                    confidence_level=confidence_level,
                    matched_symptoms=matched,
                    matched_weight=matched_weight,
                    total_known_symptoms=len(disease_symptoms),
                    description=self._descriptions.get(disease, ""),
                    precautions=self._precautions.get(disease, []),
                    supporting_evidence=supporting_evidence,
                )
            )

        candidates.sort(
            key=lambda candidate: (
                candidate.confidence,
                candidate.score,
                candidate.matched_weight,
                len(candidate.matched_symptoms),
                candidate.disease,
            ),
            reverse=True,
        )
        filtered = self._apply_confidence_thresholds(candidates)
        return filtered[:limit]

    def _confidence_level(self, confidence: float, matched_count: int, focus: float) -> str:
        if confidence >= 0.72 and matched_count >= 3 and focus >= 0.6:
            return "high"
        if confidence >= 0.45 and matched_count >= 2:
            return "medium"
        return "low"

    def _apply_confidence_thresholds(self, candidates: List[DiseaseCandidate]) -> List[DiseaseCandidate]:
        if not candidates:
            return []
        top = candidates[0]
        kept: List[DiseaseCandidate] = []
        for candidate in candidates:
            score_gap = top.score - candidate.score
            confidence_gap = top.confidence - candidate.confidence
            if candidate.confidence_level == "high":
                kept.append(candidate)
                continue
            if candidate.confidence_level == "medium" and score_gap <= 6.0 and confidence_gap <= 0.18:
                kept.append(candidate)
                continue
            if not kept:
                kept.append(candidate)
        return kept[:5]

    def as_prompt_context(self, symptom_text: str, limit: int = 5) -> Dict[str, object]:
        extracted_symptoms = self.extract_user_symptoms(symptom_text)
        candidates = self.retrieve(symptom_text, limit=limit)
        overall_confidence = candidates[0].confidence if candidates else 0.0
        overall_level = candidates[0].confidence_level if candidates else "low"
        return {
            "extracted_symptoms": extracted_symptoms,
            "candidate_count": len(candidates),
            "overall_confidence": overall_confidence,
            "overall_confidence_level": overall_level,
            "candidates": [
                {
                    "disease": candidate.disease,
                    "score": candidate.score,
                    "confidence": candidate.confidence,
                    "confidence_level": candidate.confidence_level,
                    "matched_symptoms": candidate.matched_symptoms,
                    "matched_weight": candidate.matched_weight,
                    "total_known_symptoms": candidate.total_known_symptoms,
                    "description": candidate.description,
                    "precautions": candidate.precautions,
                    "supporting_evidence": candidate.supporting_evidence,
                }
                for candidate in candidates
            ],
        }


@lru_cache(maxsize=1)
def get_knowledge_base() -> SymptomKnowledgeBase:
    return SymptomKnowledgeBase()
