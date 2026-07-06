# doctypes — erp_ai_integration

_Generated: 2026-07-06 21:39:00_

## ai_access_user

| Key | Value |
|-----|-------|
| Module | erp_ai_integration |
| Path | `erp_ai_integration/doctype/ai_access_user` |
| Controller | `erp_ai_integration/doctype/ai_access_user/ai_access_user.py` |
| Client script | none |

---

## ai_chat

| Key | Value |
|-----|-------|
| Module | erp_ai_integration |
| Path | `erp_ai_integration/doctype/ai_chat` |
| Controller | `erp_ai_integration/doctype/ai_chat/ai_chat.py` |
| Client script | none |
| doc_events | see hooks.md |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` before_insert` | no |
| ` on_trash` | no |
| ` get_permission_query_conditions` | no |
| ` has_permission` | no |

---

## ai_chat_message

| Key | Value |
|-----|-------|
| Module | erp_ai_integration |
| Path | `erp_ai_integration/doctype/ai_chat_message` |
| Controller | `erp_ai_integration/doctype/ai_chat_message/ai_chat_message.py` |
| Client script | none |
| doc_events | see hooks.md |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` get_permission_query_conditions` | no |

---

## ai_usage_log

| Key | Value |
|-----|-------|
| Module | erp_ai_integration |
| Path | `erp_ai_integration/doctype/ai_usage_log` |
| Controller | `erp_ai_integration/doctype/ai_usage_log/ai_usage_log.py` |
| Client script | none |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` log_usage` | no |
| ` get_tokens_used_this_month` | no |

---

## claude_ai_settings

| Key | Value |
|-----|-------|
| Module | erp_ai_integration |
| Path | `erp_ai_integration/doctype/claude_ai_settings` |
| Controller | `erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.py` |
| Client script | `erp_ai_integration/doctype/claude_ai_settings/claude_ai_settings.js` |

### Methods

| Method | Whitelisted |
|--------|-------------|
| ` validate` | no |
| ` validate_allowed_users` | no |
| ` get_model` | no |
| ` get_active_api_key` | no |
| ` get_settings` | no |
| ` check_enabled` | no |

---

