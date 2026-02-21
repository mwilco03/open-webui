# DALEC — Design Document

**Developer AI Learning Environment for Code**
Open WebUI + Ollama + Jupyter + OpenSearch

---

## Open WebUI Plugin Taxonomy

Open WebUI provides four extension points. Each has different mechanics, costs, and appropriate use cases.

### Tool

| Property | Value |
|---|---|
| **What it is** | A Python class with methods that the LLM can call via OpenAI function calling |
| **Injected into prompt?** | Yes — every method's schema goes into the `tools[]` array on every turn |
| **Token cost** | Always-on. ~70-100 tokens per method per turn |
| **LLM decides to call it?** | Yes — the LLM sees the specs and chooses when to invoke |
| **Toggleable?** | Yes — tools are enabled per-model or per-chat in the UI |
| **Has Global Valves?** | Yes — admin-configured in the tool settings panel |
| **Has UserValves?** | Yes — each user configures their own values via the tool settings |
| **Non-repudiation?** | Yes, via UserValves — user's personal credentials flow through to the target system |
| **Runs on every request?** | Schema is sent every turn; execution only when LLM calls it |

**When to use:** Any capability the LLM should be able to invoke on demand. API integrations, search, write operations. The LLM is the decision-maker.

### Function (Filter / Pipe / Action)

| Property | Value |
|---|---|
| **What it is** | Backend middleware. Three subtypes: Filter (inlet/outlet/stream hooks), Pipe (replaces the LLM call), Action (on-demand via UI button) |
| **Injected into prompt?** | No — completely invisible to the LLM. Zero schema tokens |
| **Token cost** | Zero |
| **LLM decides to call it?** | No — Filters run automatically on every request. Pipes replace the LLM. Actions are user-triggered |
| **Toggleable?** | Filters: attached per-model or set global. Can be toggled on/off. Pipes: selected as the model. Actions: appear as UI buttons |
| **Has Global Valves?** | Yes |
| **Has UserValves?** | Yes |
| **Non-repudiation?** | Possible via UserValves but functions are infrastructure, not user-facing |
| **Runs on every request?** | Filters: YES, every request to models they're attached to. Pipes: when selected. Actions: on-click only |

**When to use:** Infrastructure that should be transparent. Caching, logging, request/response transformation, rate limiting. Not for capabilities the LLM should decide about — the LLM never knows functions exist.

### Knowledge

| Property | Value |
|---|---|
| **What it is** | RAG document collections. Files are chunked, embedded, and stored in a vector database |
| **Injected into prompt?** | Depends on mode. Without native function calling: auto-retrieved and injected every turn. With native function calling: LLM calls `query_knowledge_files()` on demand |
| **Token cost** | Without native FC: variable, always-on (retrieved chunks injected). With native FC: on-demand (only the builtin tool spec is always-on) |
| **LLM decides to call it?** | With native FC: yes. Without: no, it's automatic |
| **Toggleable?** | Attached per-model in model settings |
| **Has Global Valves?** | No |
| **Has UserValves?** | No |
| **Non-repudiation?** | No — knowledge is read-only reference material |
| **Runs on every request?** | Without native FC: yes. With native FC: only when LLM queries it |

**When to use:** Reference material the LLM should be able to consult. Documentation, standards, runbooks. Not for live/mutable data.

### Skill

| Property | Value |
|---|---|
| **What it is** | Markdown instruction templates. Behavioral guidance the LLM can load on demand |
| **Injected into prompt?** | Partially. A manifest (name + one-line description per skill) is injected into the system message every turn. Full content is lazy-loaded when the LLM calls `view_skill()` |
| **Token cost** | Hybrid. ~50 tokens/skill for the always-on manifest. Full content on-demand only when loaded |
| **LLM decides to call it?** | Yes — LLM sees the manifest and calls `view_skill(name)` when it decides it needs the instructions |
| **Toggleable?** | Attached per-model or per-chat |
| **Has Global Valves?** | No |
| **Has UserValves?** | No |
| **Non-repudiation?** | N/A — skills are text, not actions |
| **Runs on every request?** | Manifest: yes. Full content: no, on-demand |

**When to use:** Workflow guidance, conventions, behavioral instructions. Cheaper than encoding guidance in tool docstrings. The LLM loads what it needs, when it needs it.

---

## DALEC Architecture

### Tools (3)

Tools are the LLM's hands. It sees what's available, decides when to act.

#### Tool 1: GitLab Read-Only

**Credential model:** Shared server PAT (`read_api` scope), admin-configured via **Global Valves**.

Works immediately. No user configuration. Every user gets the same read access through a service account.

