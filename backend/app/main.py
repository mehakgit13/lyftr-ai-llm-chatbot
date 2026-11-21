import hashlib, json, os, re, sqlite3, time
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

try:
    import litellm
    from litellm import Cache
except Exception:  # Allows tests and MOCK_LLM mode to run before dependencies are installed.
    litellm = None
    Cache = None

APP_TITLE = "Lyftr LLM Chatbot"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
DB_PATH = DATABASE_URL.replace("sqlite:///", "", 1) if DATABASE_URL.startswith("sqlite:///") else DATABASE_URL
if DB_PATH.startswith("//"):
    DB_PATH = "/" + DB_PATH.lstrip("/")
DEFAULT_MODEL = os.getenv("LLM_MODEL", "gemini/gemini-3.5-flash-lite")
DEFAULT_SYSTEM_PROMPT = "You are a helpful, accurate assistant. Keep answers clear and useful."
MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"
ENABLE_FAILURE_SIMULATION = os.getenv("ENABLE_FAILURE_SIMULATION", "false").lower() == "true"
API_KEYS = [x.strip() for x in os.getenv("LLM_API_KEYS", "").split(",") if x.strip()]
KEYS = [(f"key_{i+1}", key) for i, key in enumerate(API_KEYS)]

# LiteLLM's own disk cache is enabled for provider calls. The small in-process index
# below gives us deterministic cache-hit metadata and guarantees the assignment's
# exact cache-key semantics (model + full message list).
if litellm is not None and Cache is not None:
    try:
        os.makedirs("/tmp/litellm-cache", exist_ok=True)
        litellm.cache = Cache(type="disk", disk_cache_dir="/tmp/litellm-cache")
        litellm.enable_cache()
    except Exception:
        # Some LiteLLM versions configure caching through completion(caching=True).
        pass

app = FastAPI(title=APP_TITLE, version="1.0.0")
origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    system_prompt: Optional[str] = None

    @field_validator("message")
    @classmethod
    def trim_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be empty")
        return value

class ChatMetadata(BaseModel):
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str]
    fallback_attempts: int

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata

@contextmanager
def db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_id_id ON messages(session_id, id)")

init_db()

# LRU response index: keys are based on model + the exact full message list.
_RESPONSE_CACHE = OrderedDict()
_CACHE_LIMIT = int(os.getenv("RESPONSE_CACHE_SIZE", "500"))

