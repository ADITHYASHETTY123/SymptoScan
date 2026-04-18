import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.history_store import HistoryStore
from app.knowledge_base import get_knowledge_base
from app.main import app
from app.schemas import SymptomRequest
from app.symptom_engine import analyze_symptoms


class KnowledgeBaseTests(unittest.TestCase):
    def test_extract_user_symptoms_maps_common_phrases(self) -> None:
        kb = get_knowledge_base()

        extracted = kb.extract_user_symptoms("Fever and dry cough for two days with fatigue and headache")

        self.assertIn("high fever", extracted)
        self.assertIn("cough", extracted)
        self.assertIn("fatigue", extracted)
        self.assertIn("headache", extracted)

    def test_retrieve_returns_ranked_candidates(self) -> None:
        kb = get_knowledge_base()

        candidates = kb.retrieve("itching with skin rash and nodal skin eruptions", limit=3)

        self.assertGreaterEqual(len(candidates), 1)
        self.assertEqual(candidates[0].disease, "Fungal infection")
        self.assertIn("itching", candidates[0].matched_symptoms)
        self.assertIn(candidates[0].confidence_level, {"medium", "high"})

    def test_low_signal_input_gets_low_confidence_context(self) -> None:
        kb = get_knowledge_base()

        context = kb.as_prompt_context("I feel off and a bit tired", limit=5)

        self.assertEqual(context["overall_confidence_level"], "low")


class HybridResponseTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "USE_LANGCHAIN_AGENT": "false"}, clear=False)
    def test_analyze_symptoms_uses_dataset_backed_fallback(self) -> None:
        result = analyze_symptoms(
            SymptomRequest(symptoms="Itching with skin rash and nodal skin eruptions", duration="2 days")
        )

        self.assertEqual(result.source, "rule_based")
        self.assertIn("Fungal infection", result.analysis.probable_conditions)
        self.assertIn("itching", result.analysis.recognized_symptoms)
        self.assertGreater(result.analysis.confidence_score, 0)
        self.assertIn(result.analysis.confidence_level, {"medium", "high"})

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "USE_LANGCHAIN_AGENT": "false"}, clear=False)
    def test_api_returns_recognized_symptoms(self) -> None:
        client = TestClient(app)

        response = client.post(
            "/api/check-symptoms",
            json={
                "symptoms": "Fever and dry cough with fatigue",
                "age_group": "18-29",
                "sex": "female",
                "duration": "2 days",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["source"], "rule_based")
        self.assertIn("recognized_symptoms", payload["analysis"])
        self.assertIn("high fever", payload["analysis"]["recognized_symptoms"])
        self.assertIn("cough", payload["analysis"]["recognized_symptoms"])
        self.assertIn("confidence_level", payload["analysis"])
        self.assertIn(payload["analysis"]["confidence_level"], {"low", "medium", "high"})

    @patch.dict(os.environ, {"OPENAI_API_KEY": "", "USE_LANGCHAIN_AGENT": "false"}, clear=False)
    def test_history_store_persists_new_analysis_fields(self) -> None:
        temp_dir = BACKEND_DIR / "tests" / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        database_path = temp_dir / f"history_store_test_{uuid.uuid4().hex}.db"
        store = HistoryStore(str(database_path))
        response = analyze_symptoms(
            SymptomRequest(symptoms="Itching with skin rash and nodal skin eruptions", duration="2 days")
        )

        store.insert("Itching with skin rash and nodal skin eruptions", response)
        records = store.list_recent(limit=1)

        self.assertEqual(len(records), 1)
        self.assertIn("itching", records[0].recognized_symptoms)
        self.assertGreater(records[0].confidence_score, 0)
        self.assertIn(records[0].confidence_level, {"low", "medium", "high"})


if __name__ == "__main__":
    unittest.main()
