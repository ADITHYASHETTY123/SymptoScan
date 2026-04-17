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
    Dockerfile
    .dockerignore
    app/
      main.py
      schemas.py
      safety.py
      symptom_engine.py
      history_store.py
    requirements.txt
    .env.example
  frontend/
    config.js
    index.html
    styles.css
    app.js
  render.yaml
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

## Deployment

### Option A: Render (recommended)

This repo includes `render.yaml` for one blueprint with:
- `symptoscan-api` (Docker web service)
- `symptoscan-frontend` (static site)

Steps:

1. Push this repository to GitHub.
2. In Render, choose **New +** -> **Blueprint** and connect the repo.
3. Render will detect `render.yaml` and create both services.
4. After API deploys, copy its public URL (example: `https://symptoscan-api.onrender.com`).
5. Set frontend env var on Render static service:
   - `RENDER_EXTERNAL_BACKEND_URL=https://your-api-url.onrender.com`
6. Set backend env vars on Render web service:
   - `FRONTEND_ORIGIN=https://your-frontend-url.onrender.com`
   - `OPENAI_API_KEY=<your-key>` (optional)
   - `OPENAI_MODEL=gpt-4.1-mini` (optional)
   - `USE_LANGCHAIN_AGENT=true` (optional)
7. Redeploy both services.

Notes:
- If `OPENAI_API_KEY` is not set, the app still works via rule-based fallback.
- `FRONTEND_ORIGIN` supports comma-separated values if you use multiple domains.

### Option B: Docker (VPS/VM)

Backend container:

```bash
cd backend
docker build -t symptoscan-api .
docker run -d --name symptoscan-api -p 8000:8000 \
  -e FRONTEND_ORIGIN=https://your-frontend-domain.com \
  -e OPENAI_API_KEY=your_key_if_needed \
  symptoscan-api
```

Frontend static hosting:
- Host `frontend/` on Netlify, Vercel (static), GitHub Pages, or Nginx.
- Set `frontend/config.js` -> `window.APP_CONFIG.API_BASE` to your backend URL.

Example:

```js
window.APP_CONFIG = {
  API_BASE: "https://your-backend-domain.com",
};
```

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
