# app_map — erp_ai_integration

_Generated: 2026-07-06 21:39:00_

## Modules

- ai
- api
- config
- db
- erp_ai_integration
- patches
- permissions
- public
- templates
- tests
- www

## Python files

_Total: 46_

- ai/agent.py
- ai/anthropic_client.py
- ai/client.py
- ai/__init__.py
- ai/openai_client.py
- ai/prompts.py
- ai/tools.py
- api/chat.py
- api/__init__.py
- api/settings.py
- config/__init__.py
- db/__init__.py
- db/readonly_connection.py
- db/readonly_user.py
- db/sql_guard.py
- erp_ai_integration/doctype/ai_access_user/ai_access_user.py
- erp_ai_integration/doctype/ai_access_user/__init__.py
- erp_ai_integration/doctype/ai_chat/ai_chat.py
- erp_ai_integration/doctype/ai_chat/__init__.py
- erp_ai_integration/doctype/ai_chat_message/ai_chat_message.py
- erp_ai_integration/doctype/ai_chat_message/__init__.py
- erp_ai_integration/doctype/ai_usage_log/ai_usage_log.py
- erp_ai_integration/doctype/ai_usage_log/__init__.py
- erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.py
- erp_ai_integration/doctype/claude_ai_settings/__init__.py
- erp_ai_integration/doctype/__init__.py
- erp_ai_integration/__init__.py
- erp_ai_integration/page/ai_chat/__init__.py
- erp_ai_integration/page/__init__.py
- erp_ai_integration/report/ai_usage_summary/ai_usage_summary.py
- erp_ai_integration/report/ai_usage_summary/__init__.py
- erp_ai_integration/report/__init__.py
- hooks.py
- __init__.py
- install.py
- patches/__init__.py
- permissions/access.py
- permissions/__init__.py
- templates/__init__.py
- templates/pages/__init__.py
- tests/__init__.py
- tests/test_chat_api.py
- tests/test_phase6.py
- tests/test_providers.py
- tests/test_sql_guard.py
- tests/test_tools.py

## JavaScript files

_Total: 3_

- erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.js
- erp_ai_integration/page/ai_chat/ai_chat.js
- erp_ai_integration/report/ai_usage_summary/ai_usage_summary.js

## JSON files

_Total: 7_

- erp_ai_integration/doctype/ai_access_user/ai_access_user.json
- erp_ai_integration/doctype/ai_chat/ai_chat.json
- erp_ai_integration/doctype/ai_chat_message/ai_chat_message.json
- erp_ai_integration/doctype/ai_usage_log/ai_usage_log.json
- erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.json
- erp_ai_integration/page/ai_chat/ai_chat.json
- erp_ai_integration/report/ai_usage_summary/ai_usage_summary.json

## Doctypes

### ai_access_user
- Path: `erp_ai_integration/doctype/ai_access_user`
- Controller: `erp_ai_integration/doctype/ai_access_user/ai_access_user.py`
- Client script: none

### ai_chat
- Path: `erp_ai_integration/doctype/ai_chat`
- Controller: `erp_ai_integration/doctype/ai_chat/ai_chat.py`
- Client script: none
- Methods:
  - before_insert:
  - on_trash:
  - get_permission_query_conditions:
  - has_permission:

### ai_chat_message
- Path: `erp_ai_integration/doctype/ai_chat_message`
- Controller: `erp_ai_integration/doctype/ai_chat_message/ai_chat_message.py`
- Client script: none
- Methods:
  - get_permission_query_conditions:

### ai_usage_log
- Path: `erp_ai_integration/doctype/ai_usage_log`
- Controller: `erp_ai_integration/doctype/ai_usage_log/ai_usage_log.py`
- Client script: none
- Methods:
  - log_usage:
  - get_tokens_used_this_month:

### claude_ai_settings
- Path: `erp_ai_integration/doctype/claude_ai_settings`
- Controller: `erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.py`
- Client script: `erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.js`
- Methods:
  - validate:
  - validate_allowed_users:
  - get_model:
  - get_active_api_key:
  - get_settings:
  - check_enabled:

