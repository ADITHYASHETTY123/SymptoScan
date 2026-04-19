import os
import logging
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .history_store import HistoryStore
from .schemas import HistoryRecord, SymptomRequest, SymptomResponse
from .symptom_engine import analyze_symptoms

load_dotenv()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


LOG_ENABLED = _env_flag("DEBUG_LOGS", os.getenv("APP_ENV", "development").lower() == "development")

logging.basicConfig(
    level=logging.INFO if LOG_ENABLED else logging.WARNING,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("symptoscan.api")

app = FastAPI(
    title=os.getenv("APP_NAME", "SymptoScan API"),
    version="1.0.0",
    description="Healthcare symptom checker API for educational use.",
)

frontend_origins_raw = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5500")
frontend_origins = [origin.strip() for origin in frontend_origins_raw.split(",") if origin.strip()]

allow_origins = [
    *frontend_origins,
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
]

# De-duplicate while preserving order.
seen = set()
allow_origins = [origin for origin in allow_origins if not (origin in seen or seen.add(origin))]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

store: Optional[HistoryStore] = None
if os.getenv("STORE_HISTORY", "true").lower() == "true":
    store = HistoryStore(os.getenv("DATABASE_PATH", "./symptoscan.db"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/check-symptoms", response_model=SymptomResponse)
def check_symptoms(payload: SymptomRequest) -> SymptomResponse:
    if LOG_ENABLED:
        logger.info(
            "request.received symptoms=%r age=%s age_group=%s sex=%s duration=%s",
            payload.symptoms,
            payload.age,
            payload.age_group,
            payload.sex,
            payload.duration,
        )

    response = analyze_symptoms(payload)

    if LOG_ENABLED:
        logger.info(
            "request.completed source=%s confidence_level=%s confidence_score=%.2f recognized=%s warnings=%s top_conditions=%s",
            response.source,
            response.analysis.confidence_level,
            response.analysis.confidence_score,
            len(response.analysis.recognized_symptoms),
            len(response.analysis.warning_signs),
            response.analysis.probable_conditions[:3],
        )

    if store:
        store.insert(payload.symptoms, response)

        if LOG_ENABLED:
            logger.info("history.saved source=%s created_at=%s", response.source, response.created_at.isoformat())

    return response


@app.get("/api/history", response_model=List[HistoryRecord])
def get_history(limit: int = Query(default=20, ge=1, le=100)) -> List[HistoryRecord]:
    if not store:
        raise HTTPException(status_code=404, detail="History storage is disabled")
    return store.list_recent(limit=limit)
