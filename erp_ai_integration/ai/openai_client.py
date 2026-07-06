"""ChatGPT (OpenAI) provider adapter.

Converts between the canonical format (see ai/client.py) and the OpenAI Chat
Completions API. All openai SDK usage lives here.
"""

import json

from openai import OpenAI


def get_client(api_key: str) -> OpenAI:
	return OpenAI(api_key=api_key)


def to_wire_tools(tools: list[dict]) -> list[dict]:
	"""Canonical (Anthropic-style) tool defs -> OpenAI function-calling format."""
	return [
		{
			"type": "function",
			"function": {
				"name": t["name"],
				"description": t.get("description") or "",
				"parameters": t.get("input_schema") or {"type": "object", "properties": {}},
			},
		}
		for t in tools
	]


def to_wire_messages(messages: list[dict], system: str | None = None) -> list[dict]:
	"""Canonical messages -> OpenAI chat messages (system prompt prepended)."""
	wire = []
	if system:
		wire.append({"role": "system", "content": system})
	for msg in messages:
		role = msg["role"]
		if role == "tool_result":
			content = msg.get("content") or ""
			if msg.get("is_error"):
				content = f"ERROR: {content}"
			wire.append({
				"role": "tool",
				"tool_call_id": msg["tool_use_id"],
				"content": content,
			})
		elif role == "assistant" and msg.get("tool_calls"):
			wire.append({
				"role": "assistant",
				"content": msg.get("content") or None,
				"tool_calls": [
					{
						"id": call["id"],
						"type": "function",
						"function": {
							"name": call["name"],
							"arguments": json.dumps(call.get("input") or {}),
						},
					}
					for call in msg["tool_calls"]
				],
			})
		else:
			wire.append({"role": role, "content": msg.get("content") or ""})
	return wire


def create_message(api_key, model, messages, system=None, tools=None, max_tokens=4096) -> dict:
	"""Returns the normalized response dict defined in ai/client.py."""
	kwargs = {
		"model": model,
		"max_completion_tokens": max_tokens,
		"messages": to_wire_messages(messages, system=system),
	}
	if tools:
		kwargs["tools"] = to_wire_tools(tools)

	response = get_client(api_key).chat.completions.create(**kwargs)
	choice = response.choices[0]

	tool_calls = []
	for call in choice.message.tool_calls or []:
		try:
			args = json.loads(call.function.arguments or "{}")
		except ValueError:
			args = {}
		tool_calls.append({"id": call.id, "name": call.function.name, "input": args})

	stop_reason = {
		"tool_calls": "tool_use",
		"length": "max_tokens",
	}.get(choice.finish_reason, "end_turn")

	return {
		"text": choice.message.content or "",
		"tool_calls": tool_calls,
		"stop_reason": stop_reason,
		"model": response.model,
		"usage": {
			"input_tokens": response.usage.prompt_tokens if response.usage else 0,
			"output_tokens": response.usage.completion_tokens if response.usage else 0,
		},
		"raw": response,
	}
