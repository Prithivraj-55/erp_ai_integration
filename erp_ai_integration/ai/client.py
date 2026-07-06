"""Provider-agnostic AI facade.

The rest of the app (agent loop, Test Connection, chat endpoints) calls ONLY
this module. The provider selected in Claude AI Settings ('Claude' or
'ChatGPT') decides which adapter handles the request:

- ai/anthropic_client.py  — Claude (Anthropic Messages API)
- ai/openai_client.py     — ChatGPT (OpenAI Chat Completions API)

Canonical formats (what callers pass in / get back, regardless of provider):

Messages — list of dicts:
  {"role": "user"|"assistant", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [{id, name, input}]}
  {"role": "tool_result", "tool_use_id": str, "content": str, "is_error": bool}

Tools — Anthropic-style definitions (converted for OpenAI by its adapter):
  {"name": str, "description": str, "input_schema": {json schema}}

Normalized response — dict:
  {"text": str, "tool_calls": [{id, name, input}],
   "stop_reason": "end_turn"|"tool_use"|"max_tokens",
   "model": str, "usage": {"input_tokens": int, "output_tokens": int}, "raw": obj}
"""

import frappe
from frappe import _

from erp_ai_integration.ai import anthropic_client, openai_client

PROVIDERS = {
	"Claude": anthropic_client,
	"ChatGPT": openai_client,
}


def get_settings():
	return frappe.get_cached_doc("Claude AI Settings")


def get_provider_name() -> str:
	return get_settings().provider or "Claude"


def get_adapter():
	name = get_provider_name()
	adapter = PROVIDERS.get(name)
	if not adapter:
		frappe.throw(_("Unknown AI provider: {0}").format(name))
	return adapter


def get_api_key() -> str:
	settings = get_settings()
	api_key = settings.get_active_api_key()
	if not api_key:
		frappe.throw(
			_("API key for provider {0} is not set in Claude AI Settings.").format(
				settings.provider or "Claude"
			)
		)
	return api_key


def get_model() -> str:
	return get_settings().get_model()


def create_message(messages, system=None, tools=None, max_tokens=None, model=None) -> dict:
	"""Single AI call via the configured provider. Returns the normalized
	response dict (see module docstring)."""
	settings = get_settings()
	return get_adapter().create_message(
		api_key=get_api_key(),
		model=model or settings.get_model(),
		messages=messages,
		system=system,
		tools=tools,
		max_tokens=max_tokens or settings.max_tokens or 4096,
	)


def ping() -> dict:
	"""Minimal API call used by Test Connection. Returns model + token usage."""
	response = create_message(
		messages=[{"role": "user", "content": "Reply with the single word: ok"}],
		max_tokens=16,
	)
	return {
		"provider": get_provider_name(),
		"model": response["model"],
		"input_tokens": response["usage"]["input_tokens"],
		"output_tokens": response["usage"]["output_tokens"],
	}
