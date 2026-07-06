# next_steps — erp_ai_integration

_Status as of: 2026-07-06 — **all planned phases (1–6) complete.**_
_When the user says **"continue"**, there is no forced next phase — check
"Optional / later" below and the "Pending user actions" first, since most
remaining work is user-driven (add API key, try the app) rather than more code._

## Done

- ✅ Phase 1: app skeleton; DocTypes (Claude AI Settings, AI Access User, AI Chat,
  AI Chat Message, AI Usage Log); `ai/client.py`; Test Connection button;
  installed on **assesment**; role `AI Chat User` auto-created.
- ✅ Phase 2: RO DB user flow (auto + manual fallback for RDS/managed DBs);
  `readonly_connection.py`; `sql_guard.py` + `permissions/access.py`.
  RO user **created and verified SELECT-only** on assesment (`claude_ro_7eeeee88`).
- ✅ Phase 2.5 Multi-provider: `provider` select (Claude | ChatGPT) with
  per-provider credential + model fields; `ai/client.py` is a provider-agnostic
  facade over `ai/anthropic_client.py` + `ai/openai_client.py` (canonical
  message/tool formats, normalized response). Test Connection tests the
  selected provider.
- ✅ Phase 3: `ai/tools.py` — `search_doctypes` (SYNONYM_MAP + LIKE search,
  ranked, accessible flags), `get_doctype_schema` (permission-checked, fields+
  labels+child tables+links), `run_query` (guard_sql → run_readonly_query),
  `handle_tool_call` dispatcher.
- ✅ Phase 4: `ai/prompts.py` (system prompt), `ai/agent.py` (`run_turn()` sync
  tool-use loop — provider-agnostic; `generate_chat_title()`), `api/chat.py`
  (create/get_chats/get_messages/send_message/rename/archive/unarchive/delete,
  full gate chain, 30/hour rate limit).
- ✅ Phase 5: Desk Page `/app/ai-chat` (`page/ai_chat/`) — sidebar, thread with
  markdown + collapsible "View SQL", input bar, empty state with 4 starters,
  error state with Retry, mobile drawer. Plain ES6, no build step.
- ✅ Phase 6 (this session): 
  - **AI Usage Summary** Script Report (`report/ai_usage_summary/`) — tokens/
    cost grouped by date+user+model, filterable by date range/user/model/
    request_type, bar chart of daily token usage.
  - **Budget indicator** on Claude AI Settings form — dashboard indicator
    showing % of `monthly_token_budget` used this month (green/orange/red at
    70%/90%), or total tokens used when unlimited. Backed by
    `api/settings.get_budget_status()`.
  - **Thumbs up/down feedback** — `AI Chat Message.feedback` field (Up/Down,
    read-only, settable only via `api/chat.set_message_feedback`), 👍/👎
    buttons under every assistant bubble in the chat UI (click again to
    clear), ownership + role enforced server-side.

**61/61 tests passing**: test_sql_guard (22), test_providers (8), test_tools
(12), test_chat_api (12), test_phase6 (7). App builds cleanly.

## Pending user actions (cannot be done by Claude)

- [ ] Pick the provider in Claude AI Settings (assesment) and paste that
      provider's API key (Anthropic or OpenAI) → run **Test Connection**.
      This is the ONLY blocker to a live end-to-end chat test.
- [ ] Once a key is set, open `/app/ai-chat` as a user with the `AI Chat User`
      role and try a real question (e.g. one of the 4 starter questions).
- [ ] Check the **AI Usage Summary** report (any Frappe report search) after a
      few real questions to confirm token/cost tracking looks right.

## Optional / later (not currently planned, no urgency)

Only pick these up if the user explicitly asks — the app is fully functional
without them:

- **Async + realtime streaming.** Plan doc §6/§11 explicitly says synchronous
  is correct at ~15 questions/day. Only revisit if usage grows materially.
- **Older-history summarization.** `agent.py.build_history()` currently does
  simple truncation to the last 20 messages — fine for the expected volume.
- **Chart rendering from query results** in the chat UI (currently markdown
  tables only).
- **Row-level permission gap** (flagged in plan doc §10.6 / §9): "Based on
  Role Permission" mode checks DocType-level read access only, not User
  Permissions (e.g. company restriction). If a client needs that, it's a
  deliberate scope decision, not a bug — would need mandatory WHERE-filter
  injection in `sql_guard.py` from `frappe.get_user_permissions`.

## Standing rules (do not regress)

- Multi-site product: nothing hardcoded; conf-driven; manual DB-user fallback intact.
- Three write-protection layers stay: SELECT-only user, sql_guard, READ ONLY session.
- AI calls only via `ai/client.py` facade — both providers (Claude/ChatGPT) must
  keep working; after touching ai/ → run test_providers + test_tools + test_chat_api.
- After touching sql_guard/access.py → run the 22-test sql_guard suite.
- `AI Chat Message.feedback` is read-only in the doctype JSON — only
  `api/chat.set_message_feedback` may write it. Don't add a direct-write path.
- Full-suite command: `for m in test_sql_guard test_providers test_tools test_chat_api test_phase6; do
  bench --site assesment run-tests --module erp_ai_integration.tests.$m; done`
- After any code change: `bash apps/erp_ai_integration/.claude/update_skill.sh`,
  update Build status in SKILL.md + this file if scope changed.
