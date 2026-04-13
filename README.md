# Chat Agent API

A production-ready, modular chat agent built with **FastAPI**, **LangGraph**, **LangChain**, and **OpenAI**. Supports PDF/CSV file understanding per session, PostgreSQL-backed persistent memory, and a plug-in tool registry.

---

## Features

| Feature | Detail |
|---|---|
| 🧠 **LangGraph ReAct Agent** | Tool-calling loop with conditional routing |
| 💾 **Session Memory** | Full message history stored in PostgreSQL, last 40 messages loaded per turn |
| 📄 **PDF Understanding** | Text extracted, chunked, and embedded via FAISS |
| 📊 **CSV Understanding** | Schema + row batches embedded for semantic search |
| 🔧 **Modular Tools** | Drop a `@tool` function in `registry.py` to extend the agent |
| 🐘 **PostgreSQL** | Sessions, messages, and file metadata — with Alembic migrations |
| 🐳 **Docker Compose** | One command to run the full stack |

---

## Project Structure

```
chat-agent/
├── app/
│   ├── main.py                  # FastAPI app + lifespan
│   ├── core/
│   │   └── config.py            # Pydantic settings (.env)
│   ├── api/
│   │   ├── chat.py              # POST /api/v1/chat
│   │   ├── sessions.py          # CRUD /api/v1/sessions
│   │   ├── files.py             # POST /api/v1/files/upload
│   │   └── health.py            # GET /health
│   ├── agents/
│   │   └── graph.py             # LangGraph graph definition
│   ├── tools/
│   │   ├── registry.py          # ← ADD NEW TOOLS HERE
│   │   └── example_tool.py      # Example custom tool
│   ├── services/
│   │   ├── chat_service.py      # Orchestrates memory + agent + DB
│   │   ├── file_service.py      # PDF/CSV ingestion + FAISS
│   │   └── memory_service.py    # Load/save LangChain messages
│   ├── db/
│   │   ├── database.py          # SQLAlchemy async engine
│   │   └── repositories.py      # Data access layer
│   └── models/
│       ├── db_models.py         # SQLAlchemy ORM models
│       └── schemas.py           # Pydantic request/response schemas
├── migrations/                  # Alembic migrations
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Quick Start

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY at minimum
```

### 2. Run with Docker Compose

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 3. Run locally (without Docker)

```bash
# Start PostgreSQL separately, then:
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload
```

> **Note:** Tables are also auto-created on startup via `init_db()`, so Alembic is optional for development.

---

## API Reference

### Chat

```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "Summarise the uploaded report",
  "session_id": "optional-uuid-to-continue-a-session"
}
```

Omit `session_id` to start a new session automatically. The response includes the new `session_id` — store it on the client.

---

### Sessions

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/sessions` | List all sessions |
| `POST` | `/api/v1/sessions` | Create session explicitly |
| `GET` | `/api/v1/sessions/{id}` | Get session + history + files |
| `DELETE` | `/api/v1/sessions/{id}` | Delete session |

---

### File Upload

```http
POST /api/v1/files/upload
Content-Type: multipart/form-data

session_id=<uuid>
file=<pdf or csv file>
```

Supported formats: `.pdf`, `.csv`  
Default max size: 20 MB (configurable via `MAX_FILE_SIZE_MB`)

After uploading, all subsequent messages in the session can reference the file contents — the agent will automatically use `search_uploaded_documents` when relevant.

---

## Adding a New Tool

1. Open `app/tools/registry.py`
2. Define your tool:

```python
from langchain_core.tools import tool

@tool
def my_new_tool(input: str) -> str:
    """Description the LLM uses to decide when to call this tool."""
    # your logic
    return result
```

3. Add it to `REGISTERED_TOOLS`:

```python
REGISTERED_TOOLS = [
    calculator,
    get_current_datetime,
    my_new_tool,   # ← added
]
```

That's all — no other changes needed. The graph picks up tools dynamically at request time.

For tools in separate files, just import them:

```python
from app.tools.my_module import my_new_tool
```

---

## Memory Design

- Every human and AI message is saved to PostgreSQL immediately after each turn.
- On each new turn, the **40 most recent messages** are loaded and prepended to the LLM context.
- The FAISS vector index lives in memory, scoped per `session_id`. On server restart, files must be re-uploaded. For production, replace FAISS with `pgvector` or a persistent vector store.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4o` | Chat model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `DATABASE_URL` | — | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | — | Sync URL for Alembic (`postgresql://...`) |
| `MAX_FILE_SIZE_MB` | `20` | Upload size limit |
| `UPLOAD_DIR` | `uploads` | Local path to store uploaded files |
| `DEBUG` | `true` | Enable SQLAlchemy query logging |
