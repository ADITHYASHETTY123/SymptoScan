import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .history_store import HistoryStore
from .schemas import HistoryRecord, SymptomRequest, SymptomResponse
from .symptom_engine import analyze_symptoms

load_dotenv()

app = FastAPI(
    title=os.getenv("APP_NAME", "SymptoScan API"),
    version="1.0.0",
    description="Healthcare symptom checker API for educational use.",
)

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://127.0.0.1:5500")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin, "http://localhost:5500", "http://127.0.0.1:3000"],
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
    response = analyze_symptoms(payload)
    if store:
        store.insert(payload.symptoms, response)
    return response


@app.get("/api/history", response_model=List[HistoryRecord])
def get_history(limit: int = Query(default=20, ge=1, le=100)) -> List[HistoryRecord]:
    if not store:
        raise HTTPException(status_code=404, detail="History storage is disabled")
    return store.list_recent(limit=limit)
