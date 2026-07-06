# functions — erp_ai_integration (detailed)

_Hand-maintained function reference. Updated: 2026-07-06 (end of Phase 6 — all planned phases done)._
_Line numbers may drift — `app_map.md` (auto-generated) always has current lines._

## ai/ — multi-provider AI layer (Claude + ChatGPT)

The `provider` field in Claude AI Settings ("Claude" | "ChatGPT") selects the
adapter. **Callers use ONLY `ai/client.py`** — never import an adapter directly.

**Canonical formats** (provider-independent, defined in client.py docstring):
- messages: `{"role": "user"|"assistant", "content": str}`,
  assistant may carry `"tool_calls": [{id, name, input}]`,
  tool results are `{"role": "tool_result", "tool_use_id", "content", "is_error"}`
- tools: Anthropic-style `{name, description, input_schema}` (OpenAI adapter converts)
- normalized response: `{text, tool_calls, stop_reason("end_turn"|"tool_use"|"max_tokens"),
  model, usage{input_tokens, output_tokens}, raw}`

### ai/client.py — facade (what the agent loop must use)

| Function | Purpose |
|---|---|
| `get_provider_name()` | "Claude" (default) or "ChatGPT" from settings |
| `get_adapter()` | anthropic_client or openai_client module |
| `get_api_key()` | Decrypted key of the **active** provider; throws if unset |
| `get_model()` | settings.get_model() (provider-aware, custom_model overrides) |
| `create_message(messages, system, tools, max_tokens, model)` | Dispatches to adapter → **normalized response dict**. Phase 4 agent loop calls this. |
| `ping()` | Test Connection: `{provider, model, input_tokens, output_tokens}` |

### ai/anthropic_client.py — Claude adapter

| Function | Purpose |
|---|---|
| `to_wire_messages(messages)` | canonical → Anthropic (tool_result → user content block; tool_calls → tool_use blocks) |
| `create_message(api_key, model, messages, system, tools, max_tokens)` | Messages API call → normalized dict; canonical tools pass through unchanged |

### ai/openai_client.py — ChatGPT adapter

| Function | Purpose |
|---|---|
| `to_wire_tools(tools)` | Anthropic-style → OpenAI `{type:"function", function:{...}}` |
| `to_wire_messages(messages, system)` | canonical → OpenAI (system prepended; tool_result → role:"tool"; tool_calls with JSON-string arguments; is_error → "ERROR:" prefix) |
| `create_message(...)` | Chat Completions call (uses `max_completion_tokens`) → normalized dict; finish_reason mapped (tool_calls→tool_use, length→max_tokens) |

## api/settings.py — whitelisted settings endpoints (System Manager only)

| Method | Args | Purpose |
|---|---|---|
| `test_connection()` | — | Calls `ping()` on the **selected provider**, stores `connection_status` ("Connected — <provider> (<model>)") + `last_test_on`, logs usage (`request_type="test"`) |
| `create_readonly_db_user(admin_user, admin_password)` | one-time admin creds | Auto-create RO user; on failure returns `{success: False, error, manual_sql, username, password}` for the manual fallback dialog |
| `set_manual_db_user(username, password)` | creds of manually-created user | Verifies SELECT-only via `verify_user` THEN stores (mode="Manual") |
| `get_manual_setup_sql()` | — | Fresh generated creds + CREATE/GRANT SQL for fully-manual setup |
| `verify_readonly_user()` | — | Re-verify stored creds (connection + SELECT-only grants) |
| `drop_readonly_db_user(admin_user, admin_password)` | one-time admin creds | Drop RO user + clear stored state (rotation) |

## db/readonly_user.py — RO user lifecycle

