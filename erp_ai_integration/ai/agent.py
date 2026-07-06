"""Synchronous tool-use agent loop (plan doc §5.3).

Provider-agnostic: talks only to ai/client.py using canonical messages and the
normalized response, so Claude and ChatGPT both work unchanged.
"""

import json
import time

import frappe
from frappe import _

from erp_ai_integration.ai import client as ai_client
from erp_ai_integration.ai.prompts import build_system_prompt
from erp_ai_integration.ai.tools import TOOL_DEFINITIONS, handle_tool_call
from erp_ai_integration.erp_ai_integration.doctype.ai_usage_log.ai_usage_log import (
	get_tokens_used_this_month,
	log_usage,
)

HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 4000  # per message, keeps token use bounded


def check_budget(settings):
	budget = settings.monthly_token_budget or 0
	if budget and get_tokens_used_this_month() >= budget:
		frappe.throw(
			_("The monthly AI token budget has been reached. Please contact your Administrator.")
		)


def build_history(chat: str) -> list[dict]:
	"""Canonical messages from the chat's persisted history (each chat has
	fully independent memory)."""
	rows = frappe.get_all(
		"AI Chat Message",
		filters={"chat": chat, "role": ("in", ["user", "assistant"])},
		fields=["role", "content"],
		order_by="creation desc",
		limit_page_length=HISTORY_MESSAGES,
	)
	messages = []
	for row in reversed(rows):
		content = (row.content or "")[:MAX_HISTORY_CHARS]
		if content:
			messages.append({"role": row.role, "content": content})
	# providers require the first message to be from the user
	while messages and messages[0]["role"] != "user":
		messages.pop(0)
	return messages


def run_turn(chat: str, user_text: str, user: str) -> dict:
	"""Run one full agent turn (question -> tools -> answer).

	Returns {answer, model, input_tokens, output_tokens, duration_ms,
	generated_sql, query_result_preview, error}.
	"""
	settings = frappe.get_cached_doc("Claude AI Settings")
	check_budget(settings)

	system = build_system_prompt(user)
	messages = build_history(chat)
	messages.append({"role": "user", "content": user_text})

	total_in = total_out = 0
	generated_sqls: list[str] = []
	result_previews: list[str] = []
	answer = ""
	error = None
	started = time.monotonic()
	model = settings.get_model()

	for _iteration in range(settings.max_tool_iterations or 8):
		response = ai_client.create_message(messages, system=system, tools=TOOL_DEFINITIONS)
		model = response["model"]
		total_in += response["usage"]["input_tokens"]
		total_out += response["usage"]["output_tokens"]
		log_usage(
			user=user,
			model=model,
			input_tokens=response["usage"]["input_tokens"],
			output_tokens=response["usage"]["output_tokens"],
			chat=chat,
			request_type="chat",
		)

		if response["stop_reason"] == "tool_use" and response["tool_calls"]:
			messages.append({
				"role": "assistant",
				"content": response["text"],
				"tool_calls": response["tool_calls"],
			})
			for call in response["tool_calls"]:
				content, is_error = handle_tool_call(call["name"], call.get("input") or {}, user)
				if call["name"] == "run_query" and not is_error:
					try:
						payload = json.loads(content)
						generated_sqls.append(payload.get("executed_sql") or "")
						result_previews.append(
							json.dumps(
								{"columns": payload.get("columns"), "rows": (payload.get("rows") or [])[:10]}
							)
						)
					except ValueError:
						pass
				messages.append({
					"role": "tool_result",
					"tool_use_id": call["id"],
					"content": content,
					"is_error": is_error,
				})
			continue

		answer = response["text"]
		break
	else:
		answer = _(
			"I could not finish answering within the allowed number of steps. "
			"Please try a simpler or more specific question."
		)
		error = "max_tool_iterations reached"

	return {
		"answer": answer,
		"model": model,
		"input_tokens": total_in,
		"output_tokens": total_out,
		"duration_ms": int((time.monotonic() - started) * 1000),
		"generated_sql": "\n\n".join(s for s in generated_sqls if s) or None,
		"query_result_preview": "\n".join(result_previews) or None,
		"error": error,
	}


def generate_chat_title(question: str, chat: str, user: str) -> str:
	"""One cheap model call to name the chat from the first question."""
	fallback = (question or "").strip().replace("\n", " ")[:50] or _("New Chat")
	try:
		settings = frappe.get_cached_doc("Claude AI Settings")
		cheap_model = (
			"gpt-4o-mini" if settings.provider == "ChatGPT" else "claude-haiku-4-5-20251001"
		)
		response = ai_client.create_message(
			messages=[{
				"role": "user",
				"content": (
					"Generate a title of at most 5 words for a chat that starts with this "
					f"question. Reply with the title only, no quotes:\n\n{question[:400]}"
				),
			}],
			max_tokens=24,
			model=cheap_model,
		)
		log_usage(
			user=user,
			model=response["model"],
			input_tokens=response["usage"]["input_tokens"],
			output_tokens=response["usage"]["output_tokens"],
			chat=chat,
			request_type="title",
		)
		title = (response["text"] or "").strip().strip('"').strip()
		return title[:60] or fallback
	except Exception:
		return fallback
