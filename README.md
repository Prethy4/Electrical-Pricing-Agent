# Chat Agent API

A production-ready, modular chat agent built with **FastAPI**, **LangGraph**, **LangChain**, and **OpenAI**. Supports PDF/CSV file understanding per session, PostgreSQL-backed persistent memory, and a plug-in tool registry.

---

## Features

| Feature | Detail |
|---|---|
| 🧠 **LangGraph ReAct Agent** | Tool-calling loop with conditional routing |
| 💾 **Session Memory** | Full message history stored in PostgreSQL, last 10 messages loaded per turn |
| 📄 **PDF/CSV/XLSX Understanding** | Text, tables, and schema extracted, chunked, and embedded via FAISS |
| 🛠️ **Modular Tools** | Drop a `@tool` function in `registry.py` or add in `tools/` to extend the agent |
| 🗄️ **PostgreSQL** | Sessions, messages, and file metadata — with Alembic migrations |
| 🐳 **Docker Compose** | One command to run the full stack |
| 🖥️ **Streamlit UI** | Modern web interface for chat and file upload |

---

## Project Structure

```
chat-agent/
├── app/
│   ├── main.py                  # FastAPI app entrypoint & lifespan
│   ├── config.toml              # Streamlit theme config
│   ├── files.py                 # File upload & processing router
│   ├── pdf_structured.py        # PDF layout-aware parsing
│   ├── streamlit_app.py         # Streamlit web UI
│   ├── core/
│   │   └── config.py            # Pydantic settings (.env)
│   ├── api/
│   │   ├── chat.py              # POST /api/v1/chat
│   │   ├── sessions.py          # CRUD /api/v1/sessions
│   │   ├── health.py            # GET /api/v1/health
│   ├── agents/
│   │   └── graph.py             # LangGraph graph definition
│   ├── tools/
│   │   ├── registry.py          # Tool registry (add new tools here)
│   │   ├── example_tool.py      # Example custom tool
│   │   ├── csv_tool.py          # CSV utilities
│   │   ├── pdf_tool.py          # PDF utilities
│   │   ├── web_scraper.py       # Web scraping tool
│   │   ├── vector_store.py      # FAISS vector store helpers
│   │   └── state.py             # Tool state management
│   ├── services/
│   │   ├── chat_service.py      # Orchestrates memory + agent + DB
│   │   ├── file_service.py      # PDF/CSV ingestion + FAISS
│   │   ├── memory_service.py    # Load/save LangChain messages
│   │   ├── article_parser.py    # Article code extraction
│   │   ├── context_builder.py   # Context tree builder
│   │   ├── csv_schema_inference.py # CSV schema inference
│   │   ├── pdf_mapper.py        # PDF article mapping
│   │   └── web_service.py       # Web-related services
│   ├── db/
│   │   ├── database.py          # SQLAlchemy async engine
│   │   └── repositories.py      # Data access layer
│   └── models/
│       ├── db_models.py         # SQLAlchemy ORM models
│       └── schemas.py           # Pydantic request/response schemas
├── migrations/
│   ├── env.py                   # Alembic env
│   ├── script.py.mako           # Alembic script template
│   └── versions/                # Migration versions
├── uploads/                     # Uploaded files (per session)
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── alembic.ini
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

### Chat Endpoint

```http
POST /api/v1/chat
Content-Type: application/json
{
  "message": "Summarise the uploaded report",
  "session_id": "optional-uuid-to-continue-a-session"
}
```
Omit `session_id` to start a new session. The response includes the new `session_id` — store it on the client.

### Sessions Endpoint

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v1/sessions` | List all sessions |
| `POST` | `/api/v1/sessions` | Create session explicitly |
| `GET` | `/api/v1/sessions/{id}` | Get session + history + files |
| `DELETE` | `/api/v1/sessions/{id}` | Delete session and all its messages/files |

### File Upload Endpoint

```http
POST /api/v1/files/upload/{session_id}
Content-Type: multipart/form-data
files=<pdf/csv/xlsx file>
files=<another file>
```
Supported formats: `.pdf`, `.csv`, `.xlsx`  
Default max size: 1000 MB (configurable via `MAX_FILE_SIZE_MB`)

After uploading, all subsequent messages in the session can reference the file contents — the agent will automatically use `search_uploaded_documents` when relevant.

---

## Adding a New Tool

1. Open or create a file in `app/tools/` (e.g. `my_tool.py`).
2. Define your tool:
   ```python
   from langchain_core.tools import tool
   @tool
   def my_new_tool(input: str) -> str:
     """Description the LLM uses to decide when to call this tool."""
     # your logic
     return result
   ```
3. Import and add it to `REGISTERED_TOOLS` in `app/tools/registry.py`:
   ```python
   from app.tools.my_tool import my_new_tool
   REGISTERED_TOOLS = [
     ...,
     my_new_tool,
   ]
   ```
That's all — the agent graph picks up tools dynamically at request time.

---

## Memory Design

- Every human and AI message is saved to PostgreSQL immediately after each turn.
- On each new turn, the **10 most recent messages** are loaded and prepended to the LLM context (configurable in `memory_service.py`).
- The FAISS vector index lives in memory, scoped per `session_id`. On server restart, files must be re-uploaded. For production, replace FAISS with `pgvector` or a persistent vector store.

---

## Streamlit App Usage

The project includes a modern Streamlit web UI for interactive chat and file upload.

### Launch the UI

```bash
streamlit run app/streamlit_app.py
```

### Features

- Start new chat sessions and view history
- Upload PDF, CSV, or XLSX files for analysis
- Download processed/updated files
- Chat with the agent and get contextual answers

The UI connects to the FastAPI backend at `http://localhost:8000` by default. You can adjust the API URL in `streamlit_app.py` if needed.

---

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-5.1` | Chat model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `DATABASE_URL` | — | Async PostgreSQL URL (`postgresql+asyncpg://...`) |
| `DATABASE_URL_SYNC` | — | Sync URL for Alembic (`postgresql://...`) |
| `MAX_FILE_SIZE_MB` | `1000` | Upload size limit |
| `UPLOAD_DIR` | `uploads` | Local path to store uploaded files |
| `DEBUG` | `true` | Enable SQLAlchemy query logging |test