| Function | Purpose |
|---|---|
| `get_db_connection_params()` | `{host, port}` from `frappe.conf` (db_host/db_port) — never hardcoded |
| `generate_credentials()` | `claude_ro_<hash8>` + `secrets.token_urlsafe(24)` |
| `get_manual_setup_sql(username, password, source_host="%")` | CREATE USER / GRANT SELECT / FLUSH / SHOW GRANTS text for manual execution |
| `create_user(admin_user, admin_password, source_host="%")` | Connect as admin via pymysql, create+grant+verify; success → `store_credentials(mode="Automatic")`; any `pymysql.MySQLError` → manual-fallback dict |
| `check_grants_select_only(grants, db_name)` | Error string if any grant is not `GRANT SELECT/USAGE ON` |
| `verify_user(username, password)` | Connect as RO user, `SELECT 1` + `SHOW GRANTS FOR CURRENT_USER()`, enforce SELECT-only |
| `store_credentials(username, password, mode)` | Persist to settings: user, encrypted password, `db_user_created=1`, timestamp, mode |
| `drop_user(admin_user, admin_password)` | DROP USER IF EXISTS + clear settings fields |

## db/readonly_connection.py — guarded execution channel

| Function | Purpose |
|---|---|
| `readonly_connection()` (contextmanager) | Separate pymysql conn with RO creds; sets `max_statement_time` (MariaDB) or `max_execution_time` (MySQL/RDS) + `SET SESSION TRANSACTION READ ONLY`; always closed |
| `run_readonly_query(sql)` | Execute guard-validated SELECT → `{columns, rows, row_count, truncated}`; caps `MAX_RETURNED_ROWS=100`, `MAX_CELL_CHARS=500`. **Phase 3 `run_query` tool calls this after `guard_sql`.** |

## db/sql_guard.py — SECURITY CORE (22 tests must stay green)

| Function | Purpose |
|---|---|
| `guard_sql(sql, user, row_limit=100) -> str` | Full validation pipeline; returns safe SQL with LIMIT enforced. Raises `GuardError` (structural) or `PermissionDenied(doctype)` |
| `_enforce_limit(sql, row_limit)` | Append LIMIT or cap an existing one (handles `LIMIT n`, `LIMIT o,n`, `LIMIT n OFFSET o`) |
| `extract_tables(statement) -> set[str]` | All tables in FROM/JOIN incl. subqueries/derived tables; fail-closed |
| `_walk` / `_consume_table_token` | sqlparse token walkers; reject schema-qualified names + table functions |

Rejects: non-SELECT, multi-statement, CTE/WITH, `/*!` executable comments,
INTO OUTFILE/DUMPFILE, LOAD_FILE, SLEEP, BENCHMARK, GET_LOCK, INFORMATION_SCHEMA,
PERFORMANCE_SCHEMA, FOR UPDATE, LOCK IN SHARE MODE, `INTO @var`.

## permissions/access.py — access modes + denylists

| Symbol | Purpose |
|---|---|
| `AI_CHAT_ROLE` | `"AI Chat User"` (created by install.ensure_role) |
| `SYSTEM_DENYLIST` | DocTypes nobody may query (User, OAuth*, Email Account, Webhook, …) |
| `RAW_TABLE_DENYLIST` | Raw tables (`__Auth`, `tabSingles`, `tabDefaultValue`, …) |
| `PermissionDenied(doctype)` | Exception carrying the doctype for the "contact Administrator" message |
| `get_access_mode(user)` | `'all'` \| `'role'` \| `None`. Administrator → all. Listed row wins (disabled → None; needs AI Chat User role). Unlisted System Manager → all |
| `user_can_query_doctype(user, doctype)` | Denylist first, then mode ('role' → `frappe.has_permission(read)`) |
| `check_table_allowed(user, table_name)` | Raw-table gate used by sql_guard; non-`tab` tables denied |

## Doctype controllers

| File | Members |
|---|---|
| `claude_ai_settings.py` | `validate` (backfills provider="Claude", clamps ints, dedupes allowed_users), `get_model` (provider-aware), `get_active_api_key` (key of selected provider), module fns `get_settings()`, `check_enabled()` (**every chat endpoint must call this first**) |
| `ai_chat.py` | `before_insert` (owner+timestamp), `on_trash` (deletes messages), `get_permission_query_conditions`, `has_permission` (owner-only unless System Manager) |
| `ai_chat_message.py` | `get_permission_query_conditions` (owner-only) |
| `ai_usage_log.py` | `MODEL_PRICING` map (Claude + GPT models); `log_usage(user, model, input_tokens, output_tokens, chat=None, request_type="chat")` — inserts row + bumps lifetime counters on Singles; `get_tokens_used_this_month()` — for budget enforcement |
| `install.py` | `ensure_role()` + `ensure_provider_default()` (backfills provider on upgraded sites) — both idempotent on install+migrate (product requirement: works on every client site) |

