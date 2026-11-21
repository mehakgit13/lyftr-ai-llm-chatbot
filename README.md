# Lyftr AI – LLM Chatbot with API Key Failover and Response Caching

## Project Overview

Lyftr AI is a full-stack conversational AI application designed to provide reliable LLM-powered responses through automatic API key failover and response caching.

The application uses a React-based frontend, a FastAPI backend, LiteLLM for LLM integration, and SQLite for persistent conversation storage. It supports multi-turn conversations, per-response metadata, automatic recovery from provider failures, and cross-session response caching.

The system is designed to maintain service availability when an LLM provider encounters rate limits, quota restrictions, or server-side errors.

## Technology Stack

| Component | Technology |
|---|---|
| Frontend | React 18.3.1, Vite 6.3.5 |
| Backend | Python, FastAPI |
| LLM Gateway | LiteLLM |
| Database | SQLite |
| Response Caching | LiteLLM Disk Cache and Exact-Response Cache |
| Containerization | Docker and Docker Compose |
| Frontend Server | Nginx |
| Testing | Pytest |
| Runtime | Python 3.12+, Node.js 22+ |

## System Architecture

The application follows a client-server architecture in which the React frontend communicates with the FastAPI backend through REST API endpoints.

The backend manages conversation context, LLM requests, API key selection, failure recovery, response caching, metadata generation, and database persistence.

### Request Processing Workflow

1. The user submits a message through the React chat interface.
2. The frontend sends the message and session identifier to the FastAPI `/chat` endpoint.
3. The backend retrieves the relevant conversation history from SQLite.
4. The complete message context is prepared for LLM processing.
5. The caching layer checks whether an identical request has already been processed.
6. On a cache miss, LiteLLM routes the request to the configured LLM provider.
7. If the selected API key encounters a provider failure, the backend attempts the next configured key.
8. Once a successful response is received, the assistant reply and associated metadata are stored in SQLite.
9. The backend returns the response and request-specific metadata to the frontend.
10. The React interface renders the response using Markdown formatting.

### High-Level Architecture

```text
             USER
              |
              v
       REACT FRONTEND
         (Port 3000)
              |
              v
        FASTAPI BACKEND
         (Port 8000)
              |
       +------+------+
       |             |
       v             v
  SQLITE DATABASE   CACHE LAYER
  Session History   Response Lookup
       |             |
       +------+------+
              |
              v
          LITELLM
              |
       +------+------+
       |             |
       v             v
     API KEY 1     API KEY 2
       |             |
       +------+------+
              |
              v
       LLM RESPONSE
              |
              v
       METADATA AND
       RESPONSE STORAGE
              |
              v
       REACT CHAT UI
```

## Core Features

### 1. Automatic API Key Failover

The application implements sequential API key failover to improve availability when communicating with external LLM providers.

Two or more provider API keys can be configured through environment variables. The backend attempts the configured keys in priority order.

When a provider request fails, the backend attempts the next available key rather than immediately terminating the conversation request.

The implementation supports:

- HTTP 429 rate-limit failures.
- Provider server errors, including HTTP 5xx responses.
- Provider exceptions and unavailable responses.
- Automatic switching between configured keys.
- Tracking of the number of fallback attempts.
- HTTP 503 response when all configured providers fail.

The API key values are never included in the response metadata.

Failure simulation is available through the `X-Simulate-Failure` request header when `ENABLE_FAILURE_SIMULATION=true`.

### 2. Response Caching

The application implements response caching to reduce unnecessary LLM requests and improve response time.

LiteLLM disk caching is enabled for provider completions. An additional bounded in-memory response index provides deterministic cache-hit identification and preserves the original response and token usage.

The cache identity is based on:

- Selected model.
- Complete ordered message context.
- System prompt, when provided.
- Previous conversation turns.
- Current user message.

An identical request made in a new session can therefore be served from the cache when its complete message context matches.

Cache responses retain the original assistant reply and token usage while returning:

- `resolution_source`: `LLM_CACHE`
- `key_id`: `null`
- `fallback_attempts`: `0`

The in-memory response index is cleared when the backend restarts.

### 3. Multi-Turn Conversation Management

Each conversation is associated with a unique session identifier.

The backend retrieves previous messages belonging to the session and includes the relevant conversation context when preparing subsequent LLM requests.