## Module-level controllers

### ai/agent.py
Functions:
  - 25:check_budget:
  - 33:build_history:
  - 54:run_turn:
  - 137:generate_chat_title:

### ai/anthropic_client.py
Functions:
  - 10:get_client:
  - 14:to_wire_messages:
  - 46:create_message:

### ai/client.py
Functions:
  - 37:get_settings:
  - 41:get_provider_name:
  - 45:get_adapter:
  - 53:get_api_key:
  - 65:get_model:
  - 69:create_message:
  - 83:ping:

### ai/openai_client.py
Functions:
  - 12:get_client:
  - 16:to_wire_tools:
  - 31:to_wire_messages:
  - 68:create_message:

### ai/prompts.py
Functions:
  - 6:get_site_timezone:
  - 13:get_default_currency:
  - 21:build_system_prompt:

### ai/tools.py
Functions:
  - 134:search_doctypes:
  - 195:get_doctype_schema:
  - 240:run_query:
  - 248:permission_denied_payload:
  - 260:handle_tool_call:

### api/chat.py
Functions:
  - 21:_check_access:
  - 30:_get_owned_chat:
  - 37:_check_rate_limit:
  - 52:create_chat:
  - 64:get_chats:
  - 79:get_messages:
  - 97:send_message:
  - 163:rename_chat:
  - 174:archive_chat:
  - 182:unarchive_chat:
  - 190:delete_chat:
  - 199:set_message_feedback:

### api/settings.py
Functions:
  - 13:_only_system_manager:
  - 19:test_connection:
  - 47:create_readonly_db_user:
  - 58:set_manual_db_user:
  - 71:get_manual_setup_sql:
  - 84:verify_readonly_user:
  - 96:drop_readonly_db_user:
  - 103:get_budget_status:

### db/readonly_connection.py
Functions:
  - 18:readonly_connection:
  - 59:run_readonly_query:

### db/readonly_user.py
Functions:
  - 26:get_db_connection_params:
  - 33:generate_credentials:
  - 39:get_manual_setup_sql:
  - 52:create_user:
  - 112:check_grants_select_only:
  - 122:verify_user:
  - 153:store_credentials:
  - 164:drop_user:

### db/sql_guard.py
Functions:
  - 55:guard_sql:
  - 100:_enforce_limit:
  - 114:extract_tables:
  - 123:_walk:
  - 151:_consume_table_token:

### hooks.py

### install.py
Functions:
  - 6:after_install:
  - 10:after_migrate:
  - 15:ensure_provider_default:
  - 25:ensure_role:

### permissions/access.py
Functions:
  - 61:get_access_mode:
  - 84:user_can_query_doctype:
  - 95:table_to_doctype:
  - 102:check_table_allowed:

### tests/test_chat_api.py

### tests/test_phase6.py

### tests/test_providers.py

### tests/test_sql_guard.py

### tests/test_tools.py

## Whitelisted API methods

- `api/settings.py:19` — `test_connection`
- `api/settings.py:47` — `create_readonly_db_user`
- `api/settings.py:58` — `set_manual_db_user`
- `api/settings.py:71` — `get_manual_setup_sql`
- `api/settings.py:84` — `verify_readonly_user`
- `api/settings.py:96` — `drop_readonly_db_user`
- `api/settings.py:103` — `get_budget_status`
- `api/chat.py:52` — `create_chat`
- `api/chat.py:64` — `get_chats`
- `api/chat.py:79` — `get_messages`
- `api/chat.py:97` — `send_message`
- `api/chat.py:163` — `rename_chat`
- `api/chat.py:174` — `archive_chat`
- `api/chat.py:182` — `unarchive_chat`
- `api/chat.py:190` — `delete_chat`
- `api/chat.py:199` — `set_message_feedback`

## hooks.py — doc_events


## hooks.py — overrides



## hooks.py — fixtures & lifecycle

after_install = "erp_ai_integration.install.after_install"
after_migrate = "erp_ai_integration.install.after_migrate"