## Client scripts

`claude_ai_settings.js` — buttons: Test Connection · Create Read-Only DB User
(admin-creds dialog) · Manual Setup / Enter Credentials · Verify Read-Only
Connection · Drop & Recreate. `show_manual_fallback()` renders error + manual
SQL + paste-back form when auto-creation fails (RDS etc.).

## ai/tools.py — discovery + query tool handlers (Phase 3)

Canonical (Anthropic-style) tool schemas in `TOOL_DEFINITIONS` — adapters in
ai/client.py convert for other providers.

| Function | Purpose |
|---|---|
| `search_doctypes(keywords, user)` | Synonym-map hits (score 80) + LIKE search on name/module/description (`tabDocType`, excludes child/single/virtual); ranks exact > startswith > contains > module/description-only; top 15; each result tagged `accessible` via `user_can_query_doctype` |
| `SYNONYM_MAP` | term → ERPNext DocType list (sales, customer, stock, payment, employee, …) — extend freely |
| `get_doctype_schema(doctype, user)` | Permission-checked (raises `PermissionDenied`); returns table name, `is_submittable`, standard columns, real fields with SQL-mapped type + label (layout fieldtypes skipped), child tables (with join hint), Link fields with target doctype |
| `FIELDTYPE_TO_SQL` / `LAYOUT_FIELDTYPES` | Frappe fieldtype → SQL type map; fieldtypes with no real column |
| `run_query(sql, user)` | `guard_sql()` (row_limit from settings) then `run_readonly_query()`; adds `executed_sql` to the result |
| `permission_denied_payload(doctype)` | JSON tool-error body carrying the standard "contact your Administrator" instruction text |
| `handle_tool_call(name, args, user)` | Dispatcher used by the agent loop → `(content_json, is_error)`. Catches `PermissionDenied`, `GuardError`, and unexpected exceptions (logged via `frappe.log_error`) — never raises into the agent loop |

## ai/prompts.py — system prompt builder (Phase 4)

| Function | Purpose |
|---|---|
| `get_site_timezone()` | `frappe.utils.get_system_timezone()` with System Settings fallback |
| `get_default_currency()` | Global default currency, for "format money sensibly" instruction |
| `build_system_prompt(user)` | Assembles the full prompt per plan §5.2: workflow (search first), permission-denial wording, Frappe SQL conventions (tab prefix, docstatus, business vs creation date, child joins, single-SELECT-no-CTE), current datetime+timezone+currency, multi-company clarification, output rules, read-only safety note |

## ai/agent.py — synchronous tool-use loop (Phase 4)

Talks ONLY to `ai/client.py` (canonical messages + normalized response) — provider-agnostic by construction.

| Function | Purpose |
|---|---|
| `check_budget(settings)` | Throws if `monthly_token_budget` is set and already reached (`get_tokens_used_this_month`) |
| `build_history(chat)` | Last `HISTORY_MESSAGES` (20) user/assistant rows from AI Chat Message, chars capped per message, trimmed so the first message is always `user` |
| `run_turn(chat, user_text, user)` | The loop: append user msg → `create_message` with `TOOL_DEFINITIONS` → if `stop_reason=="tool_use"` run each call via `handle_tool_call`, append assistant+tool_result turns, continue; else return final text. Caps at `max_tool_iterations`; logs usage per API call via `log_usage`; collects `generated_sql`/`query_result_preview` from any `run_query` calls. Returns `{answer, model, input_tokens, output_tokens, duration_ms, generated_sql, query_result_preview, error}` |
| `generate_chat_title(question, chat, user)` | One cheap call (haiku for Claude / gpt-4o-mini for ChatGPT) to name the chat from its first question; falls back to a truncated question on any failure |

## api/chat.py — whitelisted chat endpoints (Phase 4)

Gate chain on every endpoint: `check_enabled()` → `get_access_mode(user)` (role + allowed_users row) → ownership where applicable.

