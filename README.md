# SymptoScan - Healthcare Symptom Checker

SymptoScan is an educational symptom checker project.
It accepts symptom text and returns:
- probable conditions
- recommended next steps
- warning signs and a safety disclaimer

## Features

- FastAPI backend endpoint for symptom analysis
- LangChain tool-calling agent for symptom reasoning
- LLM-powered reasoning when API key is configured
- Rule-based fallback when LLM is unavailable
- Optional SQLite history storage for previous requests
- Simple frontend form to test the flow end-to-end

## Important Safety Note

This app is for educational use only. It does **not** provide medical diagnosis.
For severe or worsening symptoms, users should seek professional care immediately.

## Project Structure

```text
SymptoScan/
  backend/
    app/
      main.py
      schemas.py
      safety.py
      symptom_engine.py
      history_store.py
    requirements.txt
    .env.example
  frontend/
    index.html
    styles.css
    app.js
  README.md
```

## Backend Setup

1. Open terminal in `backend` folder.
2. Create and activate a virtual environment.
3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Copy environment file and edit values:

```powershell
copy .env.example .env
```

5. Run backend API:

```powershell
uvicorn app.main:app --reload --port 8000
```

API docs: `http://127.0.0.1:8000/docs`

## Frontend Setup

Serve the `frontend` directory with any static server.

Example with Python:

```powershell
cd frontend
python -m http.server 5500
```

Open: `http://127.0.0.1:5500`

## API Contract

### POST `/api/check-symptoms`

Request body:

```json
{
  "symptoms": "Fever and dry cough for two days",
  "age": null,
  "age_group": "18-29",
  "sex": "female",
  "duration": "2 days"
}
```

Response shape:

```json
{
  "analysis": {
    "probable_conditions": ["..."],
    "recommended_next_steps": ["..."],
    "warning_signs": ["..."],
    "educational_disclaimer": "..."
  },
  "source": "llm",
  "created_at": "2026-04-16T12:00:00Z"
}
```

### GET `/api/history?limit=20`

Returns recent requests if history storage is enabled.

## LLM Configuration

Set in `backend/.env`:
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-4.1-mini`)
- `OPENAI_BASE_URL` (default OpenAI endpoint)

If no API key is set, backend automatically uses rule-based fallback.

## LangChain Agent Configuration

Set in `backend/.env`:
- `USE_LANGCHAIN_AGENT=true`

Runtime order:
1. LangChain agent path (`source = langchain_agent`)
2. Direct LLM fallback (`source = llm`)
3. Rule-based fallback (`source = rule_based`)

## Demo Video Checklist

For your deliverable video:
1. Start backend and open Swagger docs.
2. Submit one mild symptom case.
3. Submit one red-flag symptom case (for warning signs).
4. Show frontend form and results.
5. Show history endpoint output.

## Evaluation Mapping

- Correctness: structured JSON output with validation
- LLM reasoning quality: optional LLM analysis path
- Safety disclaimers: enforced in all responses
- Code design: modular backend and clean API contracts
