const configuredApiBase = (window.APP_CONFIG?.API_BASE || "").trim();
const isLocalHost = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost";
const isRenderFrontend = window.location.hostname.endsWith(".onrender.com");

let API_BASE = configuredApiBase;

if (!API_BASE) {
  if (isLocalHost) {
    API_BASE = "http://127.0.0.1:8000";
  } else if (isRenderFrontend) {
    API_BASE = "https://symptoscan-api.onrender.com";
  }
}

if (window.location.protocol === "https:" && API_BASE.startsWith("http://")) {
  API_BASE = API_BASE.replace("http://", "https://");
}

const form = document.getElementById("symptom-form");
const submitBtn = document.getElementById("submit-btn");
const resultSection = document.getElementById("result");
const ageSelect = document.getElementById("age");
const sexSelect = document.getElementById("sex");
const sourcePill = document.getElementById("source-pill");
const sourceNote = document.getElementById("source-note");
const confidencePanel = document.getElementById("confidence-panel");
const confidencePill = document.getElementById("confidence-pill");
const confidenceNote = document.getElementById("confidence-note");
const conditions = document.getElementById("conditions");
const steps = document.getElementById("steps");
const recognizedSymptoms = document.getElementById("recognized-symptoms");
const warnings = document.getElementById("warnings");
const disclaimer = document.getElementById("disclaimer");
const themeToggle = document.getElementById("theme-toggle");

const THEME_KEY = "symptoscan-theme";

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeToggle.textContent = theme === "dark" ? "Light mode" : "Dark mode";
  themeToggle.setAttribute("aria-pressed", String(theme === "dark"));
}

function initTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === "dark" || saved === "light") {
    applyTheme(saved);
    return;
  }

  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(prefersDark ? "dark" : "light");
}

themeToggle.addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
});

initTheme();

const SOURCE_META = {
  hybrid_agent: {
    label: "Hybrid Agent",
    note: "The answer was produced by the tool-calling agent after checking your dataset matches and red flags first.",
  },
  hybrid_llm: {
    label: "Hybrid LLM",
    note: "The answer was written by the LLM, but only after grounding it with ranked dataset candidates and safety checks.",
  },
  rule_based: {
    label: "Dataset Fallback",
    note: "The answer came directly from dataset matching and rule-based safety logic without using the LLM.",
  },
};

const CONFIDENCE_META = {
  high: { label: "High Confidence", className: "confidence-high" },
  medium: { label: "Medium Confidence", className: "confidence-medium" },
  low: { label: "Low Confidence", className: "confidence-low" },
};

function renderList(node, values, warning = false) {
  node.innerHTML = "";
  const items = values && values.length ? values : ["None reported"];
  for (const value of items) {
    const li = document.createElement("li");
    li.textContent = value;
    if (warning && value !== "None reported") {
      li.classList.add("warning-item");
    }
    node.appendChild(li);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const symptoms = document.getElementById("symptoms").value.trim();
  if (!symptoms) {
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = "Analyzing...";

  const ageGroup = ageSelect.value.trim();
  const sex = sexSelect.value.trim();
  const duration = document.getElementById("duration").value.trim();

  const payload = {
    symptoms,
    age: null,
    age_group: ageGroup || null,
    sex: sex || null,
    duration: duration || null,
  };

  try {
    const endpoint = API_BASE ? `${API_BASE}/api/check-symptoms` : "/api/check-symptoms";

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(`API returned ${response.status}`);
    }

    const data = await response.json();
    const sourceMeta = SOURCE_META[data.source] || {
      label: data.source,
      note: "The backend returned this response source.",
    };

    sourcePill.textContent = `Mode: ${sourceMeta.label}`;
    sourceNote.textContent = sourceMeta.note;

    const confidence = data.analysis.confidence_level || "low";
    const confidenceScore = Number(data.analysis.confidence_score || 0);
    const confidenceMeta = CONFIDENCE_META[confidence] || CONFIDENCE_META.low;
    confidencePanel.className = `confidence-panel ${confidenceMeta.className}`;
    confidencePill.textContent = `${confidenceMeta.label} • ${Math.round(confidenceScore * 100)}%`;
    confidenceNote.textContent = data.analysis.confidence_note || "Confidence information was not provided.";

    renderList(conditions, data.analysis.probable_conditions);
    renderList(steps, data.analysis.recommended_next_steps);
    renderList(recognizedSymptoms, data.analysis.recognized_symptoms);
    renderList(warnings, data.analysis.warning_signs, true);
    disclaimer.textContent = data.analysis.educational_disclaimer;

    resultSection.classList.remove("hidden");
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    alert(`Unable to process request: ${error.message}`);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Analyze Symptoms";
  }
});
