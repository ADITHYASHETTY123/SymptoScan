import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

from .knowledge_base import get_knowledge_base
from .safety import DEFAULT_DISCLAIMER, detect_warning_signs
from .schemas import SymptomCheckResult, SymptomRequest, SymptomResponse

load_dotenv()


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _build_confidence_note(confidence_level: str, recognized_symptoms: List[str], candidate_count: int) -> str:
    if confidence_level == "high":
        return f"The dataset found a strong pattern match from {len(recognized_symptoms)} recognized symptoms."
    if confidence_level == "medium":
        return f"The dataset found a partial match. Use the returned conditions as possibilities, not conclusions."
    if candidate_count == 0:
        return "The dataset could not find a reliable symptom pattern for this input."
    return "The dataset evidence is limited or ambiguous, so the ranked conditions have low confidence."


def _rule_based_result(payload: SymptomRequest) -> SymptomResponse:
    kb = get_knowledge_base()
    context = kb.as_prompt_context(payload.symptoms, limit=5)
    candidates = context["candidates"]
    recognized_symptoms = list(context.get("extracted_symptoms") or [])
    confidence_score = float(context.get("overall_confidence") or 0.0)
    confidence_level = str(context.get("overall_confidence_level") or "low")
    warning_signs = detect_warning_signs(payload.symptoms)

    conditions = [candidate["disease"] for candidate in candidates[:5]]
    if confidence_level == "low":
        conditions = conditions[:3]
    if not conditions:
        conditions = [
            "Non-specific symptom pattern",
            "Further clinical evaluation may be needed",
        ]

    steps: List[str] = []
    seen_steps = set()

    def add_step(step: str) -> None:
        normalized = step.strip().lower()
        if not normalized or normalized in seen_steps:
            return
        seen_steps.add(normalized)
        steps.append(step)

    if warning_signs:
        add_step("Seek urgent medical care now due to possible red-flag symptoms.")

    extracted = context.get("extracted_symptoms") or []
    if extracted:
        add_step(f"Symptoms recognized from the dataset: {', '.join(extracted[:6])}.")

    for candidate in candidates[:2]:
        for precaution in candidate.get("precautions") or []:
            if precaution:
                add_step(precaution.capitalize())
        if len(steps) >= 6:
            break

    default_steps = [
        "Monitor symptoms for the next 24-48 hours and note any changes.",
        "Stay hydrated and rest if symptoms are mild.",
        "Book a clinician visit for persistent or worsening symptoms.",
    ]
    for step in default_steps:
        add_step(step)

    if confidence_level == "low":
        add_step("Share more specific symptoms, duration, fever level, pain location, and triggers to improve the match quality.")

    analysis = SymptomCheckResult(
        probable_conditions=conditions[:5],
        recommended_next_steps=steps[:6],
        warning_signs=warning_signs,
        recognized_symptoms=recognized_symptoms[:8],
        confidence_score=round(confidence_score, 2),
        confidence_level=confidence_level,
        confidence_note=_build_confidence_note(confidence_level, recognized_symptoms, len(candidates)),
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
    kb = get_knowledge_base()
    context = kb.as_prompt_context(payload.symptoms, limit=5)

    age_context = payload.age_group or (str(payload.age) if payload.age is not None else "unknown")

    @tool
    def emergency_red_flags(symptoms: str) -> str:
        """Detect emergency warning signs from symptom text."""
        return json.dumps(detect_warning_signs(symptoms))

    @tool
    def dataset_matcher(symptoms: str) -> str:
        """Return best dataset-grounded disease matches, symptom extraction, descriptions, and precautions."""
        return json.dumps(kb.as_prompt_context(symptoms, limit=5))

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
                "Always ground your reasoning in dataset evidence. "
                "Call dataset_matcher before finalizing your answer, and call emergency_red_flags when symptoms may be severe. "
                "Prefer the top retrieved candidates over unsupported speculation. "
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

    agent = create_tool_calling_agent(llm=llm, tools=[emergency_red_flags, dataset_matcher], prompt=prompt)
    executor = AgentExecutor(agent=agent, tools=[emergency_red_flags, dataset_matcher], verbose=False)
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
        recognized_symptoms=(context.get("extracted_symptoms") or [])[:8],
        confidence_score=round(float(context.get("overall_confidence") or 0.0), 2),
        confidence_level=str(context.get("overall_confidence_level") or "low"),
        confidence_note=_build_confidence_note(
            str(context.get("overall_confidence_level") or "low"),
            list(context.get("extracted_symptoms") or []),
            len(context.get("candidates") or []),
        ),
        educational_disclaimer=parsed.get("educational_disclaimer") or DEFAULT_DISCLAIMER,
    )

    if not analysis.probable_conditions or not analysis.recommended_next_steps:
        return None

    return SymptomResponse(
        analysis=analysis,
        source="hybrid_agent",
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
    kb = get_knowledge_base()

    age_context = payload.age_group or (str(payload.age) if payload.age is not None else "unknown")
    grounded_context = kb.as_prompt_context(payload.symptoms, limit=5)
    detected = detect_warning_signs(payload.symptoms)

    system_prompt = (
        "You are a clinical education assistant. Do not provide a diagnosis. "
        "Return concise educational possibilities and safe next steps. "
        "You must use the supplied dataset retrieval context as your main evidence and avoid unsupported conditions. "
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
        f"Retrieved dataset context: {json.dumps(grounded_context)}\n"
        f"Detected red flags: {json.dumps(detected)}\n"
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
    merged_warning_signs = []
    for item in [*warning_signs, *detected]:
        if item and item not in merged_warning_signs:
            merged_warning_signs.append(item)

    analysis = SymptomCheckResult(
        probable_conditions=(parsed.get("probable_conditions") or [])[:5],
        recommended_next_steps=(parsed.get("recommended_next_steps") or [])[:6],
        warning_signs=merged_warning_signs,
        recognized_symptoms=(grounded_context.get("extracted_symptoms") or [])[:8],
        confidence_score=round(float(grounded_context.get("overall_confidence") or 0.0), 2),
        confidence_level=str(grounded_context.get("overall_confidence_level") or "low"),
        confidence_note=_build_confidence_note(
            str(grounded_context.get("overall_confidence_level") or "low"),
            list(grounded_context.get("extracted_symptoms") or []),
            len(grounded_context.get("candidates") or []),
        ),
        educational_disclaimer=parsed.get("educational_disclaimer") or DEFAULT_DISCLAIMER,
    )

    if not analysis.probable_conditions or not analysis.recommended_next_steps:
        return None

    return SymptomResponse(
        analysis=analysis,
        source="hybrid_llm",
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
