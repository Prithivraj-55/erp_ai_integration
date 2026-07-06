# Copyright (c) 2026, Craft and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# USD per 1M tokens (input, output) — used for the estimated_cost column only
MODEL_PRICING = {
	# Claude (Anthropic)
	"claude-sonnet-4-6": (3.00, 15.00),
	"claude-haiku-4-5-20251001": (1.00, 5.00),
	"claude-haiku-4-5": (1.00, 5.00),
	"claude-opus-4-8": (5.00, 25.00),
	# ChatGPT (OpenAI) — approximate list prices
	"gpt-4o": (2.50, 10.00),
	"gpt-4o-mini": (0.15, 0.60),
	"gpt-4.1": (2.00, 8.00),
	"gpt-4.1-mini": (0.40, 1.60),
	"gpt-5": (1.25, 10.00),
	"gpt-5-mini": (0.25, 2.00),
}


class AIUsageLog(Document):
	pass


def log_usage(user: str, model: str, input_tokens: int, output_tokens: int, chat: str | None = None, request_type: str = "chat"):
	"""Insert one usage row and bump lifetime counters on settings."""
	pricing = MODEL_PRICING.get(model, (0, 0))
	cost = (input_tokens * pricing[0] + output_tokens * pricing[1]) / 1_000_000

	frappe.get_doc({
		"doctype": "AI Usage Log",
		"user": user,
		"chat": chat,
		"model": model,
		"request_type": request_type,
		"input_tokens": input_tokens,
		"output_tokens": output_tokens,
		"estimated_cost": cost,
	}).insert(ignore_permissions=True)

	# lifetime counters (single doc; direct db update to avoid version churn)
	frappe.db.sql(
		"""update `tabSingles` set value = cast(value as signed) + %s
		where doctype = 'Claude AI Settings' and field = 'total_input_tokens'""",
		(input_tokens,),
	)
	frappe.db.sql(
		"""update `tabSingles` set value = cast(value as signed) + %s
		where doctype = 'Claude AI Settings' and field = 'total_output_tokens'""",
		(output_tokens,),
	)
	frappe.clear_document_cache("Claude AI Settings", "Claude AI Settings")


def get_tokens_used_this_month() -> int:
	"""Combined input+output tokens for the current calendar month."""
	row = frappe.db.sql(
		"""select coalesce(sum(input_tokens + output_tokens), 0)
		from `tabAI Usage Log`
		where creation >= date_format(now(), '%Y-%m-01')""",
	)
	return int(row[0][0]) if row else 0
