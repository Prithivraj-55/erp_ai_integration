---
name: project2-erp-ai-integration
description: >
  Load this skill whenever the user mentions: erp_ai_integration, project 2,
  assesment site, AI chat, Claude AI Settings, AI Access User, AI Chat,
  AI Chat Message, AI Usage Log, sql_guard, readonly db user, ai agent loop,
  or any doctype/module in this app.
---

# Project: erp_ai_integration (project 2)

## Environment

| Key         | Value                                                    |
|-------------|----------------------------------------------------------|
| Bench       | frappe-bench1                                            |
| Site        | **assesment** (always pass `--site assesment`)           |
| App         | erp_ai_integration                                       |
| App root    | apps/erp_ai_integration/                                 |
| Python pkg  | apps/erp_ai_integration/erp_ai_integration/              |
| Frappe      | v15                                                      |
| Module      | ERP AI Integration                                       |
| Role        | AI Chat User (created by install/migrate hook)           |
| Deps        | anthropic, openai, sqlparse (in bench env + pyproject)   |
| Providers   | Claude (default) or ChatGPT — `provider` field in settings |

The bench default site stays **manufact** (project 1). All bench commands for
this app must target assesment explicitly:
`bench --site assesment migrate` / `console` / `run-tests`.

## What this app is

A reusable, multi-site product: ERP users ask natural-language questions in a
chat UI; Claude (Messages API + tool use) discovers the relevant DocType,
inspects its schema, runs a guarded read-only SELECT through a dedicated
SELECT-only MariaDB user, and formats the answer. Full spec:
`apps/erp_ai_integration_plan doc.md` (bench root apps/ folder).

**Product constraints (apply to every change):**
- Nothing site-/server-specific hardcoded — host/port/db from `frappe.conf`.
- Managed DBs (AWS RDS etc.): auto-creation of the RO user may fail → the UI
  shows the exact SQL for manual setup + credential paste-back with
  SELECT-only verification. Never break this fallback.
- AI can never write to the DB: RO user (SELECT-only) + sql_guard + read-only
  session — all three layers stay.

## First thing every session

**Read these before doing anything else:**
1. `.claude/references/app_map.md` — current files + every function with line numbers
2. `.claude/references/next_steps.md` — what is done, what is pending, what comes next

Regenerate references after code changes: `bash .claude/update_skill.sh`.

## When the user says "continue"

All planned phases (1–6) are done. Open `.claude/references/next_steps.md` for
what's optional/later (streaming, history summarization, chart rendering in
chat) and check the "Pending user actions" below first — most "continue" work
now is user-driven (add an API key, try the app) rather than more building.

## Architecture

```
erp_ai_integration/erp_ai_integration/
├── hooks.py                  # after_install/after_migrate (role), perm hooks
├── install.py                # ensure_role("AI Chat User"), ensure_provider_default()
├── erp_ai_integration/doctype/
│   ├── claude_ai_settings/   # Single: provider + per-provider creds/model, limits,
│   │                         #   allowed_users, RO-db-user state, status, budget (+ form JS)
│   ├── ai_access_user/       # child: user + access_mode + enabled
│   ├── ai_chat/              # session; if_owner perms + permission query
│   ├── ai_chat_message/      # separate doctype (not child) — indexed on chat
│   └── ai_usage_log/         # one row per API request; log_usage(); month sum
├── erp_ai_integration/page/
│   └── ai_chat/               # Desk Page /app/ai-chat — sidebar+thread+input, plain ES6,
│                             #   thumbs up/down on assistant answers
├── erp_ai_integration/report/
│   └── ai_usage_summary/      # Script Report: tokens/cost by day/user/model, bar chart
├── api/
│   ├── settings.py           # test_connection, create_readonly_db_user,
│   │                         #   set_manual_db_user, get_manual_setup_sql,
│   │                         #   verify_readonly_user, drop_readonly_db_user,
│   │                         #   get_budget_status
│   └── chat.py                # create_chat, get_chats, get_messages, send_message,
│                             #   rename/archive/unarchive/delete_chat, set_message_feedback,
│                             #   rate limit
├── ai/
│   ├── client.py              # PROVIDER-AGNOSTIC facade — the only AI entry point
│   │                         #   (canonical msg/tool formats + normalized response)
│   ├── anthropic_client.py    # Claude adapter (all anthropic SDK code)
│   ├── openai_client.py       # ChatGPT adapter (all openai SDK code)
│   ├── tools.py                # search_doctypes, get_doctype_schema, run_query,
│   │                         #   handle_tool_call dispatcher, SYNONYM_MAP
│   ├── prompts.py             # build_system_prompt() (workflow, SQL conventions, safety)
│   └── agent.py                # run_turn() sync tool-use loop, generate_chat_title()
├── db/
│   ├── readonly_user.py      # create/verify/drop RO user; manual SQL generator
│   ├── readonly_connection.py# separate pymysql conn; READ ONLY session; timeouts
│   └── sql_guard.py          # SECURITY CORE — single SELECT, denylists,
│                             #   table extraction, permission check, LIMIT cap
├── permissions/
│   └── access.py             # access modes, SYSTEM_DENYLIST, RAW_TABLE_DENYLIST,
│                             #   PermissionDenied(doctype)
└── tests/
    ├── test_sql_guard.py     # 22 tests — run after ANY guard/permissions change
    ├── test_providers.py     # 8 tests — provider selection + wire-format conversion
    ├── test_tools.py          # 12 tests — search/schema/run_query/dispatcher
    ├── test_chat_api.py       # 12 tests — gates, ownership, rate limit, lifecycle, feedback
    └── test_phase6.py         # 7 tests — usage report query, budget status endpoint
```