Conversation messages are persisted in SQLite, allowing the application to maintain session history independently of the frontend page state.

The history endpoint returns messages in chronological order and excludes system prompts.

### 4. SQLite Persistence

SQLite provides lightweight and persistent conversation storage.

The `messages` table is created automatically during backend startup.

Stored information includes:

- Message identifier.
- Session identifier.
- Message role.
- Message content.
- Response metadata.
- Creation timestamp.

Only successfully processed user and assistant messages are stored. Failed requests are not added to conversation history.

In Docker deployments, the database is stored at `/data/app.db` using a named Docker volume.

### 5. Per-Response Metadata

Every successful assistant response includes request-specific execution metadata.

| Field | Description |
|---|---|
| `resolution_source` | Indicates `LIVE_INFERENCE` or `LLM_CACHE` |
| `model` | Model used to generate the response |
| `latency_ms` | Measured request latency |
| `input_tokens` | Input tokens for the current request |
| `output_tokens` | Output tokens for the current response |
| `key_id` | API key identifier used for live inference; null for cache hits |
| `fallback_attempts` | Number of failed provider attempts before success |

Token usage is reported per response rather than accumulated across the conversation.

### 6. Frontend Interface

The React frontend provides a responsive conversational interface with:

- Multi-turn chat functionality.
- Unique conversation sessions.
- Optional system prompt configuration.
- Markdown-rendered assistant responses.
- Formatted headings, lists, tables and code blocks.
- Backend health indicator.
- Loading animation.
- Response metadata display.
- Readable error messages.
- Error Boundary for unexpected rendering failures.

The interface remains usable when the backend returns an error such as HTTP 503.

## API Endpoints

### Health Check

`GET /health`

Returns the backend health status, configured API key count, and cache availability.

Example response:

```json
{
  "status": "ok",
  "keys_configured": 2,
  "cache_enabled": true
}
```

### Chat Completion

`POST /chat`

Accepts a session identifier, user message, and optional system prompt.

Example request:

```json
{
  "session_id": "demo-session-001",
  "message": "Explain artificial intelligence.",
  "system_prompt": "Provide clear and concise explanations."
}
```

The response includes the generated reply and execution metadata.

### Conversation History

`GET /sessions/{session_id}/messages`

Retrieves the chronological message history for a particular session.

The endpoint returns user and assistant messages without exposing system prompts.

### Provider Failure Response

When all configured providers are unavailable, the endpoint returns HTTP 503:

```json
{
  "detail": "all providers unavailable"
}
```

Failed requests are not persisted in the conversation history.

## Project Structure

```text
lyftr-ai-fullstack-assignment/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   └── ...
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── main.jsx
│   │   └── style.css
│   ├── index.html
│   ├── package.json
│   ├── nginx.conf
│   └── Dockerfile
│
├── docker-compose.yml
├── Makefile
├── .env.example
├── .gitignore
└── README.md
```

## Installation and Execution

### Docker Deployment

The application uses Docker Compose to build and run the frontend and backend services.

Configuration is supplied through environment variables. Provider credentials are maintained outside the source code.

The following commands manage the application:

```bash
make up
```

The command builds and starts the application services.

```bash
make down
```

The command stops and removes the application containers.

The application exposes the following local endpoints:

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend | http://localhost:8000 |
| API Documentation | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

### Local Development Without Docker

The backend can be executed independently using Python and a virtual environment.