def cache_key(model: str, messages: list[dict]) -> str:
    raw = json.dumps({"model": model, "messages": messages}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def simulated_status(header: Optional[str], key_id: str) -> Optional[int]:
    if not ENABLE_FAILURE_SIMULATION or not header:
        return None
    for item in header.split(","):
        if "=" not in item:
            continue
        name, status = item.strip().split("=", 1)
        if name.strip() in (key_id, "*"):
            try:
                code = int(status.strip())
                if code in (429, 500, 502, 503):
                    return code
            except ValueError:
                continue
    return None

def mock_completion(messages: list[dict], model: str):
    question = messages[-1]["content"]
    prior = sum(1 for m in messages if m["role"] == "user")
    answer = f"Mock AI response: {question}\n\nThis is a local demonstration response (turn {prior}). Configure real LLM_API_KEYS and MOCK_LLM=false for live model inference."
    return {"reply": answer, "input_tokens": max(1, sum(len(m["content"].split()) for m in messages)), "output_tokens": max(1, len(answer.split())), "model": model}

def call_provider(messages: list[dict], model: str, api_key: str):
    if MOCK_LLM:
        return mock_completion(messages, model)
    if litellm is None:
        raise RuntimeError("LiteLLM is not installed")
    response = litellm.completion(model=model, messages=messages, api_key=api_key, caching=True, temperature=0.4)
    choice = response.choices[0].message
    usage = getattr(response, "usage", None)
    return {
        "reply": choice.content or "",
        "input_tokens": int(getattr(usage, "prompt_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "completion_tokens", 0) or 0),
        "model": getattr(response, "model", model) or model,
    }

def persist(session_id: str, role: str, content: str, metadata=None):
    with db() as conn:
        conn.execute("INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
                     (session_id, role, content, json.dumps(metadata) if metadata is not None else None,
                      datetime.now(timezone.utc).isoformat()))

def session_history(session_id: str):
    with db() as conn:
        rows = conn.execute("SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    return [{"role": r["role"], "content": r["content"], **({"metadata": json.loads(r["metadata"])} if r["metadata"] else {})} for r in rows]

@app.get("/health")
def health():
    try:
        with db() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok", "keys_configured": len(KEYS) if not MOCK_LLM else max(2, len(KEYS)), "cache_enabled": True}
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")

@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, x_simulate_failure: Optional[str] = Header(default=None, alias="X-Simulate-Failure")):
    if not request.session_id.strip():
        raise HTTPException(status_code=422, detail="session_id must not be empty")
    # Load existing conversation; the system prompt is never persisted or returned.
    history = session_history(request.session_id)
    prior_messages = [{"role": m["role"], "content": m["content"]} for m in history]
    system_prompt = request.system_prompt.strip() if request.system_prompt and request.system_prompt.strip() else DEFAULT_SYSTEM_PROMPT
    messages = [{"role": "system", "content": system_prompt}, *prior_messages, {"role": "user", "content": request.message}]
    model = DEFAULT_MODEL
    key = cache_key(model, messages)
    started = time.perf_counter()
    cached = _RESPONSE_CACHE.get(key)
    if cached is not None:
        _RESPONSE_CACHE.move_to_end(key)
        elapsed = max(1, int((time.perf_counter() - started) * 1000))
        # Keep cache hits measurably quick; live provider latency is measured independently.
        metadata = {"resolution_source": "LLM_CACHE", "model": cached["model"], "latency_ms": elapsed,
                    "input_tokens": cached["input_tokens"], "output_tokens": cached["output_tokens"],
                    "key_id": None, "fallback_attempts": 0}
        persist(request.session_id, "user", request.message)
        persist(request.session_id, "assistant", cached["reply"], metadata)
        return {"session_id": request.session_id, "reply": cached["reply"], "metadata": metadata}

    # In mock mode, synthetic keys allow the failure hook to be demonstrated safely.
    key_pool = KEYS if KEYS else ([ ("key_1", "mock-key-1"), ("key_2", "mock-key-2") ] if MOCK_LLM else [])
    if not key_pool:
        raise HTTPException(status_code=503, detail="all providers unavailable")
    failures = 0
    last_error = None
    for key_id, api_key in key_pool:
        simulated = simulated_status(x_simulate_failure, key_id)
        if simulated is not None:
            failures += 1
            last_error = simulated
            continue
        try:
            result = call_provider(messages, model, api_key)
            reply = str(result["reply"] or "").strip()
            if not reply:
                raise RuntimeError("provider returned an empty reply")
            elapsed = max(1, int((time.perf_counter() - started) * 1000))
            metadata = {"resolution_source": "LIVE_INFERENCE", "model": result["model"], "latency_ms": elapsed,
                        "input_tokens": int(result["input_tokens"]), "output_tokens": int(result["output_tokens"]),
                        "key_id": key_id, "fallback_attempts": failures}
            _RESPONSE_CACHE[key] = {"reply": reply, "model": result["model"], "input_tokens": metadata["input_tokens"], "output_tokens": metadata["output_tokens"]}
            _RESPONSE_CACHE.move_to_end(key)
            while len(_RESPONSE_CACHE) > _CACHE_LIMIT:
                _RESPONSE_CACHE.popitem(last=False)
            persist(request.session_id, "user", request.message)
            persist(request.session_id, "assistant", reply, metadata)
            return {"session_id": request.session_id, "reply": reply, "metadata": metadata}
        except Exception as exc:
            last_error = exc
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            # Assignment requires failover on rate limits, quota and 5xx. Other provider
            # errors are also attempted on the next configured key for resilience.
            failures += 1
            continue
    raise HTTPException(status_code=503, detail="all providers unavailable")

@app.get("/sessions/{session_id}/messages")
def get_messages(session_id: str):
    history = session_history(session_id)
    if not history:
        raise HTTPException(status_code=404, detail="session not found")
    return {"session_id": session_id, "messages": history}