## Build status — all planned phases complete

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Skeleton, settings, usage log, Test Connection | ✅ done |
| 2 | RO DB user (+ manual fallback), RO connection, sql_guard + tests | ✅ done — RO user **created and verified SELECT-only** on assesment |
| 2.5 | Multi-provider: Claude/ChatGPT switch in settings, adapters + facade, tests | ✅ done |
| 3 | ai/tools.py: search_doctypes (synonyms), get_doctype_schema, run_query, dispatcher | ✅ done |
| 4 | ai/prompts.py, ai/agent.py, api/chat.py (sync agent loop + endpoints) | ✅ done |
| 5 | Chat UI desk page /app/ai-chat | ✅ done |
| 6 | Polish: AI Usage Summary report, budget indicator on settings, thumbs up/down feedback | ✅ done |

**61/61 tests passing** across all five suites. App builds cleanly
(`bench build --app erp_ai_integration`). Chat title generation was implemented
as part of Phase 4/agent.py, ahead of schedule. Async/streaming and
history-summarization were intentionally left out — plan doc §6 says sync is
correct at ~15 questions/day; revisit only if usage grows materially.

## Conventions

- **AI calls go through `ai/client.py` ONLY** (never import an adapter or SDK
  directly elsewhere). Canonical message/tool formats + normalized response are
  documented in its docstring — the Phase 4 agent loop must be written against
  them so both providers work.
- Models: Claude default `claude-sonnet-4-6` (also haiku/opus); ChatGPT default
  `gpt-4o` (also 4o-mini, 4.1, 4.1-mini, 5, 5-mini); `custom_model` Data field
  overrides the active provider's selection. Pricing map in `ai_usage_log.py`.
- Every chat endpoint must check: settings.enabled → AI Chat User role →
  allowed_users row enabled → ownership.
- Tool errors back to Claude as `tool_result` with `is_error: true`;
  PermissionDenied produces the standard "contact your Administrator" message
  naming the DocType.
- Tabs for indentation in Python (ruff config in pyproject).
- After changing sql_guard or access.py, ALWAYS run:
  `bench --site assesment run-tests --module erp_ai_integration.tests.test_sql_guard`
- After changing ai/tools.py or api/chat.py, run test_tools + test_chat_api too.
- Feedback (`AI Chat Message.feedback`) is read-only in the doctype — only
  `api/chat.set_message_feedback` may write it (ownership + role checked there).
- Full suite: `for m in test_sql_guard test_providers test_tools test_chat_api test_phase6; do
  bench --site assesment run-tests --module erp_ai_integration.tests.$m; done`

## Pending user actions

- [ ] Paste a provider API key into Claude AI Settings (assesment) → **Test
      Connection**. RO DB user is already created and verified; API key is the
      only remaining blocker to a live end-to-end chat test.
- [ ] Once a key is set, open `/app/ai-chat` as an `AI Chat User` and try a
      real question; check **AI Usage Summary** report afterwards to confirm
      the usage numbers land correctly.

## Reference files

| File                              | Read when …                                  |
|------------------------------------|----------------------------------------------|
| `.claude/references/app_map.md`   | Any task — always first                      |
| `.claude/references/next_steps.md`| Session start / user says "continue"         |
| `.claude/references/functions.md` | Need signatures + purpose of existing functions |
| `.claude/references/doctypes.md`  | Doctype/controller/child-table changes       |
| `.claude/references/hooks.md`     | hooks.py changes                             |
| `.claude/references/api.md`       | Adding/calling whitelisted methods           |
