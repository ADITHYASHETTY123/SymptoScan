import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .safety import DEFAULT_DISCLAIMER, detect_warning_signs
from .schemas import SymptomCheckResult, SymptomRequest, SymptomResponse

load_dotenv()

KEYWORD_HINTS = {
    "fever": "Viral infection (for example influenza-like illness)",
    "cough": "Upper respiratory tract irritation or infection",
    "sore throat": "Pharyngitis",
    "headache": "Tension headache or migraine",
    "nausea": "Gastroenteritis or dietary intolerance",
    "stomach": "Gastritis or digestive upset",
    "rash": "Allergic or inflammatory skin reaction",
    "fatigue": "Non-specific fatigue (sleep stress nutritional factors)",
}


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _rule_based_result(payload: SymptomRequest) -> SymptomResponse:
    s = payload.symptoms.lower()
    conditions: List[str] = []
    steps: List[str] = [
        "Monitor symptoms for the next 24-48 hours and note any changes.",
        "Stay hydrated and rest if symptoms are mild.",
        "Book a clinician visit for persistent or worsening symptoms.",
    ]

    for keyword, label in KEYWORD_HINTS.items():
        if keyword in s and label not in conditions:
            conditions.append(label)

    if not conditions:
        conditions = [
            "Non-specific symptom pattern",
            "Further clinical evaluation may be needed",
        ]

    warning_signs = detect_warning_signs(payload.symptoms)
    if warning_signs:
        steps.insert(0, "Seek urgent medical care now due to possible red-flag symptoms.")

    analysis = SymptomCheckResult(
        probable_conditions=conditions[:5],
        recommended_next_steps=steps[:6],
        warning_signs=warning_signs,
        educational_disclaimer=DEFAULT_DISCLAIMER,
    )
    return SymptomResponse(
        analysis=analysis,
        source="rule_based",
        created_at=datetime.now(timezone.utc),
    )


def _langchain_agent_result(payload: SymptomRequest) -> Optional[SymptomResponse]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    use_agent = os.getenv("USE_LANGCHAIN_AGENT", "true").lower() == "true"
    if not use_agent:
        return None

    try:
        from langchain.agents import AgentExecutor, create_tool_calling_agent
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
        from langchain_core.tools import tool
        from langchain_openai import ChatOpenAI
    except Exception:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    timeout = float(os.getenv("LLM_TIMEOUT", "25"))

    age_context = payload.age_group or (str(payload.age) if payload.age is not None else "unknown")

    @tool
    def emergency_red_flags(symptoms: str) -> str:
        """Detect emergency warning signs from symptom text."""
        return json.dumps(detect_warning_signs(symptoms))

    @tool
    def symptom_keyword_hints(symptoms: str) -> str:
        """Return educational condition hints from symptom keywords."""
        lowered = symptoms.lower()
        hints = [label for keyword, label in KEYWORD_HINTS.items() if keyword in lowered]
        return json.dumps(hints[:6])

    llm = ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.2,
        timeout=timeout,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a clinical education assistant. Do not provide diagnosis. "
                "You may call tools for red-flag and hint support. "
                "Return only JSON with keys: probable_conditions (array of strings), "
                "recommended_next_steps (array of strings), warning_signs (array of strings), "
                "educational_disclaimer (string).",
            ),
            (
                "human",
                "Symptoms: {symptoms}\nAge: {age}\nSex: {sex}\nDuration: {duration}\n"
                "Use tools if helpful. Output JSON only.",
            ),
            MessagesPlaceholder("agent_scratchpad"),
        ]
    )

    agent = create_tool_calling_agent(llm=llm, tools=[emergency_red_flags, symptom_keyword_hints], prompt=prompt)
    executor = AgentExecutor(agent=agent, tools=[emergency_red_flags, symptom_keyword_hints], verbose=False)
    result = executor.invoke(
        {
            "symptoms": payload.symptoms,
            "age": age_context,
            "sex": payload.sex or "unknown",
            "duration": payload.duration or "unknown",
        }
    )

    content = str(result.get("output", ""))
    parsed = _extract_json(content)
    if not parsed:
        return None

    warning_signs = parsed.get("warning_signs") or []
    detected = detect_warning_signs(payload.symptoms)
    merged_warning_signs = []
    for item in [*warning_signs, *detected]:
        if item and item not in merged_warning_signs:
            merged_warning_signs.append(item)

    analysis = SymptomCheckResult(
        probable_conditions=(parsed.get("probable_conditions") or [])[:5],
        recommended_next_steps=(parsed.get("recommended_next_steps") or [])[:6],
        warning_signs=merged_warning_signs,
        educational_disclaimer=parsed.get("educational_disclaimer") or DEFAULT_DISCLAIMER,
    )

    if not analysis.probable_conditions or not analysis.recommended_next_steps:
        return None

    return SymptomResponse(
        analysis=analysis,
        source="langchain_agent",
        created_at=datetime.now(timezone.utc),
    )


def _llm_result(payload: SymptomRequest) -> Optional[SymptomResponse]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    timeout = float(os.getenv("LLM_TIMEOUT", "25"))

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    age_context = payload.age_group or (str(payload.age) if payload.age is not None else "unknown")

    system_prompt = (
        "You are a clinical education assistant. Do not provide a diagnosis. "
        "Return concise educational possibilities and safe next steps. "
        "Always include a clear safety disclaimer. "
        "Respond in JSON with keys: probable_conditions (array of strings), "
        "recommended_next_steps (array of strings), warning_signs (array of strings), "
        "educational_disclaimer (string)."
    )

    user_prompt = (
        f"Symptoms: {payload.symptoms}\n"
        f"Age: {age_context}\n"
        f"Sex: {payload.sex if payload.sex else 'unknown'}\n"
        f"Duration: {payload.duration if payload.duration else 'unknown'}\n"
        "Provide safe, educational output only."
    )

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )

    content = completion.choices[0].message.content or ""
    parsed = _extract_json(content)
    if not parsed:
        return None

    warning_signs = parsed.get("warning_signs") or []
    detected = detect_warning_signs(payload.symptoms)
    merged_warning_signs = []
    for item in [*warning_signs, *detected]:
        if item and item not in merged_warning_signs:
            merged_warning_signs.append(item)

    analysis = SymptomCheckResult(
        probable_conditions=(parsed.get("probable_conditions") or [])[:5],
        recommended_next_steps=(parsed.get("recommended_next_steps") or [])[:6],
        warning_signs=merged_warning_signs,
        educational_disclaimer=parsed.get("educational_disclaimer") or DEFAULT_DISCLAIMER,
    )

    if not analysis.probable_conditions or not analysis.recommended_next_steps:
        return None

    return SymptomResponse(
        analysis=analysis,
        source="llm",
        created_at=datetime.now(timezone.utc),
    )


def analyze_symptoms(payload: SymptomRequest) -> SymptomResponse:
    try:
        result = _langchain_agent_result(payload)
        if result:
            return result
    except Exception:
        pass

    try:
        result = _llm_result(payload)
        if result:
            return result
    except Exception:
        pass
    return _rule_based_result(payload)
