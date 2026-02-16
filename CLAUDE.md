# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Open WebUI is a self-hosted AI platform with a Python FastAPI backend and SvelteKit frontend. It supports multiple LLM providers (Ollama, OpenAI-compatible APIs), has built-in RAG capabilities with 9 vector database options, and includes features like image generation, audio/video calls, Python function calling, and enterprise authentication.

## Development Setup

### Backend (Python FastAPI)

**Starting the backend for development:**
```bash
cd backend
bash dev.sh
```

This runs uvicorn with auto-reload on port 8080 with CORS enabled for localhost:5173 and localhost:8080.

**Alternative direct command:**
```bash
cd backend
PORT=8080 uvicorn open_webui.main:app --port 8080 --host 0.0.0.0 --forwarded-allow-ips '*' --reload
```

**Install backend dependencies:**
```bash
pip install -e .
# or for development with all optional dependencies:
pip install -e ".[all]"
```

**Running backend tests:**
```bash
pytest backend/open_webui/test/
```

**Linting backend:**
```bash
npm run lint:backend
# or directly:
pylint backend/
```

**Formatting backend:**
```bash
npm run format:backend
# or directly:
black . --exclude ".venv/|/venv/"
```

### Frontend (SvelteKit)

**Starting the frontend dev server:**
```bash
npm run dev
# Runs on http://localhost:5173 by default
```

**Building the frontend:**
```bash
npm run build
```

**Running frontend tests:**
```bash
npm run test:frontend
# Uses vitest
```

**Linting:**
```bash
npm run lint:frontend  # ESLint with auto-fix
npm run lint:types     # Svelte type checking
npm run lint           # Runs both frontend, types, and backend linting
```

**Formatting:**
```bash
npm run format
# Uses Prettier for JS, TS, Svelte, CSS, MD, HTML, JSON files
```

**End-to-end tests:**
```bash
npm run cy:open
# Opens Cypress test runner (requires backend running on port 8080)
```

### Full Stack Development

**Running both backend and frontend:**
1. Terminal 1: `cd backend && bash dev.sh`
2. Terminal 2: `npm run dev`

Access the app at http://localhost:5173 (frontend dev server proxies API requests to backend at :8080)

### Docker Development

```bash
# Build and start with docker-compose
docker-compose up -d --build

# Using Makefile shortcuts
make install        # docker-compose up -d
make startAndBuild  # docker-compose up -d --build
make stop           # docker-compose stop
```

## Architecture

### Backend Structure

The backend is located in `backend/open_webui/` with the following organization:

- **`main.py`**: FastAPI application entry point, mounts all routers, configures middleware (CORS, compression, sessions, audit logging), handles WebSocket connections via `socket_app`
- **`routers/`**: API route handlers (27 routers including auths, chats, channels, files, functions, images, knowledge, models, ollama, openai, pipelines, retrieval, users, etc.)
- **`models/`**: Database models using SQLAlchemy and Peewee (chats, users, files, functions, knowledge, memories, channels, groups, etc.)
- **`internal/db.py`**: Database connection setup, supports SQLite (with optional SQLCipher encryption), PostgreSQL, handles both Peewee and SQLAlchemy migrations
- **`migrations/`**: Alembic database migrations
- **`retrieval/`**: RAG implementation with loaders, vector databases, and web search integrations
- **`socket/`**: WebSocket handlers for real-time features
- **`storage/provider.py`**: Abstraction for file storage (local, S3, Google Cloud Storage, Azure Blob Storage)
- **`utils/`**: Utility modules including auth, access control, audit logging, chat utilities, embeddings, filters, middleware (185KB middleware.py handles pipelines, tools, and processing)
- **`tools/`**: Built-in tool implementations
- **`env.py`**: Environment configuration, loads .env files, configures device type (CPU/CUDA/MPS), logging levels

### Frontend Structure

The frontend is a SvelteKit 2.x application in `src/`:

- **`routes/`**: SvelteKit file-based routing
  - `routes/(app)/`: Main application routes (protected by auth)
  - `routes/auth/`: Authentication pages
  - `routes/error/`: Error pages
