"""Whitelisted endpoints for the AI chat UI.

Gate chain on every endpoint (plan doc §6):
settings.enabled -> access mode resolved (AI Chat User role + allowed_users
row, or System Manager) -> chat ownership where applicable.
"""

import frappe
from frappe import _
from frappe.utils import cint

from erp_ai_integration.ai.agent import generate_chat_title, run_turn
from erp_ai_integration.erp_ai_integration.doctype.claude_ai_settings.claude_ai_settings import (
	check_enabled,
)
from erp_ai_integration.permissions.access import get_access_mode

RATE_LIMIT_PER_HOUR = 30


def _check_access():
	check_enabled()
	if not get_access_mode(frappe.session.user):
		frappe.throw(
			_("You do not have access to AI Chat. Please contact your Administrator."),
			frappe.PermissionError,
		)


def _get_owned_chat(chat: str):
	doc = frappe.get_doc("AI Chat", chat)
	if doc.user != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("This chat belongs to another user."), frappe.PermissionError)
	return doc


def _check_rate_limit():
	user = frappe.session.user
	key = f"ai_chat_rate:{user}:{frappe.utils.now_datetime().strftime('%Y%m%d%H')}"
	cache = frappe.cache()
	count = cint(cache.get_value(key) or 0)
	if count >= RATE_LIMIT_PER_HOUR:
		frappe.throw(
			_("Rate limit reached ({0} questions per hour). Please try again later.").format(
				RATE_LIMIT_PER_HOUR
			)
		)
	cache.set_value(key, count + 1, expires_in_sec=3600)


@frappe.whitelist()
def create_chat():
	_check_access()
	doc = frappe.get_doc({
		"doctype": "AI Chat",
		"title": _("New Chat"),
		"user": frappe.session.user,
		"status": "Active",
	}).insert(ignore_permissions=True)
	return {"name": doc.name, "title": doc.title}


@frappe.whitelist()
def get_chats(include_archived: int = 0):
	_check_access()
	filters = {"user": frappe.session.user}
	if not cint(include_archived):
		filters["status"] = "Active"
	return frappe.get_all(
		"AI Chat",
		filters=filters,
		fields=["name", "title", "status", "last_message_on", "model_used"],
		order_by="last_message_on desc",
		limit_page_length=100,
	)


@frappe.whitelist()
def get_messages(chat: str, start: int = 0, limit: int = 50):
	_check_access()
	_get_owned_chat(chat)
	messages = frappe.get_all(
		"AI Chat Message",
		filters={"chat": chat},
		fields=[
			"name", "role", "content", "generated_sql", "feedback",
			"input_tokens", "output_tokens", "duration_ms", "error", "creation",
		],
		order_by="creation asc",
		limit_start=cint(start),
		limit_page_length=min(cint(limit) or 50, 100),
	)
	return messages


@frappe.whitelist()
def send_message(chat: str, message: str):
	"""Main entry: persist the question, run the agent loop, persist and
	return the answer."""
	_check_access()
	chat_doc = _get_owned_chat(chat)
	message = (message or "").strip()
	if not message:
		frappe.throw(_("Message is empty."))
	if len(message) > 5000:
		frappe.throw(_("Message is too long (max 5000 characters)."))
	_check_rate_limit()

	user = frappe.session.user
	is_first_message = not frappe.db.exists("AI Chat Message", {"chat": chat, "role": "user"})

	frappe.get_doc({
		"doctype": "AI Chat Message",
		"chat": chat,
		"role": "user",
		"content": message,
	}).insert(ignore_permissions=True)

	try:
		result = run_turn(chat, message, user)
	except Exception as e:
		frappe.log_error(title="AI chat turn failed", message=frappe.get_traceback())
		frappe.get_doc({
			"doctype": "AI Chat Message",
			"chat": chat,
			"role": "system_note",
			"content": _("The AI request failed."),
			"error": str(e)[:400],
		}).insert(ignore_permissions=True)
		frappe.db.commit()
		frappe.throw(_("The AI request failed: {0}").format(str(e)[:200]))

	assistant_msg = frappe.get_doc({
		"doctype": "AI Chat Message",
		"chat": chat,
		"role": "assistant",
		"content": result["answer"],
		"generated_sql": result["generated_sql"],
		"query_result_preview": result["query_result_preview"],
		"input_tokens": result["input_tokens"],
		"output_tokens": result["output_tokens"],
		"duration_ms": result["duration_ms"],
		"error": result["error"],
	}).insert(ignore_permissions=True)

	updates = {"last_message_on": frappe.utils.now_datetime(), "model_used": result["model"]}
	if is_first_message:
		updates["title"] = generate_chat_title(message, chat, user)
	chat_doc.db_set(updates, commit=False)
	frappe.db.commit()

	return {
		"message_name": assistant_msg.name,
		"answer": result["answer"],
		"generated_sql": result["generated_sql"],
		"model": result["model"],
		"duration_ms": result["duration_ms"],
		"chat_title": updates.get("title"),
	}


@frappe.whitelist()
def rename_chat(chat: str, title: str):
	_check_access()
	doc = _get_owned_chat(chat)
	title = (title or "").strip()[:60]
	if not title:
		frappe.throw(_("Title is empty."))
	doc.db_set("title", title)
	return {"title": title}


@frappe.whitelist()
def archive_chat(chat: str):
	_check_access()
	doc = _get_owned_chat(chat)
	doc.db_set("status", "Archived")
	return {"status": "Archived"}


@frappe.whitelist()
def unarchive_chat(chat: str):
	_check_access()
	doc = _get_owned_chat(chat)
	doc.db_set("status", "Active")
	return {"status": "Active"}


@frappe.whitelist()
def delete_chat(chat: str):
	_check_access()
	doc = _get_owned_chat(chat)
	doc.delete(ignore_permissions=True)  # on_trash removes its messages
	frappe.db.commit()
	return {"deleted": True}


@frappe.whitelist()
def set_message_feedback(message: str, feedback: str):
	"""Thumbs up/down on an assistant answer. feedback: 'Up' | 'Down' | ''
	(empty clears it). Dataset for future prompt tuning (plan doc §10.4)."""
	_check_access()
	if feedback not in ("Up", "Down", ""):
		frappe.throw(_("Invalid feedback value."))
	msg = frappe.get_doc("AI Chat Message", message)
	_get_owned_chat(msg.chat)  # ownership check via the parent chat
	if msg.role != "assistant":
		frappe.throw(_("Feedback can only be given on assistant answers."))
	msg.db_set("feedback", feedback)
	return {"feedback": feedback}