```bash
cd backend
python -m venv .venv
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The frontend can be executed independently using Node.js and Vite.

```bash
cd frontend
npm install
npm run dev
```

The Vite development server runs on port 5173 by default.

## Environment Configuration

The application uses environment variables for runtime configuration.

Important configuration parameters include:

| Variable | Purpose |
|---|---|
| `LLM_API_KEYS` | Configured provider API keys |
| `LLM_MODEL` | Selected LLM model |
| `DATABASE_URL` | SQLite database connection |
| `ALLOWED_ORIGINS` | Permitted frontend origins |
| `VITE_API_URL` | Backend URL used by the frontend |
| `ENABLE_FAILURE_SIMULATION` | Enables controlled provider failure testing |
| `MOCK_LLM` | Enables mock inference mode |

Provider credentials are maintained in the local `.env` file and are excluded from version control.

## Verification and Testing

The application was tested against the main functional requirements of the assignment.

### Functional Verification

| Test Case | Observed Result |
|---|---|
| Backend health endpoint | Successful |
| Live LLM inference | Successful |
| Multi-turn conversation | Successful |
| SQLite message persistence | Successful |
| Cross-session cache hit | Successful |
| Cache response metadata | Successful |
| First-key failure and second-key fallback | Successful |
| All-provider failure | HTTP 503 |
| Failed request persistence | Failed request not stored |
| Frontend error handling | Readable error displayed |
| Markdown response rendering | Successful |
| Response metadata display | Successful |

### Cache Verification

An identical first message was submitted using two different session identifiers.

The initial request returned `LIVE_INFERENCE`, while the subsequent identical request returned `LLM_CACHE`.

The cached response retained the original reply and token usage.

### Failover Verification

A simulated HTTP 429 failure was applied to the first API key.

The backend successfully switched to the second API key, returning a successful response with:

```json
{
  "resolution_source": "LIVE_INFERENCE",
  "key_id": "key_2",
  "fallback_attempts": 1
}
```

### All-Provider Failure Verification

A simulated failure was applied to both configured API keys.

The backend returned HTTP 503 with the expected error response. A subsequent history lookup confirmed that the failed session was not persisted.

### Frontend Error Verification

The frontend was tested with a simulated HTTP 503 response.

The user message remained visible, the application displayed a readable error banner, and the chat interface remained functional.

### Automated Tests

Backend automated tests are executed using:

```bash
cd backend
pytest -q
```

## Design Decisions

### Sequential Failover

Sequential API key selection provides a straightforward recovery mechanism while maintaining a predictable provider priority order.

### Combined Caching Strategy

LiteLLM caching and an exact-response index provide provider-level caching and deterministic response identification.

### SQLite Storage

SQLite was selected to provide persistent session history without requiring a separate database server.

### Docker-Based Execution

Docker Compose provides a consistent environment for running the frontend and backend services and simplifies application startup and shutdown.

### Separation of Responsibilities

The React frontend handles user interaction and response presentation, while FastAPI manages inference, provider selection, caching, persistence and metadata generation.

## Deployment

The frontend and backend are designed to be deployed as separate services.

The backend requires:

- A public service URL.
- Two configured provider API keys.
- A valid model configuration.
- A persistent storage location mounted at `/data`.
- An appropriate frontend origin in `ALLOWED_ORIGINS`.

The frontend requires:

- A production build using Vite.
- The public backend URL configured through `VITE_API_URL`.
- A static hosting environment capable of serving the generated `dist` directory.


## Deployment URLs

| Resource | URL |
|---|---|
| Public Frontend | https://lyftr-aichatbot-hsvlt0mtm-mehakgit13.vercel.app/ |
| Public Backend | https://lyftr-ai-llm-chatbot-5xyz.onrender.com |
| Backend Health Check | https://lyftr-ai-llm-chatbot-5xyz.onrender.com/health |
| API Documentation | https://lyftr-ai-llm-chatbot-5xyz.onrender.com/docs |

## GitHub Repository

https://github.com/mehakgit13/lyftr-ai-llm-chatbot

## Setup and Development Environment

| Item | Configuration |
|---|---|
| Operating System | Windows 11 |
| IDE | Visual Studio Code |
| Frontend Runtime | Node.js 22 |
| Frontend Framework | React 18 |
| Backend Runtime | Python |
| Backend Framework | FastAPI |
| LLM Integration | LiteLLM |
| Database | SQLite |
| Containerization | Docker Desktop and Docker Compose |
| Version Control | Git and GitHub |

## Bonus Features

The application additionally includes:

- Responsive dark-themed interface.
- Optional session-specific system prompt.
- Real-time backend health indicator.
- Markdown-rendered AI responses.
- Readable frontend error handling.
- Error Boundary for unexpected rendering failures.
- Bounded in-memory exact-response cache.

## Security Considerations

- API credentials are supplied through environment variables.
- Secrets are excluded from the Git repository.
- API key values are not returned in response metadata.
- Failure simulation is controlled through an environment variable.
- The production configuration disables mock inference and failure simulation.

## Demonstration

The project demonstration covers the following application capabilities:

1. Frontend interface and live LLM interaction.
2. Multi-turn conversation handling.
3. Per-response metadata.
4. Cross-session response caching.
5. Automatic API key failover.
6. Handling of complete provider failure.
7. Persistent conversation history.