| Method | Purpose |
|---|---|
| `_check_access()` | The two-gate check, called first in every endpoint |
| `_get_owned_chat(chat)` | Loads the AI Chat doc; throws PermissionError unless owner or System Manager |
| `_check_rate_limit()` | `frappe.cache()` counter keyed by user+hour; throws at `RATE_LIMIT_PER_HOUR` (30) |
| `create_chat()` | New AI Chat doc for the session user |
| `get_chats(include_archived=0)` | Caller's chats, sorted by `last_message_on desc` |
| `get_messages(chat, start=0, limit=50)` | Paginated messages (ownership-checked) |
| `send_message(chat, message)` | Persists user message → `run_turn()` → persists assistant message (or a `system_note` + re-raised error on failure) → updates `last_message_on`/`model_used`, generates title on the first message. Validates length (≤5000 chars) and non-empty before the rate-limit check |
| `rename_chat` / `archive_chat` / `unarchive_chat` / `delete_chat` | Housekeeping, all ownership-checked; delete cascades to messages via `AIChat.on_trash` |

## page/ai_chat/ (Phase 5) — Desk Page `/app/ai-chat`

Restricted to roles `AI Chat User` + `System Manager` (page doc). Plain ES6
class `AIChatUI` in `ai_chat.js`, CSS injected once via `inject_css()` (no
build step). Key methods: `render_layout()` (sidebar + thread + input),
`load_chats()`/`new_chat()`/`select_chat()` (data), `render_chat_list()` +
`filter_chats()` (sidebar search) + `show_chat_menu()` (rename/archive/delete
dialog), `append_message()` (markdown for assistant, collapsible "View SQL"
`<details>`, renders feedback buttons via `render_feedback()` when a message
name is available), `render_feedback($bubble, message_name, current)` (Phase
6 — 👍/👎 buttons, click-again-to-clear, calls `set_message_feedback`),
`render_empty_state()` (4 starter questions), `show_thinking()` /
`show_error()` (retry button), `send()` (calls `api/chat.send_message`,
updates sidebar ordering + title on response, passes `message_name` through
so feedback buttons work on fresh answers too). Mobile: sidebar becomes an
off-canvas drawer toggled by `.aichat-toggle-sidebar` under 768px.

## Phase 6 — Polish

### api/chat.py addition

| Method | Purpose |
|---|---|
| `set_message_feedback(message, feedback)` | Thumbs up/down on an assistant answer (`feedback` ∈ `"Up"`/`"Down"`/`""`); validates role=="assistant" and ownership via the parent chat, `db_set`s the field. Dataset for future prompt tuning. |

### api/settings.py addition

| Method | Purpose |
|---|---|
| `get_budget_status()` | System-Manager-only; returns `{used, budget, percent, total_input_tokens, total_output_tokens}` from `get_tokens_used_this_month()` vs `monthly_token_budget`. `percent` is `None` when budget is unlimited (0), capped at 100 otherwise. Powers the settings-form dashboard indicator. |

### erp_ai_integration/doctype/ai_chat_message

Added `feedback` Select field (`""`/`Up`/`Down`, read-only — only settable via
the whitelisted endpoint) to `field_order` + `fields`; included in
`api/chat.get_messages()` output so the UI can restore button state on reload.

### erp_ai_integration/report/ai_usage_summary/ — Script Report

`ai_usage_summary.py`:

| Function | Purpose |
|---|---|
| `execute(filters)` | Standard Script Report entry point → `(columns, data, None, chart)` |
| `get_columns()` | Date, User, Model, Requests, Input/Output/Total Tokens, Estimated Cost |
| `get_data(filters)` | Grouped SQL (date+user+model) over `tabAI Usage Log`, sums tokens/cost, ordered by date desc then total_tokens desc |
| `build_conditions(filters)` | from_date/to_date (defaults: month start → today), optional user/model/request_type filters |
| `get_chart(data)` | Bar chart of total tokens per day |

`ai_usage_summary.js` — filter fields: From Date, To Date, User (Link), Model
(Data), Request Type (Select: chat/test/title). System Manager only (report
roles).

### claude_ai_settings.js addition

`add_budget_indicator(frm)` — calls `get_budget_status`, shows a dashboard
indicator: blue "no budget set" when unlimited, else green/orange/red at
70%/90% thresholds. `format_number(n)` helper for comma-formatted token counts.