| Workflow | Functions |
|---|---|
| **Find code** | `search_projects`, `search_code`, `get_file`, `get_tree` |
| **Review changes** | `get_merge_request`, `get_mr_changes`, `list_mr_notes`, `compare_branches` |
| **Understand history** | `list_commits`, `get_commit`, `get_commit_diff` |
| **Check CI** | `get_pipeline`, `list_pipeline_jobs`, `get_job_log` |
| **Browse issues** | `list_issues`, `get_issue` |

~15 functions organized by what the developer is trying to do, not by GitLab API shape.

**Valves (Global — admin sets once):**
```
gitlab_url:        GitLab instance URL
gitlab_read_token: Shared PAT with read_api scope
verify_ssl:        SSL verification toggle
```

#### Tool 2: GitLab Write

**Credential model:** Per-user PAT (`api` scope), each user configures via **UserValves**.

Non-repudiation: commits, MRs, and comments are attributed to the human, not a service account. Git blame works. Audit trails intact.

| Workflow | Functions |
|---|---|
| **Ship code** | `create_branch`, `commit_files`, `create_merge_request` |
| **Refine work** | `update_merge_request` (title, desc, labels, assignees — NOT state) |
| **Discuss** | `create_mr_note`, `create_issue_note` |

6 functions. The developer inner loop: branch, commit, MR, review.

**Valves (Global — admin sets once):**
```
gitlab_url:  GitLab instance URL  (shared with read tool or duplicated)
```

**UserValves (each user sets their own):**
```
gitlab_write_token: Personal PAT with api scope
```

When `gitlab_write_token` is empty, write functions return a clear error with instructions to configure it. The admin could provide a link that opens a pop-out window to the GitLab PAT creation page (`{gitlab_url}/-/user_settings/personal_access_tokens`) with the `api` scope pre-selected. This is a Valve value pointing to the URL — the frontend renders it as a link.

**Deliberately excluded:**

| Excluded | Why |
|---|---|
| `merge_merge_request` | Merging is a human approval decision |
| `close_issue`, `close_mr` | State transitions are human decisions |
| `delete_branch` | Destructive. GitLab auto-deletes on merge |
| `create_issue` | The AI responds to issues, not files them |
| `retry_job`, `cancel_job`, `create_pipeline` | CI control is high-risk |
| All admin/member/wiki/snippet ops | Out of scope |

`update_merge_request` accepts title, description, labels, assignee_ids. It omits `state_event`. The implementation only forwards the allowed fields — extra parameters are silently dropped.

#### Tool 3: Mattermost

**Credential model:** Shared bot token, admin-configured via **Global Valves**.

Messages come from the bot account. Users expect "DALEC Bot," not messages impersonating them.

| Workflow | Functions |
|---|---|
| **Find conversations** | `get_channels`, `search_posts` |
| **Read context** | `get_channel_posts`, `get_thread` |
| **Respond** | `send_message` |

5 functions. Read context, send messages. No channel management, no user management, no post deletion.

**Valves (Global — admin sets once):**
```
mattermost_url:       Mattermost server URL
mattermost_bot_token: Bot account token
```

### Function: Semantic Cache (Filter)

A Filter that intercepts every request transparently.

```
inlet():  Embed query → search cache → if hit above threshold, return cached response
outlet(): Embed query+response → store in cache
```

**Why a Filter?** Caching is infrastructure. The LLM should not know the cache exists. Filters run on every request with zero schema tokens. This is exactly what Filters are for.

**Valves (Global):**
```
enabled:              Toggle cache on/off
similarity_threshold: Cosine similarity threshold (default: 0.95)
ttl_seconds:          Cache entry expiration (default: 900)
bypass_on_tool_use:   Skip caching when response involved tool calls (default: true)
```

**Design constraints for a coding assistant:**
- `bypass_on_tool_use: true` — responses that called GitLab/Mattermost tools reference mutable state and must not be cached
- High threshold (0.95+) to avoid near-miss collisions ("revert a commit" vs. "revert a merge commit")
- TTL to bound staleness
- Cache keyed per-user to prevent cross-user leakage

### Skill: Developer Workflow

Markdown content the LLM loads via `view_skill()` when it needs guidance.

**Always-on cost:** ~50 tokens (one manifest entry with name + description).
**Full content:** loaded on-demand only when relevant.

**Content covers:**
- The intended workflow: branch → commit → MR → review comment
- Commit message conventions (conventional commits, or project-specific)
- Files the assistant should not modify (`.gitlab-ci.yml`, `CODEOWNERS`, deployment manifests)
- When to confirm with the user before acting (destructive or high-visibility actions)
- Mattermost norms (which channels, tone, when to post)

This is cheaper than encoding all of this in tool docstrings (~50 tokens always-on vs. repeating guidance across 26 function descriptions) and more maintainable — update one Skill, not 26 docstrings.

### System Prompt

Short, positive-framing, on the model configuration:

