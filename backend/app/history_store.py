import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

from .schemas import HistoryRecord, SymptomResponse


class HistoryStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS symptom_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symptoms TEXT NOT NULL,
                    source TEXT NOT NULL,
                    probable_conditions TEXT NOT NULL,
                    recommended_next_steps TEXT NOT NULL,
                    warning_signs TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "recognized_symptoms", "TEXT NOT NULL DEFAULT '[]'")
            self._ensure_column(conn, "confidence_score", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "confidence_level", "TEXT NOT NULL DEFAULT 'low'")
            self._ensure_column(conn, "confidence_note", "TEXT NOT NULL DEFAULT ''")
            conn.commit()

    def _ensure_column(self, conn: sqlite3.Connection, column_name: str, definition: str) -> None:
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(symptom_history)").fetchall()
        }
        if column_name in columns:
            return
        conn.execute(f"ALTER TABLE symptom_history ADD COLUMN {column_name} {definition}")

    def insert(self, symptoms: str, response: SymptomResponse) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO symptom_history (
                    symptoms,
                    source,
                    probable_conditions,
                    recommended_next_steps,
                    warning_signs,
                    recognized_symptoms,
                    confidence_score,
                    confidence_level,
                    confidence_note,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symptoms,
                    response.source,
                    json.dumps(response.analysis.probable_conditions),
                    json.dumps(response.analysis.recommended_next_steps),
                    json.dumps(response.analysis.warning_signs),
                    json.dumps(response.analysis.recognized_symptoms),
                    response.analysis.confidence_score,
                    response.analysis.confidence_level,
                    response.analysis.confidence_note,
                    response.created_at.isoformat(),
                ),
            )
            conn.commit()

    def list_recent(self, limit: int = 20) -> List[HistoryRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, symptoms, source, probable_conditions,
                       recommended_next_steps, warning_signs, recognized_symptoms,
                       confidence_score, confidence_level, confidence_note, created_at
                FROM symptom_history
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        records: List[HistoryRecord] = []
        for row in rows:
            records.append(
                HistoryRecord(
                    id=row["id"],
                    symptoms=row["symptoms"],
                    source=row["source"],
                    probable_conditions=json.loads(row["probable_conditions"]),
                    recommended_next_steps=json.loads(row["recommended_next_steps"]),
                    warning_signs=json.loads(row["warning_signs"]),
                    recognized_symptoms=json.loads(row["recognized_symptoms"] or "[]"),
                    confidence_score=float(row["confidence_score"] or 0.0),
                    confidence_level=row["confidence_level"] or "low",
                    confidence_note=row["confidence_note"] or "",
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
            )
        return records