- **`lib/components/`**: Svelte components organized by feature (admin, chat, workspace, channel, common, icons, layout, notes, playground)
- **`lib/apis/`**: Frontend API client modules (one per backend router)
- **`lib/stores/index.ts`**: Svelte stores for global state management
- **`lib/utils/`**: Frontend utility functions
- **`lib/i18n/`**: Internationalization support with translations in `locales/`
- **`lib/pyodide/`**: Python code execution in the browser using Pyodide

**Key Frontend Dependencies:**
- Svelte 5.x with TypeScript
- TipTap for rich text editing
- CodeMirror for code editing
- Pyodide for Python execution in browser
- Chart.js, Mermaid for visualizations
- Socket.io-client for WebSocket connections
- Y.js for collaborative editing

### Database

**Supported databases:**
- SQLite (default, with optional SQLCipher encryption)
- PostgreSQL (with pgvector extension for RAG)

**Migrations:** The project uses both Peewee migrations (legacy) and Alembic migrations. Peewee migrations run first, then Alembic migrations.

**Connection:** Configured via `DATABASE_URL` environment variable. The system supports connection pooling for PostgreSQL and Redis-backed sessions for horizontal scalability.

### Key Integration Points

**RAG System:**
- Vector databases: ChromaDB (default), PGVector, Qdrant, Milvus, Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle 23ai
- Content extraction engines: Tika, Docling, Document Intelligence, Mistral OCR
- Web search providers: 15+ including SearXNG, Google PSE, Brave, Kagi, DuckDuckGo, Perplexity

**Authentication:**
- LDAP/Active Directory integration
- OAuth providers
- SCIM 2.0 for automated provisioning
- SSO via trusted headers
- Role-based access control (RBAC)

**LLM Providers:**
- Ollama integration (`routers/ollama.py`)
- OpenAI-compatible API support (`routers/openai.py`)
- Pipelines framework for custom integrations

**Real-time Features:**
- WebSocket connections handled in `socket/main.py`
- Redis support for multi-worker deployments
- Session sharing across nodes

## Python Requirements

- Python 3.11 or 3.12 (NOT 3.13 or higher)
- Node.js >= 18.13.0, <= 22.x.x
- npm >= 6.0.0

## Environment Variables

Key environment variables are loaded from `.env` file in the project root. See `.env.example` for reference.

Important variables:
- `DATABASE_URL`: Database connection string
- `OLLAMA_BASE_URL`: Ollama server URL
- `OPENAI_API_KEY`: OpenAI API key
- `WEBUI_SECRET_KEY`: Secret key for sessions (auto-generated if not provided)
- `ENABLE_DB_MIGRATIONS`: Enable automatic database migrations (default: true)
- `DEVICE_TYPE`: cpu/cuda/mps for embedding models
- `UVICORN_WORKERS`: Number of workers for production (default: 1)

## Testing

**Backend tests:** Located in `backend/open_webui/test/`, run with pytest
**Frontend tests:** Run with `npm run test:frontend` (vitest)
**E2E tests:** Cypress tests in `cypress/`, run with `npm run cy:open`

## Common Workflows

**Adding a new API endpoint:**
1. Create or update router in `backend/open_webui/routers/`
2. Create corresponding frontend API client in `src/lib/apis/`
3. Register router in `backend/open_webui/main.py`

**Database schema changes:**
1. Create Alembic migration: `alembic revision -m "description"`
2. Edit generated file in `backend/open_webui/migrations/versions/`
3. Migrations run automatically on startup if `ENABLE_DB_MIGRATIONS=true`

**Adding translations:**
1. Add language code directory in `src/lib/i18n/locales/`
2. Copy en-US JSON files and translate
3. Add language to `src/lib/i18n/locales/languages.json`
4. Submit translations in separate PR from features

**Working with Python tools/functions:**
- Custom Python functions can be added through the UI in the tools workspace
- Built-in tools are in `backend/open_webui/tools/`
- Tools integrate with LLMs via function calling

## Notes

- The project uses both SQLAlchemy (newer) and Peewee (legacy) ORMs
- Frontend is built as static files and served by FastAPI in production
- WebSocket support requires Redis for multi-worker deployments
- The middleware.py file (185KB) handles the complex pipeline and tool processing logic
- Pyodide integration allows Python code execution in the browser for tools