> You are DALEC, a coding assistant connected to GitLab and Mattermost. Help developers browse code, review merge requests, commit changes, and discuss work. When performing write operations, confirm the target branch and file paths with the user first. Use the Developer Workflow skill for conventions and guidelines.

~60 tokens. Establishes identity and default behavior.

### Builtin Tool Configuration

Disable unused builtin tool categories on the DALEC model to keep the token budget honest:

```json
{
  "time": true,
  "knowledge": false,
  "chats": false,
  "memory": false,
  "web_search": false,
  "code_interpreter": true,
  "image_generation": false,
  "notes": false,
  "channels": false
}
```

`code_interpreter: true` because DALEC can use Jupyter (see below).

### Token Budget

| Component | Tokens/turn | Type |
|---|---|---|
| GitLab Read (~15 functions) | ~1,100 | Always-on (schema) |
| GitLab Write (6 functions) | ~450 | Always-on (schema) |
| Mattermost (5 functions) | ~375 | Always-on (schema) |
| Builtin: time (2 functions) | ~100 | Always-on (schema) |
| Builtin: code_interpreter (1 function) | ~75 | Always-on (schema) |
| Skill manifest (1 entry) | ~50 | Always-on (manifest) |
| System prompt | ~60 | Always-on |
| Skill full content | ~300-500 | On-demand |
| Semantic cache filter | 0 | Invisible |
| **Total always-on** | **~2,210** | |

---

## Deployment: DALEC + Jupyter + OpenSearch

### Docker Compose Stack

```yaml
services:
  # --- Core ---
  ollama:
    image: ollama/ollama:latest
    container_name: dalec-ollama
    volumes:
      - ollama-data:/root/.ollama
    ports:
      - "11434:11434"
    # Add deploy.resources.reservations.devices for GPU

  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: dalec-webui
    depends_on:
      - ollama
      - jupyter
      - opensearch
    ports:
      - "3000:8080"
    environment:
      # Ollama
      - OLLAMA_BASE_URL=http://ollama:11434

      # Jupyter code execution
      - CODE_INTERPRETER_ENGINE=jupyter
      - CODE_INTERPRETER_JUPYTER_URL=http://jupyter:8888
      - CODE_INTERPRETER_JUPYTER_AUTH=token
      - CODE_INTERPRETER_JUPYTER_AUTH_TOKEN=${JUPYTER_TOKEN}
      - CODE_INTERPRETER_JUPYTER_TIMEOUT=120

      # OpenSearch as vector DB for Knowledge/RAG
      - VECTOR_DB=opensearch
      - OPENSEARCH_URI=https://opensearch:9200
      - OPENSEARCH_SSL=true
      - OPENSEARCH_CERT_VERIFY=false
      - OPENSEARCH_USERNAME=${OPENSEARCH_USER}
      - OPENSEARCH_PASSWORD=${OPENSEARCH_PASSWORD}

      # SSO (secrets via env, behavior via admin UI)
      - OAUTH_CLIENT_ID=${OAUTH_CLIENT_ID}
      - OAUTH_CLIENT_SECRET=${OAUTH_CLIENT_SECRET}
      - OPENID_PROVIDER_URL=${OPENID_PROVIDER_URL}
      - OAUTH_PROVIDER_NAME=SSO
      - OAUTH_SCOPES=openid email profile
      - ENABLE_OAUTH_SIGNUP=true
      - ENABLE_OAUTH_GROUP_MANAGEMENT=true
    volumes:
      - webui-data:/app/backend/data

  # --- Code Execution ---
  jupyter:
    image: jupyter/scipy-notebook:latest
    container_name: dalec-jupyter
    environment:
      - JUPYTER_TOKEN=${JUPYTER_TOKEN}
    ports:
      - "8888:8888"
    volumes:
      - jupyter-data:/home/jovial/work

  # --- Logging & Search ---
  opensearch:
    image: opensearchproject/opensearch:latest
    container_name: dalec-opensearch
    environment:
      - discovery.type=single-node
      - OPENSEARCH_INITIAL_ADMIN_PASSWORD=${OPENSEARCH_PASSWORD}
      - "OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m"
    volumes:
      - opensearch-data:/usr/share/opensearch/data
    ports:
      - "9200:9200"

  opensearch-dashboards:
    image: opensearchproject/opensearch-dashboards:latest
    container_name: dalec-dashboards
    environment:
      - OPENSEARCH_HOSTS=["https://opensearch:9200"]
    ports:
      - "5601:5601"
    depends_on:
      - opensearch

volumes:
  ollama-data:
  webui-data:
  jupyter-data:
  opensearch-data:
```

### Jupyter — How It Works With DALEC

Open WebUI's code interpreter has a Jupyter backend (`utils/code_interpreter.py`). When the LLM calls the `execute_code` builtin tool:

1. Open WebUI creates a **fresh Jupyter kernel** via `POST /api/kernels`
2. Sends the code over **WebSocket** to `api/kernels/{id}/channels`
3. Collects stdout, stderr, images (base64 PNG) from the kernel
4. **Deletes the kernel** after execution

Each execution is stateless — no persistent notebooks, no shared state between calls. This is safe for multi-user but means the LLM can't build up state across multiple code blocks in a single conversation. If persistent sessions are needed, that's a future enhancement.

**What the LLM can do with Jupyter:**
- Run Python to analyze data, do math, generate charts
- Process GitLab API responses (e.g., parse JSON, compute stats)
- Generate code snippets and verify they work before committing

### OpenSearch — Two Roles

OpenSearch serves two purposes in DALEC:

#### Role 1: Vector Database for Knowledge/RAG

Set `VECTOR_DB=opensearch`. Open WebUI uses OpenSearch as the vector store for its Knowledge system. When you upload documents to a Knowledge base, they're chunked, embedded, and stored in OpenSearch with KNN vector indices.

The LLM queries knowledge via the `query_knowledge_files()` builtin tool (with native function calling enabled).

**Use cases:**
- Coding standards and style guides
- Onboarding documentation
- Architecture decision records
- Runbooks

#### Role 2: Log Aggregation (via custom Tool)

For operational logs (application logs, audit trails, CI/CD logs), OpenSearch collects and indexes them. To let the LLM query this data, build a **Tool** (not Knowledge — logs are structured/mutable, not static documents):

```python
class Tools:
    class Valves(BaseModel):
        opensearch_url: str = Field(default="https://opensearch:9200")
        opensearch_user: str = Field(default="")
        opensearch_password: str = Field(default="")
        default_index: str = Field(default="logs-*")
        max_results: int = Field(default=50)

    async def search_logs(
        self,
        query: str,
        index: str = None,
        time_range: str = "24h",
        __user__: dict = {},
    ) -> str:
        """
        Search operational logs in OpenSearch.

        :param query: Search query (Lucene syntax or natural language)
        :param index: Index pattern to search (default: logs-*)
        :param time_range: Time range to search (e.g., "1h", "24h", "7d")
        :return: Matching log entries with timestamps and source
        """
        # Implementation: build OpenSearch query, execute, format results
        ...

    async def get_log_context(
        self,
        doc_id: str,
        index: str,
        context_lines: int = 20,
        __user__: dict = {},
    ) -> str:
        """
        Get surrounding log entries for context around a specific log line.

        :param doc_id: Document ID of the log entry
        :param index: Index containing the document
        :param context_lines: Number of surrounding entries to return
        :return: Log entries before and after the target entry
        """
        ...
```

This gives the LLM the ability to search logs when a developer asks "why did the pipeline fail?" or "show me errors from the last hour." The LLM decides when to query — it's not automatic.

---

## Credential Flow Summary

| Component | Admin Configures (Global Valves / Env) | User Configures (UserValves) | Works Immediately? |
|---|---|---|---|
| GitLab Read Tool | `gitlab_url` + shared `read_api` PAT | Nothing | Yes |
| GitLab Write Tool | `gitlab_url` | Personal PAT (`api` scope) | No — user must add PAT |
| Mattermost Tool | `mattermost_url` + bot token | Nothing | Yes |
| OpenSearch Logs Tool | `opensearch_url` + credentials | Nothing | Yes |
| Semantic Cache Filter | Threshold, TTL, toggle | Nothing | Yes |
| Jupyter | URL + token (env vars) | Nothing | Yes |
| OpenSearch Vector DB | URI + credentials (env vars) | Nothing | Yes |
| SSO/OAuth | Provider secrets (env vars) | Nothing | Yes |

**21+ read/infrastructure functions work out of the box.** The 6 GitLab write functions require a one-time PAT setup per user — this is the non-repudiation boundary.

---

## Future Considerations

### Automation Opportunities
- **Filter: Auto-link** — detect GitLab MR/issue URLs in messages and auto-fetch context (inlet filter)
- **Filter: Audit log** — log all tool invocations to OpenSearch for compliance (outlet filter)
- **Action: Quick commit** — UI button that triggers a pre-configured branch+commit+MR flow

### PAT Creation Pop-Out
The GitLab Write tool's UserValves configuration page can include a description field with a direct link to `{gitlab_url}/-/user_settings/personal_access_tokens?scopes=api`. Open WebUI renders Valve descriptions as HTML — this becomes a clickable link that opens the GitLab PAT page in a new tab. No custom frontend work needed.

### Persistent Jupyter Sessions
Current implementation creates/destroys kernels per execution. For data exploration workflows where the LLM builds up state (load data → analyze → visualize), persistent kernel sessions per chat would be valuable. This requires extending `JupyterCodeExecuter` to reuse kernel IDs stored in chat metadata.
